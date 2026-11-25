"""
Casting: Bulba prepares an episode before it starts, so the things that must stay the same are fixed up front.

Bulba reads the chat (memory, recent texts, "📍 Right now", the phone's remembered places, a Pulse plan), each
person's episode looks and the recent episodes, and proposes a casting sheet: who is there, the place written out
(time, light, weather, the objects that stay put) with a backdrop to use or to draw, each person's outfit item by
item (an existing look, or a new one), the facts the episode must keep true, how it opens, and one optional
detail. Every part is a proposal the user applies, edits or turns down; nothing is drawn until they say so.

The applied sheet goes to `vn_scenes.start_scene` as `casting` and becomes fixed for the episode.
"""
import json
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from mainapp import ai_client, episode_looks, messenger, vn_scenes, vn_support
from mainapp.models import EpisodePlace

MAX_FACTS = 10


def _person(user, key, character, thread_data):
    setting = episode_looks.setting_for(character) if character else "canon"
    name = messenger.char_profile(character)["display_name"] if character else ""
    wearing = ""
    for who, row in ((thread_data or {}).get("scene") or {}).items():
        if character and who.strip().lower() in (name.lower(), character.name.lower()):
            wearing = row.get("wearing") or ""
    looks = episode_looks.looks_for(user, character, setting)
    return {"key": key, "name": name, "setting": setting, "wearing": wearing,
            "looks": [{"id": l.pk, "name": l.name, "outfit": l.outfit} for l in looks[:8]]}


def _story_data(story):
    """A story's end-of-last-scene in the phone's shape: who wears what."""
    last = (story.bible or {}).get("last") or {}
    return {"scene": {name: {"wearing": worn} for name, worn in (last.get("outfits") or {}).items()}, "places": {}}


def context(user, thread, chars, pulse_event=None, director=False, story=None):
    """Everything Bulba reads for the casting sheet, and what the sheet's choices are checked against."""
    if story is not None:
        from mainapp import stories
        thread, pulse_event = None, None
        data, scene = _story_data(story), stories.scene_context(user, story)
    else:
        data = messenger.thread_data(thread) if thread else {}
        scene = vn_support.scene_context(user, thread)
    people = [_person(user, c.slug, c, data) for c in chars]
    me = _person(user, "user", None, data)
    me.update(name=scene["user_name"], setting=vn_scenes.scene_setting(chars),
              looks=[{"id": l.pk, "name": l.name, "outfit": l.outfit}
                     for l in episode_looks.looks_for(user, None, vn_scenes.scene_setting(chars))[:8]])
    for who, row in (data.get("scene") or {}).items():
        if who.strip().lower() == scene["user_name"].lower():
            me["wearing"] = row.get("wearing") or ""
    backdrops = [{"id": b["id"], "name": b["name"], "kept": bool(b.get("kept"))}
                 for b in vn_scenes.available_backgrounds(chars, user)]
    recent = [{"title": g.get("title", ""), "location": g.get("location", ""), "summary": g.get("summary", "")[:240]}
              for g in (vn_scenes.get_vn_state(user).get("gallery") or [])[-4:]
              if not thread or g.get("thread_id") in (None, thread.pk)]
    if story is not None:
        recent = [{"title": s.title, "location": s.place, "summary": s.summary[:240]}
                  for s in list(story.scenes.order_by("-number")[:4])[::-1]]
    return {"story": story, "scene": scene, "people": people, "me": me, "director": director, "backdrops": backdrops,
            "phone_places": data.get("places") or {}, "recent": recent, "pulse": pulse_event or {}}


PROMPT = """You are Bulba, preparing the casting sheet for an in-person visual-novel episode that continues a texting chat.
Everything you write is shown to the user and stays fixed for the whole episode, so be exact and concrete.
Plain words only: no metaphors, no mood-writing, no adjectives that don't describe something visible.

CHAT ({user} with {names}). Story clock: {clock}
Memory: {memory}
Scenario: {scenario}
Right now (from the phone): {right_now}
Recent texts:
{conversation}
{pulse}
User's wish for this episode: {wish}

PEOPLE (key, name, setting, what the phone says they wear, their existing episode looks):
{people}

KEPT AND AVAILABLE BACKDROPS (id: name; "kept" = a place drawn for an earlier episode):
{backdrops}

PLACES THE PHONE ALREADY DESCRIBED (keep them matching): {phone_places}

RECENT EPISODES (don't repeat their openings or places without a reason):
{recent}

Return ONLY this JSON:
{{
  "cast": ["keys of the people present when the episode opens"],
  "place": {{"name": "short name of the place", "background_id": "an id from the list ONLY if that backdrop really shows this place, else ''",
            "time": "story day and time", "light": "where the light comes from and its colour", "weather": "weather, or '' indoors",
            "layout": "as seen standing in it at eye level: what is on the left, in the middle, at the back, on the right",
            "details": ["3 to 6 concrete things in this place that stay put: furniture, objects, layout"]}},
  "outfits": [{{"key": "person key", "look_id": "id of their existing look if it fits time, place and plan, else null",
               "name": "2-3 word name for the outfit", "items": "item by item: garment, colour, material; shoes; accessories",
               "why": "one short reason",
               "moods": ["4 to 7 moods this person will likely show in THIS episode, one or two words each, beyond neutral"],
               "mood_notes": {{"<mood>": "how THIS person shows it, face only: eyebrows, eyes, mouth"}}}}],
  "facts": ["4 to 8 short facts this episode must keep true: where things stand between them, promises and plans,
            who knows what and who doesn't, injuries or moods that carry over"],
  "opening": "one or two sentences: where they are and what is happening when the episode starts",
  "nudge": "one concrete detail grounded in the chat that would make this episode unlike the recent ones, or ''"
}}
Rules: an outfit for every person in the cast{me_rule}. Moods fit the person and this episode's plan, not a stock
list: a proud, arrogant or manipulative person barely moves their face (a thin one-sided smile, a slow blink), so their
moods are quiet ones and their notes say so; an open, warm person shows more. Never theatrical. Base outfits on what the phone says they wear when it fits.
Don't invent events the chat doesn't support. A kept place is reused when the episode happens there."""


def _lines(items):
    return "\n".join(items) or "(none)"


def propose(user, thread, chars, pulse_event=None, wish="", director=False, story=None):
    """Bulba's casting sheet (one call to Bulba's model), checked against what really exists."""
    ctx = context(user, thread, chars, pulse_event, director, story=story)
    sc = ctx["scene"]
    people = ctx["people"] + ([ctx["me"]] if director else [])
    prompt = PROMPT.format(
        user=sc["user_name"], names=", ".join(p["name"] for p in ctx["people"]), clock=sc["clock"],
        memory=sc["memory"][:1500] or "(none)", scenario=sc["scenario"][:800] or "(none)",
        right_now=json.dumps(sc["scene"], ensure_ascii=False)[:800] or "(none)",
        conversation="\n".join(sc["conversation"].splitlines()[-24:])[:3500] or "(no texts yet)",
        pulse=("PLAN: " + json.dumps({k: ctx["pulse"].get(k) for k in ("title", "when_label", "location", "purpose")},
                                     ensure_ascii=False)) if ctx["pulse"] else "",
        wish=str(wish or "")[:600] or "(none)",
        people=_lines(f"- {p['key']}: {p['name'] or 'the user'} ({p['setting']}); wears: {p['wearing'] or 'unknown'}; "
                      f"looks: {json.dumps(p['looks'], ensure_ascii=False)}" for p in people),
        backdrops=_lines(f"- {b['id']}: {b['name']}{' (kept)' if b['kept'] else ''}" for b in ctx["backdrops"]),
        phone_places=json.dumps(ctx["phone_places"], ensure_ascii=False)[:1200] or "(none)",
        recent=_lines(f"- {r['title']} at {r['location']}: {r['summary']}" for r in ctx["recent"]),
        me_rule=", and for `user`" if director else "",
    )
    if story is not None:
        prompt = _for_story(prompt, story)
    raw = messenger.ask_json(user, prompt, need=("place", "opening"), max_tokens=2200)
    return clean(raw, ctx)


def _for_story(prompt, story):
    """The same sheet for the next scene of a long-form story: the bible and where the last scene ended, no phone."""
    bible = story.bible or {}
    last = bible.get("last") or {}
    first = not story.scenes.exists()
    head = ("You are Bulba, preparing the casting sheet for the NEXT SCENE of a long-form visual-novel story "
            f"(\"{story.title}\", {story.tone or 'its own tone'}). There is no phone chat: the story bible below is the truth.\n"
            + ("This is the FIRST scene. Its opening: " + (bible.get("opening") or story.premise[:400]) + "\n" if first else
               f"The last scene ended at {last.get('place') or '?'}, {last.get('time') or '?'}, with "
               f"{', '.join(last.get('present') or []) or '?'} there. The next scene follows on (later the same day, or "
               "after a gap the story makes sensible); time only moves forward.\n")
            + "Timeline so far:\n" + "\n".join(f"- {t}" for t in (bible.get("timeline") or [])[-8:]) + "\n")
    body = prompt.split("\n", 1)[1] if "\n" in prompt else prompt
    return head + body.replace("Right now (from the phone)", "What they wore at the end of the last scene").replace(
        "Recent texts:", "(no texts: this is a story)").replace("PLACES THE PHONE ALREADY DESCRIBED", "PLACES ALREADY DESCRIBED").replace(
        "RECENT EPISODES", "EARLIER SCENES OF THE STORY").replace("Don't invent events the chat doesn't support.",
                                                                  "Don't invent events the story doesn't support.")


def clean(raw, ctx):
    """Keep only what fits: known people, their own looks, listed backdrops; trim every text."""
    keys = {p["key"]: p for p in ctx["people"]}
    if ctx.get("director"):
        keys["user"] = ctx["me"]
    text = lambda v, n: " ".join(str(v or "").split())[:n]
    cast = [k for k in (raw.get("cast") or []) if isinstance(k, str) and k in keys and k != "user"]
    cast = cast or [p["key"] for p in ctx["people"]]
    if ctx.get("pulse", {}).get("participants"):
        cast = [k for k in ctx["pulse"]["participants"] if k in keys]  # a plan's cast is the plan's
    place = raw.get("place") if isinstance(raw.get("place"), dict) else {}
    backdrop_ids = {b["id"] for b in ctx["backdrops"]}
    place = {"name": text(place.get("name"), 120), "time": text(place.get("time"), 120),
             "light": text(place.get("light"), 200), "weather": text(place.get("weather"), 160),
             "layout": text(place.get("layout"), 400),
             "details": [text(d, 160) for d in (place.get("details") or []) if text(d, 160)][:6] if isinstance(place.get("details"), list) else [],
             "background_id": place.get("background_id") if place.get("background_id") in backdrop_ids else ""}
    outfits = []
    for o in raw.get("outfits") or []:
        if not isinstance(o, dict) or o.get("key") not in keys or any(x["key"] == o["key"] for x in outfits):
            continue
        own = {l["id"] for l in keys[o["key"]]["looks"]}
        look_id = int(o["look_id"]) if str(o.get("look_id") or "").isdigit() and int(o["look_id"]) in own else None
        items = text(o.get("items"), 900)
        from mainapp import sprites
        moods = list(dict.fromkeys(m for m in (sprites.clean_name(x) for x in (o.get("moods") or [])
                                                if isinstance(x, str)) if m and m != "neutral"))[:8] \
            if isinstance(o.get("moods"), list) else []
        raw_notes = o.get("mood_notes") if isinstance(o.get("mood_notes"), dict) else {}
        notes = {}
        for k, v in raw_notes.items():
            mood = sprites.clean_name(k)
            if mood in moods and text(v, 240):
                notes[mood] = text(v, 240)
        if look_id or items:
            outfits.append({"key": o["key"], "look_id": look_id, "name": text(o.get("name"), 60) or "Episode outfit",
                            "items": items, "why": text(o.get("why"), 200), "moods": moods, "mood_notes": notes})
    facts = [text(f, 240) for f in (raw.get("facts") or []) if text(f, 240)][:MAX_FACTS] if isinstance(raw.get("facts"), list) else []
    return {"cast": cast, "place": place, "outfits": outfits, "facts": facts,
            "opening": text(raw.get("opening"), 500), "nudge": text(raw.get("nudge"), 300)}


def place_card(place):
    """The place written out, as the storyteller and the picture model read it."""
    if not isinstance(place, dict):
        return ""
    parts = [place.get("name") or ""]
    for label, key in (("Time", "time"), ("Light", "light"), ("Weather", "weather"), ("Layout", "layout")):
        if place.get(key):
            parts.append(f"{label}: {place[key]}")
    if place.get("details"):
        parts.append("Fixed details: " + "; ".join(place["details"]))
    return ". ".join(p for p in parts if p)


def draw_place(user, place, setting="canon"):
    """Draw the place from its card once and keep it. Returns (EpisodePlace, cost)."""
    card = place_card(place)
    if not (place or {}).get("name"):
        raise ai_client.AIError("Give the place a name first.")
    era = "present day" if setting == "modern" else "the world and era of the story"
    from mainapp import picture_checks
    image, cost, _ = picture_checks.draw_checked(user, (
        f"A visual-novel background of {card}.\nSetting: {era}.\n"
        "Environment only: no people, no characters, no text or lettering. Eye-level wide shot, as if standing in the "
        "room or street, arranged exactly as the layout says, with open floor in the lower middle where characters "
        "will stand. Every listed detail visible."), kind="place", what=card)
    path = default_storage.save(f"episode_places/{user.pk}/{uuid.uuid4().hex}.png", ContentFile(image))
    kept = EpisodePlace.objects.create(author=user, name=place["name"][:120], card=card, setting=setting, image=path)
    return kept, float(cost or 0.0)


def pack_place(kept):
    return {"id": f"place_{kept.pk}", "name": kept.name, "card": kept.card, "url": default_storage.url(kept.image)}


def brief(casting):
    """The applied casting sheet as fixed instructions for the storyteller."""
    if not isinstance(casting, dict):
        return ""
    lines = ["CASTING (fixed for this episode; keep every part of it true):"]
    card = place_card(casting.get("place"))
    if card:
        lines.append("Place: " + card)
    if casting.get("facts"):
        lines.append("Facts to keep true:\n" + "\n".join(f"- {f}" for f in casting["facts"]))
    if casting.get("opening"):
        lines.append("Opening: " + casting["opening"])
    if casting.get("nudge"):
        lines.append("A detail to use somewhere in this episode, naturally: " + casting["nudge"])
    return "\n".join(lines) if len(lines) > 1 else ""


def checked(raw, chars, user):
    """The casting sheet the user applied, as start_scene keeps it: only known people, listed backdrops, short texts."""
    if not isinstance(raw, dict):
        return None
    keys = {c.slug for c in chars}
    text = lambda v, n: " ".join(str(v or "").split())[:n]
    place = raw.get("place") if isinstance(raw.get("place"), dict) else {}
    ids = {b["id"] for b in vn_scenes.available_backgrounds(chars, user)}
    out = {
        "cast": [k for k in (raw.get("cast") or []) if k in keys],
        "place": {"name": text(place.get("name"), 120), "time": text(place.get("time"), 120),
                  "light": text(place.get("light"), 200), "weather": text(place.get("weather"), 160),
                  "layout": text(place.get("layout"), 400),
                  "details": [text(d, 160) for d in (place.get("details") or [])][:6] if isinstance(place.get("details"), list) else [],
                  "background_id": place.get("background_id") if place.get("background_id") in ids else ""},
        "facts": [text(f, 240) for f in (raw.get("facts") or []) if text(f, 240)][:MAX_FACTS] if isinstance(raw.get("facts"), list) else [],
        "opening": text(raw.get("opening"), 500),
        "nudge": text(raw.get("nudge"), 300),
    }
    return out
