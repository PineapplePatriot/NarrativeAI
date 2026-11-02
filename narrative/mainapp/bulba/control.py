"""
Who writes the user's character: "dont" (the AI never does), "write" (it writes them too) or "director" (the user
directs the story from outside it). The wording is Pura's tested blocks (data/library/pura-director-16.json).

Our starters say "don't write for {{user}}" in their Roleplay or Style text; "write" and "director" take those
lines out and add a "Your character" block. Realistic Frankenstein keeps that rule in its anti-echo block; its
authors' advice for an AI that writes the user is to switch that off and Embellish Mode on.
"""
import copy
import re

from mainapp import presets
from mainapp.bulba import library

MODES = {"dont": "The AI never writes for you", "write": "The AI writes your character too",
         "director": "You direct the story from outside it"}
PURA = {"dont": "Don’t Write for User", "write": "Write for User", "director": "User Is Not A Character"}
BLOCK = "Your character"
# Our starters' lines that keep the AI off the user's character
STARTER_LINE = re.compile(r"^.*(\{\{user\}\}.*(belong to the player|Never write or decide them|own character: write "
                          r"their actions)|Never speak for \{\{user\}\}).*$\n?", re.M | re.I)
RF_ANTI_ECHO, RF_EMBELLISH = "🦜 Anti-parrot and anti-echo 💬", "🧂Embellish Mode- Experimental 🧙‍♂️"


def wording(mode):
    return library.get(PURA[mode])["content"].strip()


def apply_to_preset(preset, mode):
    """A copy of the normalized preset set to this mode."""
    preset = copy.deepcopy(preset)
    preset["blocks"] = [b for b in preset["blocks"] if b["name"] != BLOCK]
    names = {b["name"]: b for b in preset["blocks"]}
    if mode != "dont":
        for b in preset["blocks"]:
            if b["kind"] == "prompt" and b["name"] in ("Roleplay", "Style"):
                b["content"] = STARTER_LINE.sub("", b["content"])
        if RF_ANTI_ECHO in names:
            names[RF_ANTI_ECHO]["enabled"] = False
            if RF_EMBELLISH in names and mode == "write":
                names[RF_EMBELLISH]["enabled"] = True
    elif RF_ANTI_ECHO in names:
        names[RF_ANTI_ECHO]["enabled"] = True
        if RF_EMBELLISH in names:
            names[RF_EMBELLISH]["enabled"] = False
    starter_has_rule = any(b["kind"] == "prompt" and STARTER_LINE.search(b["content"]) for b in preset["blocks"])
    if mode != "dont" or not (starter_has_rule or RF_ANTI_ECHO in names):
        block = presets.normalize_block({"name": BLOCK, "kind": "prompt", "content": wording(mode)})
        idx = next((i + 1 for i, b in enumerate(preset["blocks"]) if b["name"] in ("Style", "Roleplay")), 1)
        preset["blocks"].insert(idx, block)
    return preset


def mode_of(preset):
    """Which mode a preset is in, as far as we can tell."""
    block = next((b for b in preset["blocks"] if b["name"] == BLOCK and b["enabled"]), None)
    if block:
        for mode in ("write", "director", "dont"):
            if block["content"].strip() == wording(mode):
                return mode
    return "dont"


# ---------------------------------------------------------------------------
# "Write for me" (impersonation): the preset is written for {{char}}'s replies, so for that one message its
# rules that keep the AI off {{user}} come out, and a short frame on top says whose message this is
# ---------------------------------------------------------------------------

# Any line telling the AI not to write, speak, act or decide for {{user}} (our starters' and common community wording)
AGENCY_LINE = re.compile(
    r"^.*(\{\{user\}\}|the user|the player)[^\n]*\b(never|don.t|do not|avoid|must not|not allowed)\b[^\n]*"
    r"\b(speak|write|act|decide|narrate|control|describe|dialogue|thoughts|actions|feelings)\b.*$\n?"
    r"|^.*\b(never|don.t|do not|avoid|must not)\b[^\n]*\b(speak|writ|act|decid|narrat|control|describ)\w*\b[^\n]*"
    r"(for |as |on behalf of )?(\{\{user\}\}|the user|the player).*$\n?", re.M | re.I)
REMINDER = "Reply reminder"  # the in-chat "reply as {{char}}" nudge right before the reply (bulba/doctor.py)
IMPERSONATE_TOP = (
    "[This turn is different. You are writing {{user}}'s next message, as {{user}}, the player's own character, "
    "not as {{char}}. The instructions below were written for {{char}}'s replies: follow their language, style "
    "and the story so far, but this one message belongs to {{user}}: their words, actions and thoughts, in the "
    "voice of {{user}}'s earlier messages. Don't write {{char}}'s or anyone else's reactions, and don't decide "
    "what happens next.]")


def for_impersonation(preset):
    """A copy of the normalized preset for writing {{user}}'s message: their-agency rules and the Your character
    block out, the reply-as-{{char}} reminder off, the frame on top. Blocks made for impersonation stay."""
    preset = copy.deepcopy(preset)
    keep = []
    for b in preset["blocks"]:
        if b["name"] == BLOCK or (b["name"] == REMINDER and b["position"] == "in_chat") or b["name"] == RF_ANTI_ECHO:
            continue
        if b["kind"] == "prompt" and "impersonate" not in (b.get("triggers") or []):
            b["content"] = AGENCY_LINE.sub("", b["content"])
        keep.append(b)
    top = presets.normalize_block({"name": "Writing for you", "kind": "prompt", "content": IMPERSONATE_TOP,
                                   "order": -10000})
    preset["blocks"] = [top] + keep
    return preset


# ---------------------------------------------------------------------------
# Director mode, per message: every direction carries what it means (Pura's block alone made models leave
# {{user}}'s own character out of the scene: "never treat {{user}} as a character")
# ---------------------------------------------------------------------------

DIRECTION_HEAD = "[Direction from the director, outside the story; not {user}'s words in it:]"
DIRECTION_TAIL = (
    "[Write the scene this asks for, as its narrator. Everyone in the scene acts and speaks in your reply, {user} "
    "included whenever the scene puts them there: as a character, {user} is yours to write (dialogue, actions, "
    "thoughts) like anyone else. Don't wait for the director to act for {user}, don't end on a question to them, "
    "and never address the director.]")
EARLIER = "[Direction] "


def frame_direction(text, user):
    return f"{DIRECTION_HEAD.format(user=user)}\n{text}\n\n{DIRECTION_TAIL.format(user=user)}"


def frame_directions(history, names):
    """Director mode: the newest message from them gets the full frame, earlier ones a short tag (the request
    only; saved messages stay as they wrote them)."""
    out = [dict(m) for m in history]
    users = [i for i, m in enumerate(out) if m.get("role") == "user" and isinstance(m.get("content"), str)]
    for i in users:
        if i == len(out) - 1:
            out[i]["content"] = frame_direction(out[i]["content"], names.get("user") or "the user")
        elif not out[i]["content"].startswith(EARLIER):
            out[i]["content"] = EARLIER + out[i]["content"]
    return out


def note_tail(user):
    """Added to a director's note in director mode (a note sent on its own has no message to frame)."""
    return "\n" + DIRECTION_TAIL.format(user=user)


# ---------------------------------------------------------------------------
# In a chat: Bulba can switch it (with the layout that goes with it)
# ---------------------------------------------------------------------------

def tool_propose_control(session, args):
    from mainapp.bulba.agent import _proposal
    mode = args.get("mode")
    if mode not in MODES:
        return {"error": "mode is dont, write or director."}, []
    active = presets.get_active(session.user)
    layout = args.get("layout") if args.get("layout") in ("chat", "book") else ("book" if mode == "director" else None)
    summary = [f"{MODES[mode]} (preset “{active.name}”)", f"Wording (Pura's): {wording(mode)}"]
    if layout:
        summary.append("Layout: " + ("book (replies as chapters, your messages fold away)" if layout == "book" else "chat bubbles"))
    summary += ["Why:", str(args.get("why") or "")[:400]]
    p = _proposal(session, "control", f"Your character: {MODES[mode].lower()}", summary,
                  {"preset_id": active.id, "mode": mode, "layout": layout})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def apply(session, p):
    from mainapp.models import Preset
    from mainapp.views import _appearance, set_layout
    data = p["payload"]
    obj = Preset.objects.filter(user=session.user, id=data["preset_id"]).first()
    if obj is None:
        raise ValueError("That preset is gone.")
    p["undo"] = {"preset_id": obj.id, "data": copy.deepcopy(obj.data), "layout": _appearance(session.user)["layout"]}
    obj.data = apply_to_preset(presets.normalize(obj.data), data["mode"])
    obj.save(update_fields=["data", "time_update"])
    if data.get("layout"):
        set_layout(session.user, data["layout"])
    return f"{MODES[data['mode']]} now. The next reply uses it."


def undo(session, p):
    from mainapp.models import Preset
    from mainapp.views import set_layout
    before = p.get("undo") or {}
    Preset.objects.filter(user=session.user, id=before.get("preset_id")).update(data=before.get("data"))
    if before.get("layout"):
        set_layout(session.user, before["layout"])


def tool_defs(fn, STR):
    return [fn("propose_control", "Switch who writes their character: dont (the AI never writes for them), write (it "
               "writes their character too) or director (they direct the story from outside it; the book layout goes "
               "with it). Uses Pura's tested wording and fixes the preset's own lines about it.",
               {"mode": {"type": "string", "enum": list(MODES)},
                "layout": {"type": "string", "enum": ["chat", "book"], "description": "Optional; director defaults to book"},
                "why": STR}, ["mode", "why"])]


HANDLERS = {"propose_control": tool_propose_control}
