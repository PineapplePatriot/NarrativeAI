"""
python manage.py seed_demo

Creates (or refreshes) the demo account graders log into: a user, an OpenRouter connection, a starter preset and
one character to chat with. Everything secret comes from environment variables set on the host, never from code:

    DEMO_PASSWORD        the demo account's password (required)
    DEMO_OPENROUTER_KEY  the OpenRouter key the demo account uses (optional; without it they add their own)
    DEMO_USERNAME        default "demo"
    DEMO_MODEL           model profile id, default "mimo-v2-6-pro" (see mainapp/data/models/)

Safe to run on every start: it only fills in what's missing, and updates the key and password.
"""
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from mainapp import chats, model_profiles, presets, starters

ROSE = {
    "name": "Rose",
    "description": "{{char}} is an alchemist in her late twenties who runs a cluttered shop at the edge of a port "
                   "town. Sharp-tongued and impatient with fools, she is quietly kind to anyone who is honest with "
                   "her. She hates being interrupted mid-experiment, keeps a cat named Sulphur, and owes money to "
                   "the harbour guild, which she tells no one.",
    "scenario": "A stormy evening. {{user}} comes into Rose's shop to get out of the sleet, just as an experiment "
                "on the counter starts to smoke.",
    "initial_message": "*The bell over the door jangles. Rose doesn't look up from the alembic.* \"Shut the door. "
                       "And don't touch anything green.\"",
}


PACKS = Path(__file__).resolve().parents[2] / "data" / "demo"
MOODS = ["neutral", "happy", "sad", "angry", "surprised", "scared", "confused", "calm", "scheming"]


def load_packs(user):
    """Characters shipped in data/demo/<name>/, added once each:
        card.png or card.json   the character card (SillyTavern V2/V3)
        lorebook.json           optional: a lorebook (our format or SillyTavern's), attached to the character
        theme.json              optional: {"bg": url, "music": {"url", "name"}, "dialogue_color": "#rrggbb"}
        sprites/<mood>.png      optional: neutral, happy, sad, angry, surprised, scared, confused, calm, scheming
    Returns the names added."""
    import json
    from django.core.files.base import ContentFile
    from mainapp import cards, lorebook
    from mainapp.models import Character, Worldbook
    added = []
    for folder in sorted(p for p in PACKS.glob("*") if p.is_dir()) if PACKS.is_dir() else []:
        card_file = next((folder / n for n in ("card.png", "card.json") if (folder / n).exists()), None)
        if card_file is None:
            continue
        card, image = cards.read(card_file.read_bytes(), card_file.name)
        if Character.objects.filter(author=user, name=card["name"]).exists():
            continue
        character = cards.create_character(user, card, image)
        lore = folder / "lorebook.json"
        if lore.exists():
            book = lorebook.normalize_book(json.loads(lore.read_text(encoding="utf-8")))
            wb = character.worldbook or Worldbook(title=book["title"] or f"{character.name}'s world",
                                                  slug=f"{character.slug}-lore", author=user)
            if character.worldbook:  # the card brought its own lore: add ours after it
                own = lorebook.load_worldbook(wb)
                book = {**own, "entries": own["entries"] + book["entries"]}
            lorebook.save_worldbook(wb, book)
            character.worldbook = wb
        theme = folder / "theme.json"
        if theme.exists():
            character.theme = json.loads(theme.read_text(encoding="utf-8"))
        for mood in MOODS:
            for ext in ("png", "webp", "jpg"):
                sprite = folder / "sprites" / f"{mood}.{ext}"
                if sprite.exists():
                    getattr(character, f"photo_{mood}").save(f"{character.slug}-{mood}.{ext}",
                                                             ContentFile(sprite.read_bytes()), save=False)
                    break
        character.save()
        chats.current(character)
        added.append(character.name)
    return added


class Command(BaseCommand):
    help = "Create or refresh the demo account (see the module docstring for the environment variables)."

    def handle(self, *args, **options):
        from mainapp.models import Character, Preset
        from users.models import ConnectionProfile
        password = os.environ.get("DEMO_PASSWORD")
        if not password:
            raise CommandError("Set DEMO_PASSWORD first.")
        username = os.environ.get("DEMO_USERNAME", "demo")
        profile_id = os.environ.get("DEMO_MODEL", "mimo-v2-6-pro")
        profile = next((p for p in model_profiles.all_profiles() if p.get("id") == profile_id), None)
        if profile is None:
            raise CommandError(f"No model profile '{profile_id}' (see mainapp/data/models/).")
        model = ((profile or {}).get("ids") or {}).get("openrouter") or "xiaomi/mimo-v2.6-pro"

        User = get_user_model()
        user, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com"})
        user.set_password(password)
        user.save()

        key = os.environ.get("DEMO_OPENROUTER_KEY", "")
        conn, _ = ConnectionProfile.objects.get_or_create(user=user, name="Main", defaults={"model": model})
        conn.provider, conn.model = ConnectionProfile.PROVIDER_OPENROUTER, model
        if key:
            conn.api_key = key
        conn.save()

        if not Preset.objects.filter(user=user).exists():
            options = (profile or {}).get("starters") or {}
            starter = options.get("rich_scene") or next(iter(options.values()), None)
            if starter and starters.get(starter):
                starters.apply(user, starter)
            else:
                presets.get_active(user)  # the built-in default

        packs = load_packs(user)
        if not packs and not Character.objects.filter(author=user).exists():
            character = Character.objects.create(slug=f"{username}-rose", author=user, **ROSE)
            chats.current(character)

        if packs:
            self.stdout.write("Demo characters added: " + ", ".join(packs))
        self.stdout.write(f"Demo account '{username}' ready ({'created' if created else 'updated'}); "
                          f"model {model}; key {'set' if key else 'not set: they add their own'}.")
