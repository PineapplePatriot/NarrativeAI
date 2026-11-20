"""Disposable fixtures for check_drive_proposals.cjs; run after seed_screen_workflow.py."""
import os
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from mainapp.models import ScreenEntry, ScreenDocumentProposal

if not os.environ.get('NARRATIVE_DATA_DIR') or Path(settings.DATA_DIR).resolve() == Path(settings.BASE_DIR).resolve():
    raise RuntimeError('Use a disposable NARRATIVE_DATA_DIR.')
user = get_user_model().objects.get(username='screen-workflow-fixture')
thread = user.messenger_threads.first()
character = thread.characters.first()
for width in (390, 1280):
    for prefix in ('Shared', 'Stale'):
        item = ScreenEntry.objects.create(owner=user, thread=thread, kind='document',
            title=f'{prefix} packing list {width}', body='Packing list\n- Map', data={'scope':'shared'})
        ScreenDocumentProposal.objects.create(document=item, base_revision=1, before=item.body,
            after=item.body+'\n- Lantern', character_slug=character.slug, character_name=character.name)
print('Seeded Drive proposal fixtures without generation.')
