"""
Stories: long-form visual novels started from scratch (no phone chat), played scene by scene.

Bulba sets a story up from the user's wishes: title, premise, the world in concrete facts, side characters it makes
for the story (real characters, kept out of the library and the phone), where everyone stands, open threads, how it
opens, and an arc of chapters with turning points and a direction for the ending. The arc stays hidden unless the
user asks to see it; the storyteller gets the current chapter's goal and next turning point as quiet direction,
never as something to announce, and the user's choices may bend it.

Each scene is an ordinary episode (casting, stage, looks, Watch) with the story as its context. When a scene ends it
is kept (StoryScene), and Bulba updates the story bible (world facts, where people stand, open threads, the timeline,
where the scene ended) and the arc's progress; a finished chapter gets a chapter card.
"""
import json
import re

from django.utils.text import slugify

from mainapp import ai_client, messenger
from mainapp.models import Character, Story, StoryScene

SETTINGS = ("canon", "modern", "original")
MODES = ("episodes", "roleplay")
SIDE_FIELDS = (("name", 80), ("role", 300), ("appearance", 600), ("personality", 600), ("speech", 300))
MAX_SIDE = 4

SETUP_PROMPT = """You are Bulba, setting up a long-form interactive visual-novel story for the user. Plain words: no
metaphors, no mood-writing. Characters are people with their own wants, not tropes or types.

The user's wishes: {wishes}
Setting: {setting}
Tone they asked for: {tone}
Who the user plays: {persona}
Their cast:
{cast}

Return ONLY this JSON:
{{
  "title": "a short title",
  "premise": "3-5 sentences: the situation when the story starts and what is at stake for the user's character",
  "tone": "the tone in a few words",
  "world": ["6 to 10 concrete facts about the world, its places and its rules that scenes must keep true"],
  "side_characters": [{{"name": "...", "role": "what they are to the story and to the cast",
                       "personality": "2-3 sentences: wants, habits, how they treat others",
                       "appearance": "concrete and visible: age, build, hair, eyes, skin, clothes",
                       "speech": "how they talk"}}],
  "relations": ["where each cast member stands with the user's character at the start, one line each"],
  "threads": ["2 to 5 open questions, promises or problems at the start"],
  "arc": {{"chapters": [{{"title": "...", "goal": "what this chapter is about",
                          "beats": ["3 to 5 turning points, in order"], "ends_when": "what closes the chapter"}}],
          "ending": "where the story is heading; the user's choices may change it"}},
  "opening": "one or two sentences: where and how the first scene starts"
}}
Rules: 3 to 6 chapters. 0 to {max_side} side characters, only for roles the cast can't fill (a rival, a mentor,
a shopkeeper who matters). Every fact must fit the cast's descriptions."""


def _text(v, n):
    return " ".join(str(v or "").split())[:n]


def _list(v, n, size=240):
    return [_text(x, size) for x in (v if isinstance(v, list) else []) if _text(x, size)][:n]


def persona_of(user, story=None, choice=None):
    """(name, description) of who the user plays: the story's own persona, or their usual one."""
    from mainapp.cards import user_name
    p = (story.persona if story else choice) or {}
    if p.get("mode") == "story" and p.get("name"):
        return _text(p["name"], 80), _text(p.get("description"), 1500)
    return user_name(user), str(getattr(user, "persona_description", "") or "")[:1500]


def propose(user, wishes, cast, setting="canon", tone="", persona=None):
    """Bulba's setup for a new story (one call), trimmed to what fits."""
    name, about = persona_of(user, choice=persona)
    lines = []
    for c in cast:
        prof = messenger.char_profile(c)
        lines.append(f"- {prof['display_name']}: {_text(c.description, 700)} | {_text(c.personality, 300)}")
    raw = messenger.ask_json(user, SETUP_PROMPT.format(
        wishes=_text(wishes, 1500) or "(none: surprise them)", tone=_text(tone, 200) or "(their choice)",
        setting={"canon": "the cast's own world and era", "modern": "the present day (a modern version of the cast)",
                 "original": "an original world made for this story"}.get(setting, setting),
        persona=f"{name}: {about or '(not described)'}", cast="\n".join(lines) or "(no cast picked: Bulba makes it)",
        max_side=MAX_SIDE), need=("title", "premise", "arc"), max_tokens=4000)
    return clean_setup(raw)


def clean_setup(raw):
    arc = raw.get("arc") if isinstance(raw.get("arc"), dict) else {}
    chapters = []
    for ch in (arc.get("chapters") or [])[:8] if isinstance(arc.get("chapters"), list) else []:
        if isinstance(ch, dict) and _text(ch.get("title") or ch.get("goal"), 10):
            chapters.append({"title": _text(ch.get("title"), 120), "goal": _text(ch.get("goal"), 400),
                             "beats": _list(ch.get("beats"), 6, 300), "ends_when": _text(ch.get("ends_when"), 300)})
    sides = []
    for s in (raw.get("side_characters") or [])[:MAX_SIDE] if isinstance(raw.get("side_characters"), list) else []:
        if isinstance(s, dict) and _text(s.get("name"), 80):
            sides.append({k: _text(s.get(k), n) for k, n in (("name", 80), ("role", 300), ("personality", 600),
                                                               ("appearance", 600), ("speech", 300))})
    return {"title": _text(raw.get("title"), 160) or "Untitled story", "premise": _text(raw.get("premise"), 1500),
            "tone": _text(raw.get("tone"), 200), "world": _list(raw.get("world"), 12),
            "side_characters": sides, "relations": _list(raw.get("relations"), 10), "threads": _list(raw.get("threads"), 8),
            "arc": {"chapters": chapters, "ending": _text(arc.get("ending"), 500), "at": {"chapter": 0, "beat": 0}},
            "opening": _text(raw.get("opening"), 500)}


def _slug(base):
    stem = slugify(base)[:40] or "side"
    slug, n = f"story-{stem}", 1
    while Character.objects.filter(slug=slug).exists():
        n += 1
        slug = f"story-{stem}-{n}"
    return slug


def create(user, setup, cast, setting="canon", persona=None, style=None, mode="episodes"):
    """The story from an applied setup: side characters become real characters of this story."""
    setup = clean_setup(setup) if isinstance(setup, dict) else clean_setup({})
    story = Story.objects.create(
        author=user, title=setup["title"], premise=setup["premise"], tone=setup["tone"],
        setting=setting if setting in SETTINGS else "canon",
        persona=persona if isinstance(persona, dict) and persona.get("mode") in ("usual", "story") else {"mode": "usual"},
        arc=setup["arc"], style=style if isinstance(style, dict) else {}, mode=mode if mode in MODES else "episodes",
        bible={"world": setup["world"], "relations": setup["relations"], "threads": setup["threads"], "timeline": [],
               "opening": setup["opening"], "last": {}})
    story.cast.set(cast)
    for side in setup["side_characters"]:
        story.cast.add(add_side(story, side))
    sync_player(story)
    return story


def add_side(story, side):
    """A side character of this story from Bulba's (or the user's) description."""
    side = {k: _text(side.get(k), n) for k, n in SIDE_FIELDS}
    person = Character.objects.create(author=story.author, name=side["name"] or "Someone", slug=_slug(side["name"]),
                                      side_story=story)
    edit_side(person, side)
    return person


def edit_side(person, side):
    """Write a side character's card from the story's fields (name, role, appearance, personality, speech)."""
    side = {k: _text(side.get(k), n) for k, n in SIDE_FIELDS}
    prof = messenger.char_profile(person)
    now = {"name": person.name, "role": person.scenario.replace("Role in the story: ", "", 1),
           "appearance": prof.get("appearance_notes") or "", "personality": person.personality,
           "speech": person.example_dialogue}
    new = {k: side[k] or now[k] for k, _ in SIDE_FIELDS}
    person.name = new["name"]
    person.description = f"{new['appearance']}\n\n{new['personality']}".strip()
    person.personality, person.example_dialogue = new["personality"], new["speech"]
    person.scenario = f"Role in the story: {new['role']}"
    person.save()
    messenger.save_char_profile(person, {"appearance_notes": new["appearance"], "display_name": new["name"]})
    return person


def side_card(person):
    prof = messenger.char_profile(person)
    return {"slug": person.slug, "name": prof["display_name"], "role": person.scenario.replace("Role in the story: ", "", 1),
            "appearance": prof.get("appearance_notes") or "", "personality": person.personality, "speech": person.example_dialogue}


def sync_player(story):
    """Who the user plays in this story as a hidden character of it, when it's someone of their own (so their looks
    are drawn from the description); none when they play their usual persona."""
    p = story.persona or {}
    if p.get("mode") != "story" or not _text(p.get("name"), 80):
        if story.player_id:
            story.player = None
            story.save(update_fields=["player"])
        return None
    side = {"name": p["name"], "role": "the user's character", "appearance": p.get("description"),
            "personality": p.get("description"), "speech": ""}
    if story.player_id:
        edit_side(story.player, side)
    else:
        story.player = add_side(story, side)
        story.save(update_fields=["player"])
    return story.player


def player(story):
    """The character standing in for the user in this story (None: their usual persona)."""
    return story.player if story is not None and story.player_id else None


def roleplay_style(story):
    """A roleplay story's turns: their own paragraphs kept as they are, about as much back, no choices."""
    return {"length": "match", "write_out": False}


def continue_hint(story):
    """Where a roleplay story's next scene starts when nothing is planned: right after the last one."""
    last = (story.bible or {}).get("last") or {}
    if not last.get("place"):
        return ""
    return (f"Continue the story straight on from where the last scene ended ({last['place']}"
            + (f", {last['time']}" if last.get("time") else "") + ", with " + (", ".join(last.get("present") or []) or "the same people")
            + "). If that moment was finished, pick up at the next thing that happens; time only moves forward.")


def look_setting(story):
    """The setting looks are drawn in: an original world counts as canon (their own clothes and era)."""
    return "modern" if story.setting == "modern" else "canon"


def scene_context(user, story):
    """What an episode of this story knows, in the shape the phone's context has."""
    name, about = persona_of(user, story)
    bible = story.bible or {}
    earlier = list(story.scenes.order_by("-number")[:6])[::-1]
    memory = "\n".join(f"Scene {s.number} ({s.place}): {s.summary}" for s in earlier)
    scenario = story.premise + ("\nThe world:\n" + "\n".join(f"- {f}" for f in bible.get("world") or []) if bible.get("world") else "")
    if bible.get("relations"):
        scenario += "\nWhere people stand:\n" + "\n".join(f"- {r}" for r in bible["relations"])
    if bible.get("threads"):
        scenario += "\nOpen threads:\n" + "\n".join(f"- {t}" for t in bible["threads"])
    last = bible.get("last") or {}
    return {"user_name": name, "persona": about, "clock": last.get("time") or "", "memory": memory,
            "scenario": scenario[:6000], "share_memory": True, "scene": {}, "events": [],
            "conversation": "", "story_title": story.title}


def secret_direction(story):
    """The arc's quiet direction for the storyteller: the chapter's goal and the next turning point."""
    arc = story.arc or {}
    chapters = arc.get("chapters") or []
    at = arc.get("at") or {}
    i = min(int(at.get("chapter") or 0), max(len(chapters) - 1, 0))
    if not chapters:
        return ""
    ch = chapters[i]
    beat_i = int(at.get("beat") or 0)
    nxt = ch["beats"][beat_i] if beat_i < len(ch.get("beats") or []) else ""
    return ("STORY DIRECTION (for you only: never announce it, never force it; the user's choices come first and may "
            f"change it): chapter {i + 1}, \"{ch['title']}\": {ch['goal']}"
            + (f" Next turning point to steer toward when it fits: {nxt}" if nxt else "")
            + (f" The chapter closes when: {ch['ends_when']}" if ch.get("ends_when") else "")
            + " When a turning point lands, that is usually a good place to end the scene (scene_end).")


KEEPER_PROMPT = """You keep the story bible of a long-form visual novel. A scene just ended. Update the bible with what
this scene made true; keep everything earlier that still holds. Plain, concrete lines.

STORY: {title}. {premise}
BIBLE BEFORE: {bible}
ARC (hidden from the user): {arc}
THE SCENE ({place}):
{transcript}

Return ONLY JSON:
{{"summary": "3-5 sentences of what happened, for the story so far",
  "world": ["the full list of world facts, new ones added"],
  "relations": ["where each person now stands with the user's character, one line each"],
  "threads": ["open questions, promises and problems now (drop the resolved ones)"],
  "timeline": "one line: when this scene happened and what it changed",
  "last": {{"place": "where the scene ended", "time": "story time at the end", "present": ["who was there at the end"],
           "outfits": {{"<name>": "what they wore at the end"}}}},
  "arc": {{"beats_reached": <how many turning points of the current chapter are now behind>, "chapter_done": true|false}},
  "chapter_card": "if the chapter closed: 2-3 sentences on how it ended, else ''",
  "new_people": [{{"name": "...", "role": "...", "appearance": "concrete and visible", "personality": "2 sentences",
                   "speech": "how they talk"}}]}}
new_people: only NAMED people who appeared in this scene, are not in the cast ({cast}) and will matter again; usually
none. Describe them as the scene showed them."""


def record_scene(user, scene, finished):
    """Keep a finished scene in its story and let Bulba update the bible and the arc's place. Returns StoryScene."""
    story = Story.objects.filter(author=user, pk=scene.get("story_id") or 0).first()
    if story is None:
        return None
    beats = scene.get("beats") or []
    arc = story.arc or {}
    at = dict(arc.get("at") or {"chapter": 0, "beat": 0})
    transcript = "\n".join(f"{b.get('speaker_name') or b.get('speaker')}: {b.get('text')}" for b in beats[-80:])
    fields = {"title": _text(scene.get("title"), 160), "place": _text(scene.get("location"), 160),
              "summary": _text(finished.get("summary"), 2000), "beats": beats, "cg_url": finished.get("cg_url") or "",
              "cost": float((finished.get("cost") or {}).get("total") or 0)}
    kept = story.scenes.filter(episode_id=scene.get("id") or "-").first()
    again = kept is not None  # reopened from Saved episodes and finished again: the same scene, rewritten
    if again:
        for key, value in fields.items():
            setattr(kept, key, value)
    else:
        kept = StoryScene.objects.create(story=story, number=story.scenes.count() + 1, chapter=int(at.get("chapter") or 0) + 1,
                                         episode_id=str(scene.get("id") or "")[:40], **fields)
    try:
        out = messenger.ask_json(user, KEEPER_PROMPT.format(
            title=story.title, premise=story.premise[:1200], bible=json.dumps(story.bible or {}, ensure_ascii=False)[:5000],
            arc=json.dumps(arc, ensure_ascii=False)[:3000], place=kept.place, transcript=transcript[:9000],
            cast=", ".join(messenger.char_profile(c)["display_name"] for c in story.cast.all())),
            need=("summary",), max_tokens=3000)
    except ai_client.AIError:
        out = {}
    bible = dict(story.bible or {})
    if out:
        kept.summary = _text(out.get("summary"), 2000) or kept.summary
        for key, n in (("world", 20), ("relations", 12), ("threads", 10)):
            if isinstance(out.get(key), list) and out[key]:
                bible[key] = _list(out[key], n)
        if _text(out.get("timeline"), 10):
            bible["timeline"] = (list(bible.get("timeline") or []) + [_text(out["timeline"], 300)])[-30:]
        if isinstance(out.get("last"), dict):
            bible["last"] = {"place": _text(out["last"].get("place"), 200), "time": _text(out["last"].get("time"), 120),
                             "present": _list(out["last"].get("present"), 8, 80),
                             "outfits": {(_text(k, 80)): _text(v, 300) for k, v in (out["last"].get("outfits") or {}).items()}
                             if isinstance(out["last"].get("outfits"), dict) else {}}
        known = {c.name.lower() for c in story.cast.all()} | {messenger.char_profile(c)["display_name"].lower() for c in story.cast.all()}
        offered = [p for p in bible.get("new_people") or [] if isinstance(p, dict)]
        for person in (out.get("new_people") if isinstance(out.get("new_people"), list) else [])[:3]:
            person = {k: _text(person.get(k), n) for k, n in SIDE_FIELDS} if isinstance(person, dict) else {}
            if person.get("name") and person["name"].lower() not in known | {o["name"].lower() for o in offered} \
                    | {n.lower() for n in bible.get("declined") or []}:
                offered.append(person)
        bible["new_people"] = offered[-6:]
        progress = out.get("arc") if isinstance(out.get("arc"), dict) else {}
        chapters = arc.get("chapters") or []
        reached = progress.get("beats_reached")
        if isinstance(reached, int) and reached >= 0:
            at["beat"] = max(int(at.get("beat") or 0), reached)
        if progress.get("chapter_done") is True and chapters and not again:
            kept.chapter_card = {"chapter": int(at.get("chapter") or 0) + 1,
                                 "title": chapters[min(int(at.get("chapter") or 0), len(chapters) - 1)]["title"],
                                 "text": _text(out.get("chapter_card"), 800)}
            at = {"chapter": int(at.get("chapter") or 0) + 1, "beat": 0}
            if at["chapter"] >= len(chapters):
                story.status = "ended"
    kept.save()
    story.bible = bible
    story.arc = {**arc, "at": at}
    story.save(update_fields=["bible", "arc", "status", "updated"])
    return kept


def pack(story, full=False):
    """A story for the page. The arc's contents only when the user asked to see them."""
    cast = [{"slug": c.slug, "name": messenger.char_profile(c)["display_name"], "side": c.side_story_id == story.pk,
             "avatar": c.photo_neutral.url if c.photo_neutral else ""} for c in story.cast.all()]
    arc = story.arc or {}
    chapters = arc.get("chapters") or []
    at = arc.get("at") or {}
    out = {"id": story.pk, "title": story.title, "premise": story.premise, "tone": story.tone, "setting": story.setting,
           "status": story.status, "cast": cast, "persona": persona_of(story.author, story)[0],
           "chapters": len(chapters), "chapter_now": min(int(at.get("chapter") or 0) + 1, max(len(chapters), 1)),
           "scenes": story.scenes.count(), "show_arc": story.show_arc, "updated": story.updated.isoformat(),
           "mode": story.mode, "persona_mode": (story.persona or {}).get("mode") or "usual",
           "cost": round(sum(s.cost for s in story.scenes.all()), 3)}
    if full:
        from mainapp import vn_scenes
        state = vn_scenes.get_vn_state(story.author)
        active = state.get("active_scene") or {}
        out["open_scene"] = {"title": active.get("title") or "", "pages": len(active.get("beats") or [])} \
            if active.get("story_id") == story.pk else None
        out["drafts"] = [{"id": d["id"], "label": d.get("label") or "", "title": d.get("title") or ""}
                         for d in state.get("drafts") or [] if (d.get("scene") or {}).get("story_id") == story.pk][-4:]
        out["missing"] = missing(story, state)
        out["sides"] = [side_card(c) for c in story.cast.filter(side_story=story)]
        out["player"] = side_card(story.player) if story.player_id else None
        out["persona_full"] = story.persona or {"mode": "usual"}
        out["new_people"] = (story.bible or {}).get("new_people") or []
        last = story.scenes.order_by("-number").first()
        out["previously"] = last.summary if last else ""
        out["bible"] = story.bible or {}
        out["scene_list"] = [{"id": s.pk, "number": s.number, "chapter": s.chapter, "title": s.title, "place": s.place,
                              "summary": s.summary, "cg_url": s.cg_url, "chapter_card": s.chapter_card,
                              "pages": len(s.beats or [])} for s in story.scenes.all()]
        out["chapter_titles"] = [c["title"] for c in chapters[:int(at.get("chapter") or 0) + 1]]  # reached so far
        if story.show_arc:
            out["arc"] = arc
    return out


def missing(story, state):
    """Finished episodes of this story that never made it in (Bulba's update failed): offered again."""
    kept = set(story.scenes.values_list("episode_id", flat=True))
    return [{"id": g["id"], "title": g.get("title") or "", "summary": (g.get("summary") or "")[:300]}
            for g in state.get("gallery") or []
            if (g.get("episode") or {}).get("story_id") == story.pk and g.get("id") not in kept]


def catch_up(user, story, episode_id):
    """Add a finished episode the story missed, from the saved episode."""
    from mainapp import vn_scenes
    entry = next((g for g in vn_scenes.get_vn_state(user).get("gallery") or []
                  if g.get("id") == episode_id and (g.get("episode") or {}).get("story_id") == story.pk), None)
    if entry is None:
        raise ValueError("That episode isn't one of this story's.")
    scene = {**entry["episode"], "beats": entry.get("beats") or entry["episode"].get("beats") or []}
    cost = entry.get("cost") if isinstance(entry.get("cost"), dict) else {"total": entry.get("cost") or 0}
    return record_scene(user, scene, {"summary": entry.get("summary") or "", "cg_url": entry.get("cg_url") or "", "cost": cost})


def take_new_person(story, name, add=True):
    """Add a person Bulba noticed as a side character, or let them go (and don't offer them again)."""
    bible = dict(story.bible or {})
    offered = [p for p in bible.get("new_people") or [] if isinstance(p, dict)]
    person = next((p for p in offered if p.get("name", "").lower() == str(name or "").strip().lower()), None)
    if person is None:
        raise ValueError("Bulba isn't offering that person any more.")
    bible["new_people"] = [p for p in offered if p is not person]
    made = None
    if add:
        made = add_side(story, person)
        story.cast.add(made)
    else:
        bible["declined"] = (list(bible.get("declined") or []) + [person["name"]])[-30:]
    story.bible = bible
    story.save(update_fields=["bible", "updated"])
    return made


def scene_beats(user, scene_id):
    kept = StoryScene.objects.filter(story__author=user, pk=scene_id).first()
    if kept is None:
        raise ValueError("That scene isn't yours.")
    return {"title": kept.title, "place": kept.place, "summary": kept.summary, "cg_url": kept.cg_url, "beats": kept.beats}


def owned(user, story_id):
    story = Story.objects.filter(author=user, pk=str(story_id or "").strip() if str(story_id or "").strip().isdigit() else 0).first()
    if story is None:
        raise ValueError("That story isn't yours or no longer exists.")
    return story


def delete(story):
    """The story, its scenes and its side characters (their looks and pictures go with them)."""
    from mainapp import episode_looks
    from mainapp.models import EpisodeLook
    for look in EpisodeLook.objects.filter(character__side_story=story):
        episode_looks.delete(look)
    story.delete()
