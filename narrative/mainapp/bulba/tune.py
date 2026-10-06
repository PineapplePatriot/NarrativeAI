"""
Bulba's fine-tuning tools: model settings (samplers), a character's trackers, alternate greetings, a card's own
text rules, lorebook settings, and making mood pictures. Each change is a proposal with Apply and Undo; making
pictures spends money, so it's a button they press, never a proposal Bulba applies.
"""
import copy

from mainapp import presets, samplers as sampler_mod, trackers as tracker_mod
from mainapp.bulba.lore import target_character

KINDS = ("samplers", "trackers", "greetings", "card_rules", "lore_settings", "voices")
LORE_SETTINGS = {"scan_depth": (1, 50), "token_budget": (200, 20000), "recursive_scan": None}
# What each tracker id means, for Bulba (the panel's own help text)
TRACKER_IDS = [t["id"] for t in tracker_mod.TRACKERS]


def _active_model(user):
    from mainapp import ai_client
    try:
        return ai_client.resolve(user, "chat")[1]
    except ai_client.NoConnection:
        return ""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def tool_read_settings(session, args):
    """The settings Bulba can tune, as they are now."""
    from mainapp import lorebook, model_profiles, regex_rules
    user = session.user
    preset = presets.get_active(user)
    current = sampler_mod.normalize(preset.data.get("samplers"))
    status = model_profiles.sampler_status(_active_model(user), current)
    out = {"preset": preset.name, "samplers": {
        k: {"on": v["on"], "value": v["value"], "label": sampler_mod.SAMPLERS_BY_KEY[k]["label"],
            "help": sampler_mod.SAMPLERS_BY_KEY[k]["help"],
            "this_model": status.get(k, {}).get("status", "unverified"),
            **({"why": status[k]["why"]} if status.get(k, {}).get("why") else {})}
        for k, v in current.items()}}
    character = target_character(session)
    if character:
        config = tracker_mod.normalize_config(character.tracker_config)
        out["character"] = character.name
        out["trackers"] = [{"id": t["id"], "label": t["label"], "help": t.get("help", ""),
                            "on": config["trackers"][t["id"]]["on"]} for t in tracker_mod.TRACKERS]
        out["custom_fields"] = config["custom_fields"]
        out["alternate_greetings"] = list(character.alternate_greetings or [])
        out["card_rules"] = [{"id": r["id"], "name": r.get("name") or r["id"], "enabled": r.get("enabled", True)}
                             for r in regex_rules.card_rules(character)]
        if character.worldbook_id:
            settings = lorebook.load_worldbook(character.worldbook).get("settings", {})
            out["lorebook_settings"] = {k: settings.get(k) for k in LORE_SETTINGS}
    return out, []


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------

def _propose(session, kind, title, summary, payload, why):
    from mainapp.bulba.agent import _proposal
    p = _proposal(session, kind, title, summary + ["Why:", str(why or "")[:300]], payload)
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def tool_propose_samplers(session, args):
    preset = presets.get_active(session.user)
    current = sampler_mod.normalize(preset.data.get("samplers"))
    changes, summary = {}, []
    for c in (args.get("changes") or [])[:8]:
        key = c.get("key") if isinstance(c, dict) else None
        spec = sampler_mod.SAMPLERS_BY_KEY.get(key)
        if spec is None:
            return {"error": f"No setting called “{key}”.", "settings": list(sampler_mod.SAMPLERS_BY_KEY)}, []
        on = bool(c.get("on", True))
        value = sampler_mod._coerce(spec, c.get("value", current[key]["value"]))
        changes[key] = {"on": on, "value": value}
        summary.append(f"{spec['label']}: {value if on else 'off (the model decides)'}"
                       + (f" (was {current[key]['value'] if current[key]['on'] else 'off'})"))
    if not changes:
        return {"error": "No changes given."}, []
    return _propose(session, "samplers", f"Model settings in “{preset.name}”", summary,
                    {"preset_id": preset.id, "changes": changes}, args.get("why"))


def tool_propose_trackers(session, args):
    character = target_character(session)
    if character is None:
        return {"error": "No character yet."}, []
    turn_on = [t for t in args.get("turn_on") or [] if t in TRACKER_IDS]
    turn_off = [t for t in args.get("turn_off") or [] if t in TRACKER_IDS]
    fields = tracker_mod.normalize_custom_fields(args.get("custom_fields")) if args.get("custom_fields") is not None else None
    if not (turn_on or turn_off or fields is not None):
        return {"error": "Nothing to change.", "trackers": TRACKER_IDS}, []
    labels = {t["id"]: t["label"] for t in tracker_mod.TRACKERS}
    summary = ([f"On: {', '.join(labels[t] for t in turn_on)}"] if turn_on else []) + \
              ([f"Off: {', '.join(labels[t] for t in turn_off)}"] if turn_off else [])
    if fields is not None:
        summary.append("Custom tracker: " + (", ".join(f"{f['label']} ({f['type']})" for f in fields) or "none"))
        if fields and "custom" not in turn_on:
            turn_on.append("custom")
    return _propose(session, "trackers", f"Trackers for {character.name}", summary,
                    {"character_id": character.id, "on": turn_on, "off": turn_off, "custom_fields": fields},
                    args.get("why"))


def tool_propose_greetings(session, args):
    character = target_character(session)
    if character is None:
        return {"error": "No character yet."}, []
    greetings = [str(g).strip()[:20000] for g in (args.get("greetings") or []) if str(g).strip()][:12]
    summary = [f"{len(greetings)} alternate greeting(s); a new chat can swipe between them and the first message."]
    summary += [f"{i + 1}. {g[:300]}{'…' if len(g) > 300 else ''}" for i, g in enumerate(greetings)]
    return _propose(session, "greetings", f"Alternate greetings for {character.name}", summary,
                    {"character_id": character.id, "greetings": greetings}, args.get("why"))


def tool_propose_card_rules(session, args):
    from mainapp import regex_rules
    character = target_character(session)
    if character is None:
        return {"error": "No character yet."}, []
    rules = {r["id"]: r for r in regex_rules.card_rules(character)}
    switches = {}
    for s in (args.get("rules") or [])[:30]:
        if isinstance(s, dict) and str(s.get("id")) in rules:
            switches[str(s["id"])] = bool(s.get("enabled"))
    if not switches:
        return {"error": "No known rule ids.", "rules": [{"id": k, "name": r.get("name")} for k, r in rules.items()]}, []
    summary = [f"{rules[k].get('name') or k}: {'on' if v else 'off'}" for k, v in switches.items()]
    return _propose(session, "card_rules", f"{character.name}'s text rules", summary,
                    {"character_id": character.id, "switches": switches}, args.get("why"))


def tool_propose_lore_settings(session, args):
    character = target_character(session)
    if character is None or not character.worldbook_id:
        return {"error": "This character has no lorebook."}, []
    settings, summary = {}, []
    for key, bounds in LORE_SETTINGS.items():
        if key not in args:
            continue
        if bounds is None:
            settings[key] = bool(args[key])
        else:
            try:
                settings[key] = max(bounds[0], min(bounds[1], int(args[key])))
            except (TypeError, ValueError):
                return {"error": f"{key} must be a number."}, []
        summary.append(f"{key.replace('_', ' ')}: {settings[key]}")
    if not settings:
        return {"error": "Nothing to change."}, []
    return _propose(session, "lore_settings", f"Lorebook settings: {character.worldbook.title}", summary,
                    {"worldbook_id": character.worldbook_id, "settings": settings}, args.get("why"))


def _eleven(session):
    from mainapp import voice
    from mainapp.utils import get_elevenlabs_key
    key = get_elevenlabs_key(session.user)
    if not key:
        raise voice.VoiceError("No ElevenLabs key: they add one on the Extras page (/users/extras/), never in this chat.")
    return voice.list_voices(key)


def tool_read_voices(session, args):
    """Their ElevenLabs voices (names and labels; the key never leaves the server) and who has which now."""
    from mainapp import voice
    try:
        voices = _eleven(session)
    except voice.VoiceError as e:
        return {"error": str(e)}, []
    character = target_character(session)
    names = {v["id"]: v["name"] for v in voices}
    out = {"voices": [{k: v[k] for k in ("name", "gender", "age", "accent", "description", "use") if v.get(k)}
                      for v in voices][:120]}
    if character:
        out["character"] = character.name
        out["now"] = {"narrator": names.get(character.eleven_voice_narr_id, character.eleven_voice_narr_id or "picked automatically"),
                      character.name: names.get(character.eleven_voice_char_id, character.eleven_voice_char_id or "picked automatically"),
                      **{n: names.get(v, v) for n, v in (character.voice_cast or {}).items()}}
    return out, []


def tool_propose_voices(session, args):
    from mainapp import voice
    character = target_character(session)
    if character is None:
        return {"error": "No character yet."}, []
    try:
        voices = _eleven(session)
    except voice.VoiceError as e:
        return {"error": str(e)}, []
    by_name = {v["name"].lower(): v for v in voices}

    def find(name):
        v = by_name.get(str(name or "").strip().lower())
        if v is None:
            raise KeyError(name)
        return v

    payload, summary = {"character_id": character.id}, []
    try:
        if args.get("narrator"):
            payload["narrator"] = find(args["narrator"])["id"]
            summary.append(f"Narrator: {find(args['narrator'])['name']}")
        if args.get("character"):
            payload["character"] = find(args["character"])["id"]
            summary.append(f"{character.name}: {find(args['character'])['name']}")
        cast = {}
        for item in (args.get("cast") or [])[:12]:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                cast[str(item["name"]).strip()[:60]] = find(item.get("voice"))["id"]
                summary.append(f"{item['name']}: {find(item.get('voice'))['name']}")
        if cast:
            payload["cast"] = cast
    except KeyError as e:
        return {"error": f"No voice called “{e.args[0]}” in their ElevenLabs list (read_voices)."}, []
    if len(payload) == 1:
        return {"error": "Nothing to change."}, []
    summary.append("Anyone else gets a voice picked automatically, kept for the chat.")
    return _propose(session, "voices", f"Voices for {character.name}", summary, payload, args.get("why"))


def tool_offer_mood_pictures(session, args):
    """A button that makes the missing mood pictures from the neutral one (on their key; they press it)."""
    from django.urls import reverse
    from mainapp.views import SPRITE_EMOTIONS
    character = target_character(session)
    if character is None:
        return {"error": "No character yet."}, []
    if not character.photo_neutral:
        return {"error": "No neutral picture yet: they add one first (📎 here, or the character's page)."}, []
    missing = [m for m in SPRITE_EMOTIONS if not getattr(character, f"photo_{m}")]
    if args.get("redo"):
        missing = list(SPRITE_EMOTIONS)
    if not missing:
        return {"status": "All mood pictures are there already; pass redo to make them again."}, []
    return {"shown": missing, "note": "They press the button; each picture costs a few cents on their key."}, [
        {"type": "make_pictures", "url": reverse("character_sprite", args=[character.slug]),
         "name": character.name, "moods": missing}]


# ---------------------------------------------------------------------------
# Apply / undo
# ---------------------------------------------------------------------------

def _character(session, cid):
    from mainapp.models import Character
    character = Character.objects.filter(author=session.user, id=cid).first()
    if character is None:
        raise ValueError("That character is gone.")
    return character


def apply(session, p):
    from mainapp import lorebook, regex_rules
    from mainapp.models import Preset, Worldbook
    data, kind = p["payload"], p["kind"]
    if kind == "samplers":
        preset = Preset.objects.filter(user=session.user, id=data["preset_id"]).first()
        if preset is None:
            raise ValueError("That preset is gone.")
        p["undo"] = {"preset_id": preset.id, "samplers": copy.deepcopy(preset.data.get("samplers"))}
        current = sampler_mod.normalize(preset.data.get("samplers"))
        current.update(data["changes"])
        preset.data = {**preset.data, "samplers": current}
        preset.save(update_fields=["data", "time_update"])
        return f"“{preset.name}” uses the new settings from the next reply."
    character = None if kind == "lore_settings" else _character(session, data["character_id"])
    if kind == "trackers":
        p["undo"] = {"character_id": character.id, "config": copy.deepcopy(character.tracker_config)}
        config = dict(character.tracker_config or {})
        items = {k: dict(v) for k, v in (config.get("trackers") or {}).items() if isinstance(v, dict)}
        for tid in data["on"]:
            items[tid] = {**items.get(tid, {}), "on": True}
        for tid in data["off"]:
            items[tid] = {**items.get(tid, {}), "on": False}
        config["trackers"] = items
        if data.get("custom_fields") is not None:
            config["custom_fields"] = data["custom_fields"]
        character.tracker_config = config
        character.save(update_fields=["tracker_config"])
        return f"{character.name}'s trackers are updated; they fill in over the next replies."
    if kind == "greetings":
        p["undo"] = {"character_id": character.id, "greetings": list(character.alternate_greetings or [])}
        character.alternate_greetings = data["greetings"]
        character.save(update_fields=["alternate_greetings"])
        return f"{character.name} has {len(data['greetings'])} alternate greeting(s) for new chats."
    if kind == "card_rules":
        p["undo"] = {"character_id": character.id, "card_data": copy.deepcopy(character.card_data)}
        for rule_id, enabled in data["switches"].items():
            try:
                regex_rules.set_card_rule(character, rule_id, enabled)
            except KeyError:
                pass
        return f"{character.name}'s text rules are switched."
    if kind == "voices":
        p["undo"] = {"character_id": character.id, "narrator": character.eleven_voice_narr_id,
                     "character": character.eleven_voice_char_id, "cast": dict(character.voice_cast or {})}
        if data.get("narrator"):
            character.eleven_voice_narr_id = data["narrator"]
        if data.get("character"):
            character.eleven_voice_char_id = data["character"]
        if data.get("cast"):
            character.voice_cast = {**(character.voice_cast or {}), **data["cast"]}
        character.save(update_fields=["eleven_voice_narr_id", "eleven_voice_char_id", "voice_cast"])
        return f"{character.name}'s voices are set. Press 🔊 on a reply to hear them."
    if kind == "lore_settings":
        wb = Worldbook.objects.filter(author=session.user, id=data["worldbook_id"]).first()
        if wb is None:
            raise ValueError("That lorebook is gone.")
        book = lorebook.load_worldbook(wb)
        p["undo"] = {"worldbook_id": wb.id, "settings": copy.deepcopy(book.get("settings"))}
        book["settings"] = {**(book.get("settings") or {}), **data["settings"]}
        lorebook.save_worldbook(wb, book)
        return f"“{wb.title}” uses the new settings from the next reply."
    raise ValueError("Unknown proposal.")


def undo(session, p):
    from mainapp import lorebook
    from mainapp.models import Character, Preset, Worldbook
    before, kind = p.get("undo") or {}, p["kind"]
    if kind == "samplers":
        preset = Preset.objects.filter(user=session.user, id=before.get("preset_id")).first()
        if preset:
            preset.data = {**preset.data, "samplers": before.get("samplers")}
            preset.save(update_fields=["data", "time_update"])
        return
    if kind == "lore_settings":
        wb = Worldbook.objects.filter(author=session.user, id=before.get("worldbook_id")).first()
        if wb:
            book = lorebook.load_worldbook(wb)
            book["settings"] = before.get("settings") or {}
            lorebook.save_worldbook(wb, book)
        return
    character = Character.objects.filter(author=session.user, id=before.get("character_id")).first()
    if character is None:
        return
    if kind == "trackers":
        character.tracker_config = before.get("config") or {}
        character.save(update_fields=["tracker_config"])
    elif kind == "greetings":
        character.alternate_greetings = before.get("greetings") or []
        character.save(update_fields=["alternate_greetings"])
    elif kind == "card_rules":
        character.card_data = before.get("card_data") or {}
        character.save(update_fields=["card_data"])
    elif kind == "voices":
        character.eleven_voice_narr_id = before.get("narrator") or ""
        character.eleven_voice_char_id = before.get("character") or ""
        character.voice_cast = before.get("cast") or {}
        character.save(update_fields=["eleven_voice_narr_id", "eleven_voice_char_id", "voice_cast"])


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def tool_defs(fn, STR):
    return [
        fn("read_settings", "The settings you can tune, as they are now: model settings of the active preset (and "
           "which ones this model ignores), the character's trackers, custom tracker fields, alternate greetings, "
           "the card's own text rules and lorebook settings. Read before proposing any of these.", {}),
        fn("propose_samplers", "Change model settings in the active preset: reply length (max_tokens), temperature, "
           "top_p, min_p, penalties, reasoning_effort and the rest (read_settings has the list). Only ones this model "
           "uses; one or two at a time.",
           {"changes": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
               "key": STR, "on": {"type": "boolean", "description": "false: not sent, the model decides"},
               "value": {"description": "number, text or list, as read_settings shows"}}, "required": ["key"]}},
            "why": STR}, ["changes", "why"]),
        fn("propose_trackers", "Switch the character's story trackers on or off, and/or set the custom tracker's "
           "fields (meters, text, lists). Pick what the story needs, not everything.",
           {"turn_on": {"type": "array", "items": {"type": "string", "enum": TRACKER_IDS}},
            "turn_off": {"type": "array", "items": {"type": "string", "enum": TRACKER_IDS}},
            "custom_fields": {"type": "array", "maxItems": 12, "items": {"type": "object", "properties": {
                "label": STR, "type": {"type": "string", "enum": list(tracker_mod.FIELD_TYPES)},
                "hint": {"type": "string", "description": "What the tracker AI should note"},
                "min": {"type": "number"}, "max": {"type": "number"}}, "required": ["label"]},
                "description": "The full new list (replaces the old one); [] removes them"},
            "why": STR}, ["why"]),
        fn("propose_greetings", "Set the character's alternate greetings (other first messages a new chat can "
           "swipe to). Give the full new list; keep the ones they like word for word.",
           {"greetings": {"type": "array", "maxItems": 12, "items": STR}, "why": STR}, ["greetings", "why"]),
        fn("propose_card_rules", "Switch the card's own text rules (regex scripts that came with it) on or off.",
           {"rules": {"type": "array", "items": {"type": "object", "properties": {
               "id": STR, "enabled": {"type": "boolean"}}, "required": ["id", "enabled"]}}, "why": STR},
           ["rules", "why"]),
        fn("propose_lore_settings", "Change how the character's lorebook is searched: scan_depth (how many recent "
           "messages are checked for keys), token_budget (most lore added per reply), recursive_scan (entries can "
           "trigger other entries).",
           {"scan_depth": {"type": "integer"}, "token_budget": {"type": "integer"},
            "recursive_scan": {"type": "boolean"}, "why": STR}, ["why"]),
        fn("read_voices", "Their ElevenLabs voices (name, gender, age, accent, description) and who has which voice "
           "now. Only when they have an ElevenLabs key.", {}),
        fn("propose_voices", "Give the narrator, the character and other people in the story (Pantalone, a sister) "
           "voices from their list, by the voice's name. Match age, gender, accent and temperament to the card; the "
           "narrator should be calm and clear. Anyone not given one gets a voice picked automatically.",
           {"narrator": STR, "character": STR,
            "cast": {"type": "array", "maxItems": 12, "items": {"type": "object", "properties": {
                "name": {"type": "string", "description": "As the story says it"}, "voice": STR},
                "required": ["name", "voice"]}},
            "why": STR}, ["why"]),
        fn("offer_mood_pictures", "Show a button that makes the missing mood pictures from the neutral one with an "
           "image model (a few cents each, on their key). They press it; say what it costs first.",
           {"redo": {"type": "boolean", "description": "Make all eight again, not only the missing ones"}}),
    ]


HANDLERS = {"read_settings": tool_read_settings, "propose_samplers": tool_propose_samplers,
            "propose_trackers": tool_propose_trackers, "propose_greetings": tool_propose_greetings,
            "propose_card_rules": tool_propose_card_rules, "propose_lore_settings": tool_propose_lore_settings,
            "offer_mood_pictures": tool_offer_mood_pictures, "read_voices": tool_read_voices,
            "propose_voices": tool_propose_voices}
TURN_ENDING = {"propose_samplers", "propose_trackers", "propose_greetings", "propose_card_rules",
               "propose_lore_settings", "offer_mood_pictures", "propose_voices"}
