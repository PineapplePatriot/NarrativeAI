"""
🥔📱 Bulba inside the messenger (the Screen Hub's TeleChat): one conversation per messenger chat
(BulbaSession.mode "texting", BulbaSession.thread), opened from the chat's header.

Bulba reads the chat (read_texting_chat) and changes things only through cards they Apply (Undo puts it back):
- propose_texting_profile: a character's texting profile (how they met, who they are here, how they text, bio,
  look notes, voice...). Never the roleplay card.
- propose_texting_chat: this chat's own scenario and its scheduled events.
- propose_texting_look: draw them again for this setup (an outfit note): it costs pictures, so it's a card.
- retry_texting_reply: the characters' last reply written again, with a note (costs one reply).
"""
import copy

from mainapp.bulba import agent as agent_mod

PROFILE_FIELDS = {
    "scenario": "Why the two of them text and how they met: the situation the chat starts from",
    "modern_persona": "Who the character is in this setup: job, daily life, temperament, how they treat the user",
    "texting_style": "How they text: rhythm, capitalisation, punctuation, emoji, bubble length",
    "bio": "Their messenger bio (up to 140 characters, in their voice)",
    "handle": "@handle",
    "display_name": "The name shown in the chat",
    "status_emoji": "One emoji by their name",
    "appearance_notes": "How they look in this setup (face, hair, build, clothes): every photo reads it",
    "art_style_notes": "The picture style kept across their photos",
    "first_text": "The first text they send in a new chat",
    "voice_id": "Their voice (a premade name like sarah or george, or an ElevenLabs voice id)",
    "mode": "modern_au (today's world) or canon (their own world)",
}

INSTRUCTIONS = """# You are Bulba, inside the messenger

They are texting with their characters in NarrativeAI's messenger (the Screen Hub's TeleChat): short phone
messages, voice notes, photos. You help with this one chat. You are the same Bulba as everywhere in the app:
warm, brief, a little potato-dry. Answer in the language they write to you in.

## The rule above all
What they tell you about the setup is a decision they already made. How they met, where, who they are to each
other, jobs, ages, places, clothes: copy it exactly into the profile, in their words where you can. Never
"adapt" it, never swap in the original roleplay story, never invent different circumstances. Fill in only what
they left open, and say what you filled in. When something they want is unclear, ask one short question first.

## How to work
1. read_texting_chat first: the characters' texting profiles, this chat's scenario and events, their own
   profile, and the recent messages. Read it again after a change was applied.
2. Then one change per card: propose_texting_profile (a character's texting profile), propose_texting_chat
   (this chat's scenario override and events), propose_texting_look (new pictures, a card because it costs),
   retry_texting_reply (their last reply again, with a note). In the card's `why`, say in one line what changes.
3. Look and lore: the texting profile may differ from the roleplay card (a modern Dottore needn't wear the mask).
   When a change touches something central to who they are (a mask, a title, a scar, a secret), ask before you
   propose it, in one short question; then put it in appearance_notes or modern_persona as they answered.
4. When the problem is in the replies (out of character, too long, therapy-speak), look at the profile first:
   the texting style and persona are what the model reads every turn. Fix the cause, then offer a retry.
5. Who the user is in this chat (their persona for this chat only) and how far tease photos go are this
   chat's setup: change them yourself with propose_texting_chat (persona, photo_mood). Never send them to a menu.
   "Bold" photos exist only when mature content is on (photo_moods in read_texting_chat lists what's allowed).
6. After a character is modernized (mode becomes modern_au, or the modern persona changes a lot), ask about
   their look: their pictures still show the old one. Offer the choices (keep the pictures / new pictures in a
   modern outfit, with what they'd wear), then propose_texting_look if they want it.
7. Whenever you ask them something, give 2-4 likely answers with offer_choices (they can still type their own).
   Help them through the setup: what's left open (how they met, where they are now, who they are here), one
   question at a time, with choices.
8. Their roleplay card is never changed from here. The texting profile is separate and is what the messenger
   uses. If they want the roleplay card changed, tell them to open Bulba from the chat page.

## What the fields mean
{fields}

The chat's own scenario override (propose_texting_chat) is for this chat only: a group chat's situation, or
"stuck at the airport tonight". The character's `scenario` (propose_texting_profile) is the base every chat
with them starts from.
"""


def _thread(session):
    from mainapp.models import MessengerThread
    if not session.thread_id:
        return None
    return MessengerThread.objects.filter(id=session.thread_id, user=session.user).prefetch_related("characters").first()


def _character(session, name=""):
    """A character of this chat by name or handle (the only one when there's one)."""
    thread = _thread(session)
    chars = list(thread.characters.all()) if thread else []
    if not name and len(chars) == 1:
        return chars[0]
    key = str(name or "").strip().lower().lstrip("@")
    for c in chars:
        from mainapp import messenger
        prof = messenger.char_profile(c)
        if key in (c.name.lower(), c.slug.lower(), prof["handle"].lower().lstrip("@"), prof["display_name"].lower()):
            return c
    return chars[0] if chars and not name else None


def context(session):
    from mainapp import messenger
    thread = _thread(session)
    if thread is None:
        return "## This chat\n(The chat is gone.)"
    chars = [c.name for c in thread.characters.all()]
    return (f"## This chat\n{'Group chat' if thread.is_group else 'Chat'} “{thread.title}” with {', '.join(chars)}. "
            f"{len(messenger.thread_data(thread)['messages'])} messages so far. Call read_texting_chat for the details.")


def system_prompt(session):
    fields = "\n".join(f"- {k}: {v}" for k, v in PROFILE_FIELDS.items())
    pending = [f"- {p['id']} {p['kind']}: {p['title']} ({p['status']})" for p in session.proposals]
    from mainapp.bulba.doctor import DATA_DIR
    app = (DATA_DIR / "guides" / "app.md").read_text(encoding="utf-8")  # the app, page by page
    return "\n\n".join(filter(None, [
        INSTRUCTIONS.replace("{fields}", fields), app,
        context(session),
        f"## Session\nBudget: ${session.spent:.2f} of ${session.budget:.2f} spent.",
        "Proposals so far:\n" + "\n".join(pending) if pending else "",
    ]))


def opening(session):
    thread = _thread(session)
    names = ", ".join(c.name for c in thread.characters.all()) if thread else "them"
    session.events = [{"type": "bulba", "text": (
        f"Hi. I'm here for your texts with {names}. Tell me what's off, or what you want different: how you met, "
        "how they text, their look, their voice. What you tell me goes in as you say it."),
        "choices": [{"label": "Fix how we met"}, {"label": "They don't text like themselves"},
                    {"label": "Change their look"}, {"label": "Pick a better voice"}]}]
    session.messages = [{"role": "assistant", "content": session.events[0]["text"]}]
    session.stage = "texting"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def tool_read_texting_chat(session, args):
    from mainapp import messenger
    thread = _thread(session)
    if thread is None:
        return {"error": "This chat is gone."}, []
    data = messenger.thread_data(thread)
    profiles = []
    for c in thread.characters.all():
        prof = messenger.char_profile(c)
        profiles.append({"name": c.name, "set_up": messenger.is_set_up(c),
                         **{k: prof.get(k) for k in PROFILE_FIELDS},
                         "has_pictures": bool(prof.get("neutral_url")), "extra_pictures": len(prof.get("extra_refs") or []),
                         "roleplay_card_summary": (c.description or "")[:600]})
    recent = []
    for m in data["messages"][-30:]:
        who = "user" if m.get("role") == "user" else (m.get("sender_name") or m.get("sender_slug") or m.get("role"))
        bits = [m.get("text") or ""]
        if m.get("voice"):
            bits.append(f"[voice note: {(m['voice'] or {}).get('transcript', '')}]")
        if m.get("photo"):
            bits.append(f"[photo: {(m['photo'] or {}).get('caption') or (m['photo'] or {}).get('prompt') or ''}]")
        recent.append({"id": m.get("id"), "from": who, "text": " ".join(b for b in bits if b)[:600]})
    me = messenger.user_profile(session.user)
    return {"chat": {"title": thread.title, "group": thread.is_group, "scenario_override": data["scenario_override"],
                     "events": data["events"], "messages_total": len(data["messages"]),
                     "persona_in_this_chat": data["persona"] or "(none: their usual persona)",
                     "photo_mood": messenger.photo_mood(session.user, data),
                     "photo_moods": {k: v[1] for k, v in messenger.PHOTO_MOODS.items()
                                     if k != "bold" or messenger._mature_on(session.user)}},
            "characters": profiles,
            "user_profile": {k: me.get(k) for k in ("display_name", "handle", "bio", "status_emoji")},
            "recent_messages": recent}, []


def tool_propose_texting_profile(session, args):
    from mainapp import messenger
    character = _character(session, args.get("character"))
    if character is None:
        return {"error": "Name one of this chat's characters."}, []
    changes = {k: str(v) for k, v in (args.get("changes") or {}).items() if k in PROFILE_FIELDS and v is not None}
    if changes.get("mode") not in (None, "modern_au", "canon"):
        return {"error": "mode is modern_au or canon."}, []
    if not changes:
        return {"error": f"Give the changes: some of {', '.join(PROFILE_FIELDS)}."}, []
    current = messenger.char_profile(character)
    summary = []
    for k, v in changes.items():
        summary += [f"{k.replace('_', ' ').capitalize()}:", f"  before: {str(current.get(k) or '(empty)')[:300]}",
                    f"  after: {v[:600]}"]
    if args.get("why"):
        summary += ["Why:", str(args["why"])[:400]]
    p = agent_mod._proposal(session, "texting_profile", f"{character.name}'s texting profile", summary,
                            {"character_id": character.id, "changes": changes})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def tool_propose_texting_chat(session, args):
    from mainapp import messenger
    thread = _thread(session)
    if thread is None:
        return {"error": "This chat is gone."}, []
    changes = {}
    if "scenario_override" in args:
        changes["scenario_override"] = str(args.get("scenario_override") or "")[:3000]
    if isinstance(args.get("events"), list):
        changes["events"] = [{"text": str(e.get("text") if isinstance(e, dict) else e)[:300],
                              **({"when": str(e.get("when"))[:80]} if isinstance(e, dict) and e.get("when") else {})}
                             for e in args["events"]][:20]
    if isinstance(args.get("persona"), dict):
        changes["persona"] = {"name": str(args["persona"].get("name") or "").strip()[:80],
                              "description": str(args["persona"].get("description") or "").strip()[:3000]}
    if args.get("photo_mood"):
        if args["photo_mood"] not in messenger.PHOTO_MOODS:
            return {"error": f"photo_mood is one of {', '.join(messenger.PHOTO_MOODS)}."}, []
        changes["photo_mood"] = args["photo_mood"]
    if not changes:
        return {"error": "Give scenario_override, events, persona and/or photo_mood."}, []
    data = messenger.thread_data(thread)
    summary = []
    if "scenario_override" in changes:
        summary += ["This chat's scenario:", f"  before: {data['scenario_override'] or '(none: the characters’ own)'}",
                    f"  after: {changes['scenario_override'] or '(none: the characters’ own)'}"]
    if "events" in changes:
        summary += ["Events:"] + [f"  • {e['text']}" + (f" ({e['when']})" if e.get("when") else "") for e in changes["events"]]
    if "persona" in changes:
        old = data["persona"] or {}
        summary += ["Who you are in this chat:", f"  before: {old.get('name') or '(your usual persona)'}"
                    + (f" — {old['description'][:300]}" if old.get("description") else ""),
                    f"  after: {changes['persona']['name'] or '(your usual persona)'}"
                    + (f" — {changes['persona']['description'][:600]}" if changes["persona"]["description"] else "")]
    if "photo_mood" in changes:
        summary += ["Tease photos go this far:", f"  before: {messenger.PHOTO_MOODS[messenger.photo_mood(session.user, data)][0]}",
                    f"  after: {messenger.PHOTO_MOODS[changes['photo_mood']][0]}"]
    if args.get("why"):
        summary += ["Why:", str(args["why"])[:400]]
    p = agent_mod._proposal(session, "texting_chat", f"“{thread.title}”: this chat's setup", summary,
                            {"thread_id": thread.id, "changes": changes})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def tool_propose_texting_look(session, args):
    character = _character(session, args.get("character"))
    if character is None:
        return {"error": "Name one of this chat's characters."}, []
    outfit = str(args.get("outfit") or "").strip()[:600]
    summary = [f"Draw {character.name} again for this setup: a new portrait and an outfit shot (2 pictures, from "
               "the pictures they have so the face stays theirs).", *([f"Outfit: {outfit}"] if outfit else []),
               "Costs two pictures. Their roleplay card's pictures stay as they are."]
    if args.get("why"):
        summary += ["Why:", str(args["why"])[:400]]
    p = agent_mod._proposal(session, "texting_look", f"New pictures for {character.name}", summary,
                            {"character_id": character.id, "outfit": outfit})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def tool_retry_texting_reply(session, args):
    from mainapp import ai_client, messenger
    thread = _thread(session)
    if thread is None:
        return {"error": "This chat is gone."}, []
    try:
        messenger.regenerate_turn(session.user, thread, note=str(args.get("note") or ""))
    except ai_client.AIError as e:
        return {"error": str(e)}, []
    data = messenger.thread_data(thread)
    last_user = max((i for i, m in enumerate(data["messages"]) if m.get("role") == "user"), default=-1)
    new = [m.get("text") or ("[voice note]" if m.get("voice") else "[photo]" if m.get("photo") else "")
           for m in data["messages"][last_user + 1:] if m.get("role") == "assistant"]
    return {"done": True, "new_reply": new, "note": "It's in the chat now (the page refreshes)."}, [{"type": "reply"}]


def tool_defs():
    from mainapp.bulba.doctor import _fn
    STR = {"type": "string"}
    props = {k: {"type": "string", "description": v} for k, v in PROFILE_FIELDS.items()}
    return [
        _fn("read_texting_chat", "This messenger chat: its characters' texting profiles, the chat's scenario and "
            "events, their own profile, and the last 30 messages. Read it before proposing anything.", {}),
        _fn("propose_texting_profile", "Change a character's texting profile (never the roleplay card). Give only the "
            "fields that change, written in full. What the user told you goes in as they said it.",
            {"character": {"type": "string", "description": "The character's name (leave out in a 1-on-1 chat)"},
             "changes": {"type": "object", "properties": props}, "why": STR}, ("changes",)),
        _fn("propose_texting_chat", "Change this chat's own setup: its scenario override, its scheduled events (the "
            "whole list as it should be), who the user is in this chat (persona: name and description; empty = their "
            "usual persona), and/or how far tease photos go (photo_mood). Give only what changes.",
            {"scenario_override": STR,
             "events": {"type": "array", "items": {"type": "object", "properties": {"text": STR, "when": STR}}},
             "persona": {"type": "object", "properties": {"name": STR, "description": STR}},
             "photo_mood": {"type": "string", "enum": ["sweet", "playful", "flirty", "bold"]},
             "why": STR}),
        _fn("propose_texting_look", "New pictures of a character for this setup (a portrait and an outfit shot), with "
            "an outfit note. Costs two pictures, so it's a card they Apply.",
            {"character": STR, "outfit": STR, "why": STR}),
        _fn("retry_texting_reply", "Write the characters' last reply again now, with a note (what should be "
            "different). Costs one reply. Use it after a fix is applied, or when they ask for another take.",
            {"note": STR}),
    ]


def tools():
    keep = {"offer_choices", "record_preference"}
    return [t for t in agent_mod.TOOLS if t["function"]["name"] in keep] + tool_defs()


HANDLERS = {"read_texting_chat": tool_read_texting_chat, "propose_texting_profile": tool_propose_texting_profile,
            "propose_texting_chat": tool_propose_texting_chat, "propose_texting_look": tool_propose_texting_look,
            "retry_texting_reply": tool_retry_texting_reply}
TURN_ENDING = {"propose_texting_profile", "propose_texting_chat", "propose_texting_look", "retry_texting_reply"}
KINDS = ("texting_profile", "texting_chat", "texting_look")


# ---------------------------------------------------------------------------
# Apply / undo
# ---------------------------------------------------------------------------

def apply(session, p):
    from mainapp import messenger
    from mainapp.models import Character, MessengerThread
    data = p["payload"]
    if p["kind"] in ("texting_profile", "texting_look"):
        character = Character.objects.filter(author=session.user, id=data["character_id"]).first()
        if character is None:
            raise ValueError("That character is gone.")
        p["undo"] = {"character_id": character.id, "profile": copy.deepcopy(character.messenger_profile or {})}
        if p["kind"] == "texting_profile":
            messenger.save_char_profile(character, data["changes"])
            return f"{character.name}'s texting profile changed. The next text uses it."
        from mainapp import ai_client
        try:
            messenger.redraw_setup_look(session.user, character, outfit=data.get("outfit") or "")
        except ai_client.AIError as e:
            raise ValueError(str(e))
        return f"{character.name} has new pictures for texting."
    if p["kind"] == "texting_chat":
        thread = MessengerThread.objects.filter(user=session.user, id=data["thread_id"]).first()
        if thread is None:
            raise ValueError("That chat is gone.")
        raw = dict(thread.data or {})
        p["undo"] = {"thread_id": thread.id, "before": {k: raw.get(k) for k in data["changes"]}}
        raw.update(data["changes"])
        thread.data = raw
        thread.save(update_fields=["data"])
        return "This chat's setup changed. The next text uses it."
    raise ValueError("Unknown proposal.")


def undo(session, p):
    from mainapp.models import Character, MessengerThread
    before = p.get("undo") or {}
    if p["kind"] in ("texting_profile", "texting_look"):
        Character.objects.filter(author=session.user, id=before.get("character_id")).update(
            messenger_profile=before.get("profile") or {})
    elif p["kind"] == "texting_chat":
        thread = MessengerThread.objects.filter(user=session.user, id=before.get("thread_id")).first()
        if thread is not None:
            raw = dict(thread.data or {})
            for k, v in (before.get("before") or {}).items():
                if v is None:
                    raw.pop(k, None)
                else:
                    raw[k] = v
            thread.data = raw
            thread.save(update_fields=["data"])
