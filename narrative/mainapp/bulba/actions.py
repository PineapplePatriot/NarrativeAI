"""Apply and Undo for Bulba's proposals. Nothing Bulba suggests changes anything until the user applies it."""
from django.utils.text import slugify

from mainapp import presets, starters


class ProposalError(Exception):
    pass


def _find(session, pid):
    p = next((p for p in session.proposals if p["id"] == pid), None)
    if p is None:
        raise ProposalError("No such proposal.")
    return p


def _unique_slug(user, name):
    from mainapp.models import Character
    base = f"{slugify(user.username)}-{slugify(name) or 'character'}"[:240]
    slug, n = base, 2
    while Character.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def apply(session, pid):
    """Carries out a pending proposal. Returns a short note for the page."""
    from users.views import _extras_state, apply_extras
    from mainapp.models import Character, Preset
    p = _find(session, pid)
    if p["status"] != "pending":
        raise ProposalError("This proposal was already handled.")
    user, data = session.user, p["payload"]

    if p["kind"] == "extras":
        before = _extras_state(user)
        error = apply_extras(user, data)
        if error:
            raise ProposalError(error)
        p["undo"] = {"summary": before["summary"], "trackers": before["trackers"],
                     "sprites": before["sprites"], "background": before["background"], "game": before["game"],
                     "story_extras": before["story_extras"]}
        note = "Extras saved."
    elif p["kind"] == "preset":
        from mainapp.bulba.agent import build_preset
        previous = presets.get_active(user)
        obj = starters.apply(user, data["starter"])
        preset = build_preset(data)
        extras = presets.normalize(obj.data)["extras"]  # keeps the starter's credit
        obj.data = {**preset, "extras": {**extras, "bulba": {"session": session.id}}}
        obj.name = presets.unique_name(user, data.get("name") or obj.name, exclude_id=obj.id)
        obj.save()
        p["undo"] = {"created": obj.id, "previous": previous.id}
        note = f"“{obj.name}” is now your active preset."
        if data.get("control") == "director":  # directing reads best as a book: replies as chapters
            from mainapp.views import _appearance, set_layout
            p["undo"]["layout"] = _appearance(user)["layout"]
            set_layout(user, "book")
            note += " Chats now read as a book (Book/Chat switch in the pen menu)."
    elif p["kind"] == "persona":
        p["undo"] = {"name": user.persona_name, "description": user.persona_description}
        user.persona_name, user.persona_description = data["name"], data["description"]
        user.save(update_fields=["persona_name", "persona_description"])
        note = "Your persona is saved."
    elif p["kind"] == "character":
        character = Character.objects.create(
            name=data["name"], slug=_unique_slug(user, data["name"]), author=user,
            description=data.get("description", ""), scenario=data.get("scenario", ""),
            initial_message=data.get("greeting", ""), personality=data.get("personality", ""),
            example_dialogue=data.get("example_dialogue", ""))
        p["undo"] = {"created": character.id}
        p["result"] = {"slug": character.slug}
        note = f"{character.name} is ready to chat."
    elif p["kind"] == "lore_edit":
        from mainapp.bulba import lore
        try:
            note = lore.apply_lore_edit(session, p)
        except ValueError as e:
            raise ProposalError(str(e))
    elif p["kind"] == "control":
        from mainapp.bulba import control
        try:
            note = control.apply(session, p)
        except ValueError as e:
            raise ProposalError(str(e))
    elif p["kind"] == "lorebook":
        from mainapp.bulba import lore
        try:
            note = lore.apply(session, p)
        except ValueError as e:
            raise ProposalError(str(e))
    elif p["kind"] in ("preset_edit", "card_edit"):  # from Bulba inside a chat
        from mainapp.bulba import doctor
        try:
            note = doctor.apply(session, p)
        except ValueError as e:
            raise ProposalError(str(e))
    else:
        raise ProposalError("Unknown proposal.")
    p["status"] = "applied"
    return note


def undo(session, pid):
    """Reverses an applied proposal."""
    from users.views import apply_extras
    from mainapp.models import Character, Preset
    from mainapp import chats
    p = _find(session, pid)
    if p["status"] != "applied":
        raise ProposalError("Only applied proposals can be undone.")
    user, before = session.user, p.get("undo") or {}

    if p["kind"] == "extras":
        apply_extras(user, before)
    elif p["kind"] == "preset":
        Preset.objects.filter(user=user, id=before.get("created")).delete()
        previous = Preset.objects.filter(user=user, id=before.get("previous")).first() or Preset.objects.filter(user=user).first()
        if previous:
            presets.activate(previous)
        if before.get("layout"):
            from mainapp.views import set_layout
            set_layout(user, before["layout"])
    elif p["kind"] == "persona":
        user.persona_name, user.persona_description = before.get("name"), before.get("description")
        user.save(update_fields=["persona_name", "persona_description"])
    elif p["kind"] == "character":
        character = Character.objects.filter(author=user, id=before.get("created")).first()
        if character:
            for chat in character.chats.all():
                chats.delete(chat)
            character.delete()
        if before.get("worldbook"):  # an imported card's own lore goes with it
            from mainapp.models import Worldbook
            Worldbook.objects.filter(author=user, id=before["worldbook"], characters__isnull=True).delete()
    elif p["kind"] in ("lorebook", "lore_edit"):
        from mainapp.bulba import lore
        lore.undo(session, p)
    elif p["kind"] == "control":
        from mainapp.bulba import control
        control.undo(session, p)
    elif p["kind"] in ("preset_edit", "card_edit"):
        from mainapp.bulba import doctor
        doctor.undo(session, p)
    p["status"] = "undone"
    return "Undone."


def dismiss(session, pid):
    p = _find(session, pid)
    if p["status"] != "pending":
        raise ProposalError("This proposal was already handled.")
    p["status"] = "dismissed"
    return "Dismissed."
