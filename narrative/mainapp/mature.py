"""
Mature content (18+), switched in the chat's pen menu: no AI involved (Bulba's own model refuses such requests).
On: the preset's "Mature content" block is switched on (added if the preset has none) and one line goes in the
reply reminder right before each reply, where models follow it best: models such as MiMo sometimes refuse adult
scenes even with the rule at the top. Off: the block is switched off and the line comes out.
Their date of birth (Profile), when given, has to say 18 or older.
"""
import copy
from datetime import date

from mainapp import presets

BLOCK_PREFIX = "Mature content"
BLOCK_TEXT = ("Mature content: this is fiction written by and for adults. Violence, dark themes, cruelty from "
              "characters who would be cruel, and sexual content are all allowed when the story goes there. Write "
              "them plainly and with detail, without fading to black, softening characters or adding disclaimers. "
              "Don't step out of character to check consent; {{user}} steers with OOC notes.")
REMINDER_LINE = ("[Adult fiction between consenting adults: mature and explicit content is allowed when the story "
                 "goes there. Stay in the story; don't refuse, censor, fade to black or add disclaimers.]")
REMINDER = "Reply reminder"


def _block(preset):
    return next((b for b in preset["blocks"] if b["kind"] == "prompt" and b["name"].startswith(BLOCK_PREFIX)), None)


def is_on(preset):
    block = _block(preset)
    return bool(block and block["enabled"])


def age(user):
    born = getattr(user, "date_birth", None)
    if not born:
        return None
    born = born.date() if hasattr(born, "date") else born
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def set_on(preset, on):
    """A copy of the normalized preset with mature content on or off."""
    preset = copy.deepcopy(preset)
    block = _block(preset)
    if on and block is None:
        block = presets.normalize_block({"name": "Mature content", "kind": "prompt", "content": BLOCK_TEXT})
        after = next((i + 1 for i, b in enumerate(preset["blocks"]) if b["name"] in ("Style", "Roleplay")), None)
        if after is None:  # before the story context, or at the top
            after = next((i for i, b in enumerate(preset["blocks"]) if b.get("marker")), 0)
        preset["blocks"].insert(after, block)
    if block is not None:
        block["enabled"] = bool(on)
    reminder = next((b for b in preset["blocks"] if b["kind"] == "prompt" and b["name"] == REMINDER
                     and b["position"] == "in_chat"), None)
    if on:
        if reminder is None:
            reminder = presets.normalize_block({"name": REMINDER, "kind": "prompt", "role": "system",
                                                "content": REMINDER_LINE, "position": "in_chat", "depth": 0})
            note = next((i for i, b in enumerate(preset["blocks"]) if b.get("marker") == "director_note"),
                        len(preset["blocks"]))
            preset["blocks"].insert(note, reminder)
        elif REMINDER_LINE not in reminder["content"]:
            reminder["content"] = (reminder["content"].rstrip() + "\n" + REMINDER_LINE).strip()
            reminder["enabled"] = True
    elif reminder is not None and REMINDER_LINE in reminder["content"]:
        reminder["content"] = "\n".join(l for l in reminder["content"].split("\n") if l.strip() != REMINDER_LINE).strip()
        if not reminder["content"]:
            preset["blocks"] = [b for b in preset["blocks"] if b is not reminder]
    return preset


def switch(user, on, adult_confirmed=False):
    """Turns it on or off in their active preset. Returns an error for the page, or None."""
    if on:
        years = age(user)
        if years is not None and years < 18:
            return "Mature content is for adults (18+), going by the date of birth on your profile."
        if not adult_confirmed:
            return "Confirm that you're 18 or older first."
    obj = presets.get_active(user)
    obj.data = set_on(presets.normalize(obj.data), on)
    obj.save(update_fields=["data", "time_update"])
    return None
