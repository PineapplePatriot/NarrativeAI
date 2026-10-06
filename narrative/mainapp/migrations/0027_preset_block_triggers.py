"""Saved presets made from the Realistic Frankenstein starters lost which blocks fire only on some kinds of
generation (e.g. "Impersonation Turn", only when the AI writes the user's message). Put that back."""
import json
from pathlib import Path

from django.db import migrations

STARTERS = Path(__file__).resolve().parent.parent / "data" / "starters"


def restore_triggers(apps, schema_editor):
    known = {}
    for path in STARTERS.glob("*.json"):
        for b in json.loads(path.read_text(encoding="utf-8")).get("preset", {}).get("blocks", []):
            if b.get("triggers"):
                known.setdefault(b["name"], b["triggers"])
    Preset = apps.get_model("mainapp", "Preset")
    for preset in Preset.objects.all():
        data = preset.data if isinstance(preset.data, dict) else {}
        changed = False
        for b in data.get("blocks") or []:
            if isinstance(b, dict) and not b.get("triggers") and b.get("name") in known:
                b["triggers"] = known[b["name"]]
                changed = True
        if changed:
            preset.data = data
            preset.save(update_fields=["data"])


class Migration(migrations.Migration):
    dependencies = [("mainapp", "0026_user_text_rules")]
    operations = [migrations.RunPython(restore_triggers, migrations.RunPython.noop)]
