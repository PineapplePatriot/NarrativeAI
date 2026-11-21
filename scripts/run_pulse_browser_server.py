"""Local, disposable UI-test server. All provider calls are replaced or blocked."""
import json
import os
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from mainapp import ai_client, vn_scenes

if not os.environ.get('NARRATIVE_DATA_DIR') or Path(settings.DATA_DIR).resolve() == Path(settings.BASE_DIR).resolve():
    raise RuntimeError('Use a disposable NARRATIVE_DATA_DIR.')

def fake_complete(user, task, messages, **kwargs):
    if 'PULSE INVITATION REPLIES' not in json.dumps(messages):
        raise ai_client.AIError('Live model calls are blocked by the Pulse browser-test server.')
    payload=json.loads(messages[-1]['content'])
    return json.dumps({'responses':[{'slug':c['slug'],'response':'accepted',
        'text':'I will bring the annotated map.'} for c in payload['cast']]})

def fake_vn(user, prompt, scene=None, **kwargs):
    if not scene or not scene.get('pulse_event'):
        raise ai_client.AIError('Only fixture Pulse scenes are enabled on this server.')
    return {'title':'The planned archive visit','location':scene['pulse_event']['location'],
        'beats':[{'speaker_slug':scene['character_slugs'][0],'text':'Here is my copy of the map.'}],
        'choices':['Compare the annotations.'],'handoff':'user_turn'}

def blocked(*args,**kwargs):
    raise ai_client.AIError('Live image generation is blocked by the Pulse browser-test server.')

ai_client.resolve=lambda *args,**kwargs:(None,'fixture/model')
ai_client.complete=fake_complete
ai_client.generate_image=blocked
vn_scenes._call_vn_json=fake_vn
call_command('runserver','127.0.0.1:8767',use_reloader=False)
