import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from mainapp import messenger, pulse
from mainapp.models import Character, PulseReminder, ScreenEntry


class PulseTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='pulse-user')
        self.other=get_user_model().objects.create_user(username='pulse-other')
        self.mira=Character.objects.create(author=self.user,name='Mira',slug='pulse-mira')
        self.oren=Character.objects.create(author=self.user,name='Oren',slug='pulse-oren')
        self.thread=messenger.create_thread(self.user,[self.mira,self.oren])
        self.second=messenger.create_thread(self.user,[self.mira])
        self.client.force_login(self.user)
        self.now=timezone.now().replace(microsecond=0)
        self.model=patch('mainapp.ai_client.complete',side_effect=AssertionError('Unexpected model request')).start()
        self.addCleanup(patch.stopall)
        patch('mainapp.ai_client.resolve',return_value=(None,'test/model')).start()

    def post(self,action,**data):
        return self.client.post(reverse('screen_apps_api'),json.dumps({'action':action,'thread_id':self.thread.pk,**data}),content_type='application/json')

    def event(self,**data):
        details={'when':(self.now+timedelta(minutes=30)).isoformat(),'timezone':'Europe/Kyiv','status':'confirmed',
                 'location':'Archive','reminder_minutes':15,'participants':[self.mira.slug],**data}
        response=self.post('create',kind='event',title='Bring the map',body='Compare the annotated copies.',data=details)
        self.assertEqual(response.status_code,201,response.content)
        return response.json()['entry']

    def save(self,item,**data):
        return self.post('save',id=item['id'],revision=item['revision'],title=item['title'],body=item['body'],data={**item['data'],**data})

    def test_exactly_once_delivery_is_free_and_not_character_attendance(self):
        item=self.event()
        self.assertEqual(pulse.deliver_due(user=self.user,now=self.now+timedelta(minutes=14))['delivered'],0)
        self.assertEqual(pulse.deliver_due(user=self.user,now=self.now+timedelta(minutes=15))['delivered'],1)
        self.assertEqual(pulse.deliver_due(user=self.user,now=self.now+timedelta(minutes=16))['delivered'],0)
        self.thread.refresh_from_db();message=self.thread.data['messages'][-1]
        self.assertEqual(message['role'],'system');self.assertEqual(message['pulse_event_id'],item['id'])
        self.assertNotIn('sender_slug',message);self.assertEqual(self.thread.data['unread'],1)
        self.assertEqual(messenger.thread_data(self.second)['messages'],[])
        self.model.assert_not_called()

    def test_cancelled_and_unconfirmed_plans_do_not_notify(self):
        for state in ['planned','tentative','declined','cancelled','completed']:
            self.event(status=state)
        result=pulse.deliver_due(user=self.user,now=self.now+timedelta(minutes=30))
        self.assertEqual(result['delivered'],0)
        self.assertFalse(PulseReminder.objects.filter(enabled=True).exists())
        self.model.assert_not_called()

    def test_reminder_off_and_minor_saves_do_not_duplicate_delivery(self):
        off=self.event(reminder_minutes=None)
        item=self.event()
        pulse.deliver_due(user=self.user,now=self.now+timedelta(minutes=16))
        result=self.save(item)
        self.assertEqual(result.status_code,200,result.content)
        self.assertIsNotNone(result.json()['entry']['schedule']['delivered_at'])
        self.assertEqual(pulse.deliver_due(user=self.user,now=self.now+timedelta(minutes=17))['delivered'],0)
        self.assertFalse(PulseReminder.objects.get(event_id=off['id']).enabled)
        group=self.event(participants=[self.mira.slug,self.oren.slug])
        reordered=self.save(group,participants=[self.oren.slug,self.mira.slug]).json()['entry']
        self.assertEqual(reordered['data']['status'],'confirmed')

    def test_story_clock_moves_its_reminder_but_not_real_time_reminders(self):
        story=self.event(clock='chat',when=(self.now+timedelta(minutes=90)).isoformat())
        self.event(clock='real',when=(self.now+timedelta(minutes=90)).isoformat())
        data=messenger.thread_data(self.thread);data['clock_offset']=5400;messenger.save_thread_data(self.thread,data)
        result=pulse.deliver_due(user=self.user,now=self.now)
        self.assertEqual(result['delivered'],1)
        self.assertIsNotNone(PulseReminder.objects.get(event_id=story['id']).delivered_at)
        self.assertEqual(PulseReminder.objects.filter(delivered_at__isnull=False).count(),1)

    def test_finished_missed_events_expire_without_fabricating_completion(self):
        item=self.event(when=(self.now-timedelta(hours=2)).isoformat())
        result=pulse.deliver_due(user=self.user,now=self.now)
        self.assertEqual(result['expired'],1);self.assertEqual(result['delivered'],0)
        self.assertEqual(ScreenEntry.objects.get(pk=item['id']).data['status'],'confirmed')
        self.thread.refresh_from_db();self.assertEqual(self.thread.data['messages'],[])

    def test_bounded_worker_rotates_future_story_jobs(self):
        self.event(clock='chat',when=(self.now-timedelta(hours=2)).isoformat())
        self.event(clock='real',when=(self.now+timedelta(minutes=5)).isoformat())
        data=messenger.thread_data(self.thread);data['clock_offset']=-86400;messenger.save_thread_data(self.thread,data)
        self.assertEqual(pulse.deliver_due(user=self.user,limit=1,now=self.now)['delivered'],0)
        self.assertEqual(pulse.deliver_due(user=self.user,limit=1,now=self.now)['delivered'],1)

    def test_invitation_and_cast_replies_confirm_the_saved_plan(self):
        item=self.event(status='planned',participants=[self.mira.slug,self.oren.slug])
        invited=self.post('pulse_invite',id=item['id'],revision=1).json()['entry']
        self.assertEqual(invited['data']['status'],'invited');self.model.assert_not_called()
        self.model.side_effect=None
        self.model.return_value=json.dumps({'responses':[{'slug':c.slug,'response':'accepted','text':'I can bring my copy.'} for c in [self.mira,self.oren]]})
        response=self.post('pulse_respond',id=item['id'],revision=invited['revision'])
        self.assertEqual(response.status_code,200,response.content)
        confirmed=response.json()['entry'];self.assertEqual(confirmed['data']['status'],'confirmed')
        self.assertTrue(confirmed['schedule']['enabled']);self.model.assert_called_once()
        self.thread.refresh_from_db();self.assertEqual(len(self.thread.data['messages']),3)
        self.assertEqual(self.post('pulse_respond',id=item['id'],revision=confirmed['revision']).status_code,400)
        self.assertEqual(self.model.call_count,1)

    def test_tentative_and_declined_replies_are_valid(self):
        for answer in ['tentative','declined']:
            item=self.event(status='planned')
            invited=self.post('pulse_invite',id=item['id'],revision=1).json()['entry']
            self.model.side_effect=None
            self.model.return_value=json.dumps({'responses':[{'slug':self.mira.slug,'response':answer,'text':'I need to check.'}]})
            response=self.post('pulse_respond',id=item['id'],revision=invited['revision']).json()['entry']
            self.assertEqual(response['data']['status'],answer);self.assertFalse(response['schedule']['enabled'])

    def test_invalid_model_response_and_concurrent_edit_do_not_deliver(self):
        item=self.event(status='planned')
        invited=self.post('pulse_invite',id=item['id'],revision=1).json()['entry']
        self.model.side_effect=None;self.model.return_value='{"responses":[]}'
        self.assertEqual(self.post('pulse_respond',id=item['id'],revision=invited['revision']).status_code,400)
        def change_during_generation(*args,**kwargs):
            self.save(invited,location='Different room')
            return json.dumps({'responses':[{'slug':self.mira.slug,'response':'accepted','text':'Yes.'}]})
        self.model.side_effect=change_during_generation
        self.assertEqual(self.post('pulse_respond',id=item['id'],revision=invited['revision']).status_code,409)
        self.thread.refresh_from_db();self.assertEqual(len(self.thread.data['messages']),1)
        self.assertEqual(ScreenEntry.objects.get(pk=item['id']).data['status'],'planned')

    def test_rescheduling_resets_rsvps_and_requires_confirmation(self):
        item=self.event()
        updated=self.save(item,when=(self.now+timedelta(hours=3)).isoformat()).json()['entry']
        self.assertEqual(updated['data']['status'],'planned');self.assertFalse(updated['schedule']['enabled'])
        confirmed=self.save(updated,status='confirmed').json()['entry']
        self.assertTrue(confirmed['schedule']['enabled'])
        self.assertEqual(pulse.deliver_due(user=self.user,now=self.now+timedelta(minutes=16))['delivered'],0)

    def test_cast_change_during_reply_generation_does_not_confirm_or_post(self):
        item=self.event(status='planned')
        invited=self.post('pulse_invite',id=item['id'],revision=1).json()['entry']
        def remove_during_generation(*args,**kwargs):
            self.thread.characters.remove(self.mira)
            return json.dumps({'responses':[{'slug':self.mira.slug,'response':'accepted','text':'Yes.'}]})
        self.model.side_effect=remove_during_generation
        self.assertEqual(self.post('pulse_respond',id=item['id'],revision=invited['revision']).status_code,400)
        self.thread.refresh_from_db();self.assertEqual(len(self.thread.data['messages']),1)
        self.assertEqual(ScreenEntry.objects.get(pk=item['id']).data['status'],'invited')

    def test_timezone_participant_and_scheduler_validation(self):
        for changes in [{'timezone':'not/a-zone'},{'clock':'invented'},{'participants':['outsider']},
                        {'participants':[self.mira.slug,self.mira.slug]},{'reminder_minutes':True},
                        {'duration_minutes':0},{'reminder_minutes':-1}]:
            response=self.post('create',kind='event',title='Bad',data={'when':self.now.isoformat(),**changes})
            self.assertEqual(response.status_code,400,response.content)
        self.model.assert_not_called()

    def test_scheduler_and_plan_access_are_scoped_to_account(self):
        item=self.event()
        self.client.force_login(self.other)
        self.assertEqual(self.post('pulse_scene_seed',id=item['id'],revision=1).status_code,404)
        self.assertEqual(self.post('pulse_tick').json()['delivered'],0)
        self.assertEqual(pulse.deliver_due(user=self.other,now=self.now+timedelta(hours=1))['delivered'],0)

    def test_offline_command_and_authenticated_poll_deliver_without_models(self):
        self.event(when=(timezone.now()-timedelta(minutes=1)).isoformat(),reminder_minutes=0)
        out=StringIO();call_command('pulse_tick',user_id=self.user.pk,stdout=out)
        self.assertIn("'delivered': 1",out.getvalue())
        self.client.get(reverse('messenger_api'),{'action':'poll'})
        self.thread.refresh_from_db();self.assertEqual(len(self.thread.data['messages']),1)
        self.model.assert_not_called()

    def test_confirmed_plan_seeds_vn_with_exact_cast_time_and_context(self):
        item=self.event()
        free=self.post('pulse_scene_seed',id=item['id'],revision=1)
        self.assertEqual(free.status_code,200);self.model.assert_not_called()
        response={'title':'Archive','beats':[{'speaker_slug':self.mira.slug,'text':'Here is the map.'}],'choices':[],'handoff':'user_turn'}
        with patch('mainapp.vn_scenes._call_vn_json',return_value=response) as generated:
            result=self.client.post(reverse('vn_scenes_api'),json.dumps({'action':'start_scene','thread_id':self.thread.pk,
                'pulse_event_id':item['id'],'pulse_event_revision':1,'character_slugs':[self.oren.slug]}),content_type='application/json')
        self.assertEqual(result.status_code,200,result.content)
        scene=result.json()['scene'];self.assertEqual(scene['character_slugs'],[self.mira.slug])
        self.assertEqual(scene['pulse_event']['id'],item['id'])
        self.assertEqual(scene['context']['clock'],free.json()['pulse_seed']['when_label'])
        self.assertIn('Compare the annotated copies',generated.call_args.args[1])
        self.thread.refresh_from_db();self.assertEqual(self.thread.data.get('clock_offset',0),0)
        self.assertEqual(ScreenEntry.objects.get(pk=item['id']).data['status'],'confirmed')

    def test_unconfirmed_or_stale_plans_do_not_generate_scenes(self):
        item=self.event(status='planned')
        self.assertEqual(self.post('pulse_scene_seed',id=item['id'],revision=1).status_code,400)
        result=self.client.post(reverse('vn_scenes_api'),json.dumps({'action':'start_scene','thread_id':self.thread.pk,
            'pulse_event_id':item['id'],'pulse_event_revision':2}),content_type='application/json')
        self.assertEqual(result.status_code,400);self.model.assert_not_called()

    def test_watch_retries_transient_failures_without_exiting(self):
        with patch('mainapp.pulse.deliver_due',side_effect=RuntimeError('Temporary failure')) as tick, \
             patch('mainapp.management.commands.pulse_tick.time.sleep',side_effect=KeyboardInterrupt) as sleep, \
             self.assertLogs('mainapp.management.commands.pulse_tick',level='ERROR'):
            call_command('pulse_tick',watch=True,stdout=StringIO())
        tick.assert_called_once();sleep.assert_called_once_with(60)
        self.model.assert_not_called()

    def test_command_rejects_bad_limits_and_unknown_accounts(self):
        from django.core.management.base import CommandError
        for kwargs in [{'limit':0},{'interval':1},{'user_id':999999999}]:
            with self.assertRaises(CommandError):
                call_command('pulse_tick',stdout=StringIO(),**kwargs)

    def test_home_counts_only_open_plans(self):
        for state in pulse.STATUSES:
            self.event(status=state)
        overview=self.client.get(reverse('screen_apps_api'),{'action':'overview'}).json()
        self.assertEqual(overview['events'],4)
