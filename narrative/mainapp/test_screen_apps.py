import json
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from mainapp import messenger, screen_apps
from mainapp.models import Character, ScreenEntry


class ScreenAppsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='desk-owner')
        self.other = get_user_model().objects.create_user(username='other-desk')
        self.char = Character.objects.create(author=self.user, slug='desk-mira', name='Mira')
        self.thread = messenger.create_thread(self.user, [self.char])
        self.second = messenger.create_thread(self.user, [self.char])
        self.foreign = messenger.create_thread(self.other, [self.char])
        self.client.force_login(self.user)
        self.url = reverse('screen_apps_api')
        self.model = patch('mainapp.ai_client.complete', side_effect=AssertionError('Unexpected model spend')).start()
        self.addCleanup(patch.stopall)

    def post(self, action, **kwargs):
        return self.client.post(self.url, json.dumps({'action': action, 'thread_id': self.thread.pk, **kwargs}), content_type='application/json')

    def create(self, kind='document', **kwargs):
        response = self.post('create', kind=kind, title='Desk record', **kwargs)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['entry']

    def test_scope_and_owner_isolation(self):
        self.create(body='only this chat')
        self.assertEqual(self.client.get(self.url, {'thread_id': self.second.pk}).json()['entries'], [])
        self.assertEqual(self.client.get(self.url, {'thread_id': self.foreign.pk}).status_code, 404)
        self.assertEqual(self.post('create', thread_id=self.foreign.pk, title='x', kind='document').status_code, 404)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url, {'thread_id': self.thread.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.url, {'action': 'overview'}).json()['documents'], 0)
        self.model.assert_not_called()

    def test_concurrent_save_and_delete_keep_newer_record(self):
        item = self.create(body='old')
        result = self.post('save', id=item['id'], revision=1, title='New', body='new', data={'scope': 'shared'})
        self.assertEqual(result.json()['entry']['revision'], 2)
        for action in ['save', 'delete', 'forward']:
            response = self.post(action, id=item['id'], revision=1, title='stale', body='stale')
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()['current']['body'], 'new')
        self.assertEqual(ScreenEntry.objects.get(pk=item['id']).body, 'new')

    def test_private_documents_mail_and_tracks_never_enter_phone_context(self):
        self.create(body='PRIVATE_DO_NOT_KNOW')
        self.create(body='SHARED_KEY_FACT', data={'scope': 'shared'})
        self.create('mail', body='MAIL_DRAFT_DO_NOT_KNOW')
        self.create('track', body='PLAYLIST_DO_NOT_KNOW')
        context = screen_apps.context_for(self.thread)
        self.assertIn('SHARED_KEY_FACT', context)
        for private in ['PRIVATE_DO_NOT_KNOW', 'MAIL_DRAFT_DO_NOT_KNOW', 'PLAYLIST_DO_NOT_KNOW']:
            self.assertNotIn(private, context)
        self.assertEqual(screen_apps.context_for(self.second), '')
        with patch('mainapp.ai_client.resolve', return_value=(None,'test/model')):
            prompt = json.dumps(messenger.build_messenger_prompt(self.user,self.thread))
        self.assertIn('SHARED_KEY_FACT', prompt)
        self.assertNotIn('PRIVATE_DO_NOT_KNOW', prompt)

    def test_calendar_is_dated_plan_not_fake_location_or_attendance(self):
        item = self.create('event', data={'when': '2026-12-01T14:30:00+02:00', 'location':'Archive'})
        context = screen_apps.context_for(self.thread)
        self.assertIn('not proof it happened', context)
        self.assertIn('+02:00', item['data']['when'])
        self.assertEqual(self.post('create', kind='event', title='bad', data={'when':'tomorrow'}).status_code,400)
        self.assertEqual(self.post('create', kind='event', title='bad', data={'when':'2026-12-01T14:30'}).status_code,400)
        self.assertEqual(self.post('create', kind='event', title='bad', data={'when':'2026-12-01T14:30Z','done':'false'}).status_code,400)
        done = self.post('save', id=item['id'], revision=1, title='done', data={**item['data'],'done':True})
        self.assertEqual(done.status_code,200)
        self.assertEqual(screen_apps.context_for(self.thread),'')
        self.model.assert_not_called()

    def test_archive_only_delivered_media_and_selected_chat(self):
        data = messenger.thread_data(self.thread)
        data['messages'] = [
            {'id':'file', 'role':'assistant', 'file':{'name':'map.txt','content':'Gate Nine'}},
            {'id':'voice', 'role':'assistant', 'voice':{'transcript':'hello','audio_url':'/media/a.mp3'}},
            {'id':'future', 'role':'assistant', 'deliver_at':time.time()+3600, 'file':{'content':'FUTURE_SECRET'}},
        ]
        messenger.save_thread_data(self.thread,data)
        result = self.client.get(self.url,{'thread_id':self.thread.pk}).json()
        self.assertEqual([r['id'] for r in result['receipts']], ['file','voice'])
        self.assertNotIn('FUTURE_SECRET',json.dumps(result))
        self.assertEqual(self.client.get(self.url,{'thread_id':self.second.pk}).json()['receipts'],[])
        self.model.assert_not_called()

    def test_forward_explicitly_shares_snapshot_without_generation(self):
        item = self.create(body='Private until forwarded')
        result = self.post('forward',id=item['id'],revision=1)
        self.assertTrue(result.json()['forwarded'])
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data['messages'][-1]['file']['content'],'Private until forwarded')
        self.assertEqual(ScreenEntry.objects.get(pk=item['id']).data['scope'],'private')
        self.second.refresh_from_db()
        self.assertEqual(self.second.data['messages'],[])
        self.model.assert_not_called()

    def test_mail_preview_spends_once_and_does_not_deliver(self):
        item = self.create('mail')
        self.model.side_effect = None; self.model.return_value='I can meet you at the archive.'
        with patch('mainapp.ai_client.resolve',return_value=(None,'test/model')):
            result=self.post('draft_mail',id=item['id'],revision=1,character_slug=self.char.slug,direction='Confirm the plan.')
        self.assertEqual(result.status_code,200,result.content)
        self.assertIn('archive',result.json()['draft'])
        self.model.assert_called_once()
        self.assertEqual(ScreenEntry.objects.get(pk=item['id']).data['messages'],[])
        self.thread.refresh_from_db();self.assertEqual(self.thread.data['messages'],[])
        self.assertIn('MAIL PRESENTATION',json.dumps(self.model.call_args.args[2]))
        delivered=self.post('send_mail',id=item['id'],revision=1,sender_slug=self.char.slug,body=result.json()['draft'])
        self.assertEqual(delivered.json()['entry']['data']['messages'][0]['sender'],'Mira')
        self.assertEqual(self.post('send_mail',id=item['id'],revision=1,body='stale').status_code,409)

    def test_mail_history_cannot_be_forged_through_save(self):
        item=self.create('mail')
        self.assertEqual(self.post('save',id=item['id'],revision=1,title='bad',data={'messages':[{'body':'made up'}]}).status_code,400)
        self.assertEqual(self.post('send_mail',id=item['id'],revision=1,sender_slug='someone-else',body='hi').status_code,400)
        self.assertEqual(self.post('create',kind='mail',title='bad',data={'messages':[{}]}).status_code,400)

    def test_unsafe_links_and_bad_inputs_rejected_without_calls(self):
        for link in ['javascript:alert(1)','data:text/html,x','//example.com','https://user:secret@example.com']:
            self.assertEqual(self.post('create',kind='track',title='bad',data={'url':link}).status_code,400)
        for thread in [True,0,-1,'no',2**80]:
            self.assertEqual(self.post('create',thread_id=thread,kind='document',title='bad').status_code,400)
        for raw in ['[]','null','bad']:
            self.assertEqual(self.client.post(self.url,raw,content_type='application/json').status_code,400)
        self.assertEqual(self.post('create',kind='not-an-app',title='bad').status_code,400)
        self.assertEqual(self.post('create',kind='document',title='',data={}).status_code,400)
        self.assertEqual(self.post('create',kind='document',title='bad',data=[]).status_code,400)
        self.model.assert_not_called()

    def test_record_cannot_be_moved_between_chats(self):
        item=self.create()
        self.assertEqual(self.post('save',id=item['id'],revision=1,thread_id=self.second.pk,title='move').status_code,404)
        self.assertEqual(ScreenEntry.objects.get(pk=item['id']).thread_id,self.thread.pk)

    def test_delete_removes_shared_context_and_counts(self):
        item=self.create(body='Shared fact',data={'scope':'shared'})
        self.assertEqual(self.client.get(self.url,{'action':'overview'}).json()['documents'],1)
        self.assertEqual(self.post('delete',id=item['id'],revision=1).status_code,200)
        self.assertEqual(screen_apps.context_for(self.thread),'')
        self.assertEqual(self.client.get(self.url,{'action':'overview'}).json()['documents'],0)

    def test_requires_login_and_supported_methods(self):
        self.assertEqual(self.client.put(self.url).status_code,405)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code,302)

    def test_home_does_not_mark_unopened_chat_as_read(self):
        data=messenger.thread_data(self.thread)
        data['unread']=3
        messenger.save_thread_data(self.thread,data)
        self.assertEqual(self.client.get(reverse('screen_hub')).status_code,200)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data['unread'],3)
        self.client.get(reverse('screen_hub'),{'thread':self.thread.pk})
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data['unread'],0)
