"""Run via manage.py shell with NARRATIVE_DATA_DIR pointing to a disposable migrated database."""
import json
import os
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from mainapp import messenger, vn_scenes
from mainapp.models import Character

if not os.environ.get("NARRATIVE_DATA_DIR") or Path(settings.DATA_DIR).resolve() == Path(settings.BASE_DIR).resolve():
    raise RuntimeError("Set NARRATIVE_DATA_DIR to a disposable database directory before seeding the browser fixture.")

user, _ = get_user_model().objects.get_or_create(username="screen-workflow-fixture", defaults={"persona_name": "Rowan"})
user.set_unusable_password(); user.save(update_fields=["password"])
character, _ = Character.objects.get_or_create(author=user, slug="screen-workflow-mira",
    defaults={"name": "Mira", "description": "An archivist returning a borrowed map."})
other = messenger.create_thread(user, [character], title="Other fixture chat")
other_data = messenger.thread_data(other); other_data["started"] = True
messenger.save_thread_data(other, other_data)
thread = messenger.create_thread(user, [character])
data = messenger.thread_data(thread)
data.update(started=True, lore_pending=True, lore_mode="off")
messenger.save_thread_data(thread, data)
vn_scenes.save_vn_state(user, {"active_scene": None, "drafts": []})
backgrounds = vn_scenes.available_backgrounds([character])
if len(backgrounds) < 2:
    raise RuntimeError("The visual-transition fixture needs two bundled backgrounds.")
response = {"title": "At the archive", "handoff": "user_turn", "choices": ["Here is your map.", '"Were you worried?"'],
    "beats": [{"speaker_slug": "narrator", "text": "Mira waits outside the archive.",
               "stage": {"location": "Outside the archive", "background": backgrounds[0]["id"]}},
              {"speaker_slug": character.slug, "text": "You brought it back. I was beginning to wonder.",
               "stage": {"location": "Inside the archive", "background": backgrounds[1]["id"]}}]}
with patch.object(vn_scenes, "_call_vn_json", return_value=response):
    vn_scenes.start_scene(user, thread)
client = Client(); client.force_login(user)
target = Path(settings.DATA_DIR) / "browser-session.json"
target.write_text(json.dumps({"sessionid": client.cookies["sessionid"].value}))
target.chmod(0o600)
print(f"Seeded the disposable workflow fixture. Browser session: {target}")
