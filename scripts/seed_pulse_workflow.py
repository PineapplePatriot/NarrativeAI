"""Disposable plans for check_pulse_workflow.cjs. Run after seed_screen_workflow.py."""
import os
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from mainapp import messenger, pulse, vn_scenes
from mainapp.models import Character, ScreenEntry

if not os.environ.get('NARRATIVE_DATA_DIR') or Path(settings.DATA_DIR).resolve() == Path(settings.BASE_DIR).resolve():
    raise RuntimeError('Use a disposable NARRATIVE_DATA_DIR.')
user=get_user_model().objects.get(username='screen-workflow-fixture')
thread=user.messenger_threads.first()
mira=Character.objects.get(author=user,slug='screen-workflow-mira')
oren,_=Character.objects.get_or_create(author=user,slug='pulse-browser-oren',defaults={'name':'Oren','description':'A colleague with his own priorities.'})
thread.characters.add(oren)
raw=messenger.thread_data(thread)
raw['events']=[{'id':'pulse-fixture-note','title':'Coffee after the archive','when':'Tomorrow around lunch','notes':'Pick a date together.','done':False}]
messenger.save_thread_data(thread,raw)
ScreenEntry.objects.filter(owner=user,kind='event',title__startswith='Pulse archive visit ').delete()
for width in (390,1280):
    details=pulse.prepare(pulse.normalize({'when':(timezone.now()+timedelta(minutes=30)).isoformat(),
        'timezone':'Europe/Kyiv','status':'planned','location':'Gate Nine','reminder_minutes':15,
        'participants':[mira.slug]}),thread)
    entry=ScreenEntry.objects.create(owner=user,thread=thread,kind='event',title=f'Pulse archive visit {width}',
        body='Compare the annotated maps.',data=details)
    pulse.sync_event(entry)
vn_scenes.save_vn_state(user,{'active_scene':None,'drafts':[]})
print('Seeded Pulse plans without model calls.')
