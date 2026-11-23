"""
Visual Novel Meet-Up Scene Mode & CG Gallery for the Digital Screen Hub.

When characters in TeleChat are about to meet in person (or when triggered manually),
the Digital Screen transitions into a Visual Novel environment:
- Central character expression sprite stage + location backdrop + background music chosen by the model
  from `media_library.built_in("music")` and the character's theme track.
- Splits narration/action and character dialogue into step-by-step Visual Novel beats, matching an
  expression mood (`emotion`) to every line and deciding when to hand input to the user (`handoff`).
- Dynamically generates new expression sprites when a beat calls for a mood the character doesn't have yet,
  and stores them as episode assets.
- Saves a completed episode and its full transcript independently of optional illustration generation,
  writes its summary back to the originating TeleChat thread, and lets the user return to the phone.
- Carries an explicit continuity record and participant references into image requests; outfit-specific
  expression assets are kept with the episode rather than replacing the character's regular sprites.
"""

import json
import copy
import logging
import re
import time
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from mainapp import ai_client, episode_looks, media_library, messenger, sprites, thinking, vn_support, vn_story
from mainapp.models import ChatSettings, EpisodeLook, MessengerThread

log = logging.getLogger(__name__)

MEETUP_CUE_RE = re.compile(
    r"\b(meet\s+up|meet\s+me|on\s+my\s+way|coming\s+over|come\s+over|at\s+the\s+door|outside\s+your|"
    r"see\s+you\s+in|see\s+you\s+at|waiting\s+for\s+you|at\s+the\s+cafe|at\s+the\s+bar|at\s+the\s+lab|"
    r"let's\s+hang|hang\s+out|grab\s+coffee|grab\s+a\s+drink| grab\s+dinner|pick\s+you\s+up|i'm\s+here|"
    r"knocking|зустрінемось|зустрінемося|зустрічай|я\s+вже\s+тут|біля\s+дверей|зайди\s+до\s+мене)\b",
    re.I,
)


def _get_settings_obj(user):
    settings_obj, _ = ChatSettings.objects.get_or_create(author=user)
    if not isinstance(settings_obj.appearance, dict):
        settings_obj.appearance = {}
    return settings_obj


def get_vn_state(user):
    """Return `{active_scene: dict|None, gallery: [dict, ...]}` from the user's `ChatSettings.appearance['vn_scenes']`."""
    settings_obj = _get_settings_obj(user)
    raw = (settings_obj.appearance or {}).get("vn_scenes")
    if not isinstance(raw, dict):
        raw = {}
    active = raw.get("active_scene") if isinstance(raw.get("active_scene"), dict) else None
    gallery = [g for g in (raw.get("gallery") or []) if isinstance(g, dict)]
    return {
        "active_scene": active,
        "gallery": gallery,
        "drafts": raw.get("drafts") or [],
        "music_catalog": available_music_tracks(),
        "bg_catalog": available_backgrounds(),
    }


@transaction.atomic
def save_vn_state(user, updates, expected=None):
    settings_obj = _get_settings_obj(user)
    settings_obj = ChatSettings.objects.select_for_update().get(pk=settings_obj.pk)
    app = dict(settings_obj.appearance or {})
    cur = dict(app.get("vn_scenes") or {})
    active = cur.get("active_scene") or {}
    if expected is not None and (active.get("id", ""), active.get("revision", 0)) != expected:
        raise ai_client.AIError("This episode changed in another request. Reload it before continuing.")
    if isinstance(updates.get("active_scene"), dict):
        updates["active_scene"]["revision"] = active.get("revision", 0) + 1
    cur.update(updates)
    app["vn_scenes"] = cur
    settings_obj.appearance = app
    settings_obj.save(update_fields=["appearance"])
    return cur


def available_music_tracks(characters=None):
    """Return all available music tracks from `media_library.built_in('music')` plus any character theme tracks."""
    tracks = []
    seen = set()
    for c in (characters or []):
        t_music = (getattr(c, "theme", None) or {}).get("music")
        if isinstance(t_music, dict) and t_music.get("url") and t_music["url"] not in seen:
            tracks.append({
                "id": f"char_music_{c.slug}",
                "name": t_music.get("name") or f"{c.name}'s Theme",
                "url": t_music["url"],
            })
            seen.add(t_music["url"])
    for idx, t in enumerate(media_library.built_in("music")):
        if t["url"] not in seen:
            tracks.append({
                "id": f"builtin_music_{idx}",
                "name": t["name"],
                "url": t["url"],
            })
            seen.add(t["url"])
    return tracks


def available_backgrounds(characters=None):
    """Return all available scene backgrounds from `media_library.built_in('backgrounds')` plus character theme BGs."""
    bgs = []
    seen = set()
    for c in (characters or []):
        t_bg = (getattr(c, "theme", None) or {}).get("bg")
        if t_bg and isinstance(t_bg, str) and t_bg not in seen:
            bgs.append({
                "id": f"char_bg_{c.slug}",
                "name": f"{c.name}'s Backdrop",
                "url": t_bg,
            })
            seen.add(t_bg)
    for idx, b in enumerate(media_library.built_in("backgrounds")):
        if b["url"] not in seen:
            bgs.append({
                "id": f"builtin_bg_{idx}",
                "name": b["name"],
                "url": b["url"],
            })
            seen.add(b["url"])
    return bgs


def detect_meetup_cue(thread):
    """
    Inspect the last 4 messages in `thread` to check if the characters and user are about to meet up in person.
    Returns `{ready: bool, reason: str}` so TeleChat can surface a '🎬 Start Meet-Up Scene' prompt.
    """
    if not thread:
        return {"ready": False, "reason": ""}
    td = messenger.thread_data(thread)
    recent = [m for m in (td.get("messages") or [])[-4:] if m.get("role") in ("user", "assistant")]
    for m in reversed(recent):
        txt = str(m.get("text") or "")
        match = MEETUP_CUE_RE.search(txt)
        if match:
            return {
                "ready": True,
                "reason": f"Meet-up cue detected in chat (\"{match.group(0)}\")",
                "trigger_text": txt[:140],
            }
    return {"ready": False, "reason": ""}


def scene_setting(chars):
    """Canon or modern for the user's own look: modern when anyone in the cast is in their modern version."""
    return "modern" if any(episode_looks.setting_for(c) == "modern" for c in chars) else "canon"


def pick_looks(user, chars, chosen=None, director=False):
    """{slug or "user": look id} for an episode: the looks the user picked, else each one's latest look.

    Only the user's own looks, in the setting the episode was entered in, are accepted.
    """
    chosen = chosen if isinstance(chosen, dict) else {}
    out = {}
    people = [(c.slug, c, episode_looks.setting_for(c)) for c in chars]
    if director:
        people.append(("user", None, scene_setting(chars)))
    for key, character, setting in people:
        look = None
        if chosen.get(key):
            look = EpisodeLook.objects.filter(author=user, character=character, setting=setting,
                                              pk=str(chosen[key]).strip() if str(chosen[key]).strip().isdigit() else 0).first()
        look = look or episode_looks.default_look(user, character, setting)
        if look:
            out[key] = look.pk
    return out


def scene_looks(user, scene):
    """{slug or "user": EpisodeLook} for the looks this episode uses."""
    worn = (scene.get("current_stage") or {}).get("looks")
    ids = {k: v for k, v in (worn if isinstance(worn, dict) else scene.get("looks") or {}).items() if str(v).isdigit()}
    found = {look.pk: look for look in EpisodeLook.objects.filter(author=user, pk__in=[int(v) for v in ids.values()])
             .select_related("character")}
    return {k: found[int(v)] for k, v in ids.items() if int(v) in found}


def looks_payload(user, scene):
    """What the stage needs to draw everyone: {slug or "user": packed look}."""
    return {k: episode_looks.pack(look) for k, look in scene_looks(user, scene).items()}


def _look_reference(look):
    """The neutral picture of a look, for illustrations: identity and the outfit worn in the episode."""
    try:
        return episode_looks._base_image(look)
    except ai_client.AIError:
        return None


VN_SCENE_PROMPT = """You are directing an interactive **Visual Novel Meet-Up Scene** launched from {user}'s TeleChat messenger.
The texting phase has transitioned into an in-person scene!

Current Real-World Clock: {clock}
{model_rules}

VISUAL NOVEL ENGINE RULES:
1. WRITE COMPLETE NARRATIVE BLOCKS; DISPLAY SPLITTING IS THE ENGINE'S JOB:
   - Let the user's requested length and style guide the prose. Descriptive narration, asides and substantial dialogue are welcome when they fit.
   - Never shorten or stretch a passage to reach a line count. There is no required number of blocks or sentences.
   - Keep each speaker's dialogue separate from narration; a block may contain multiple paragraphs.
   - Preserve each character's current intention, knowledge, voice and relationship. Do not add hostility, attraction or a confession to manufacture drama.
   - Follow the explicit interaction and authorship mode below; it defines who the model may write for.
   - You are in person now. Characters can perceive what is present, but cannot know private thoughts or events they did not witness.
   - Vary speech according to character and circumstance. Do not recycle the previous turn's sentence shape, accusation list or rhetorical exchange merely with synonyms.
   - Continue until the situation offers a meaningful opening for user input. Scene changes require narrative cause; preserve outfits, objects, injuries and positions until an event changes them.
   - Top-level background, music and location describe the opening, not the end of the passage.
   - For EACH block, include `stage` containing changes that take effect at that block: background/music IDs, location, and a continuity patch (outfits, positions, time, summary, open_threads). Do not apply later changes to earlier blocks. Copy unchanged outfit descriptions verbatim.
   - Update `continuity` cumulatively: retain earlier facts and unresolved matters, and record actual changes. Time follows the story clock, not the wall clock.
   - Each item in `beats` must be either narration or one character's spoken dialogue.
   - Format examples below describe speaker metadata only; they are not length requirements.
   - Just like a real visual novel, each item in `"beats"` must be EITHER:
     * A **Narration / Action block** (`"speaker_slug": "narrator"`, `"speaker": "Narrator"`, `"emotion": "neutral"`, `"text": "Complete narration or action, without dialogue quote marks"`), OR
     * A **Character Dialogue block** (`"speaker_slug": "<character slug>"`, `"speaker": "<character name>"`, `"emotion": "<specific expression mood>"`, `"text": "Their complete spoken dialogue without narration tags"`).
   - Return 6–10 complete beats per request, ending at a natural input point. Continue in the next request.
2. EXPRESSIONS AND OUTFITS:
   - On every block with character speech or a silent reaction, set `"emotion"` to the face they show right now, chosen ONLY from that character's own mood list in PARTICIPATING CHARACTER(S). Do not invent moods; pick the closest listed one.
   - Each character wears exactly the outfit written under their name. Describe it only with those items. Clothes change only when the story makes them change.
   - When the story does change someone's clothes (a coat comes off, they get soaked, they change for bed), add to THAT block's `stage`: `"outfit_change": {{"<character slug>": "their whole new outfit, item by item"}}`. Once, at the block where it happens; never to restate an unchanged outfit.
3. MUSIC & BACKDROP SELECTION:
   - Choose `"music"` from the available music tracks list below that best matches the current emotional tone of the scene.
   - Choose `"background"` from the available backgrounds list below (or keep the current one).
4. TURN HANDOFF (CHOOSE WHEN TO LET {user} TYPE):
   - Set `"handoff"` to:
     * `"user_turn"` — Pause at a natural moment so {user} can type a short action or dialogue reply (and provide 2-3 short `"choices"` {user} can click or adapt).
     * `"auto_continue"` — The character is in the middle of an unfolding action/moment; let {user} click "Continue ▶" (or interrupt if they want).
     * `"climax_ready"` — The scene has reached a memorable peak or parting moment and is ready to conclude with a full Finale CG illustration!

AVAILABLE MUSIC TRACKS:
{music_list}

AVAILABLE BACKGROUNDS:
{bg_list}

USER PROFILE:
- Name: {user} — {user_persona}

PARTICIPATING CHARACTER(S):
{char_roster}

RECENT TELECHAT MESSAGES LEADING INTO THIS MEET-UP:
{telechat_context}

SCENE STATE SO FAR:
{scene_history}

LATEST INPUT / DIRECTION FOR THIS STEP:
{step_input}

Return ONLY a valid JSON object matching this exact structure (no markdown fences):
{{
  "title": "Short evocative title for this meet-up scene (e.g. 'Midnight at the Sumeru Lab')",
  "location": "Specific location & time label (e.g. 'Zurich Biotech Lab · 01:40 AM')",
  "background": "Exact name of chosen background from AVAILABLE BACKGROUNDS",
  "music": "Exact name of chosen music track from AVAILABLE MUSIC TRACKS",
  "handoff": "user_turn",
  "handoff_prompt": "Short 4-10 word cue for {user}, e.g. 'How do you answer Il Dottore?' or 'Scene climax reached — capture Finale CG!'",
  "choices": [
    "Short action or dialogue option 1 (under 14 words)",
    "Short action or dialogue option 2 (under 14 words)"
  ],
  "continuity": {{
    "summary": "Cumulative events and relationship changes; retain earlier consequential facts",
    "location": "Current setting, lighting, weather and relevant objects",
    "time": "Current story date and time; advance only as the scene warrants",
    "outfits": {{"<character slug>": "Current clothes and changes from their reference"}},
    "positions": {{"<character slug>": "Current position and action"}},
    "open_threads": ["Unresolved plans, promises, questions or injuries"]
  }},
  "beats": [
    {{
      "speaker_slug": "narrator",
      "speaker": "Narrator",
      "character_slug": "<slug of the character currently visible center-stage>",
      "emotion": "neutral",
      "stage": {{}},
      "text": "The complete narration block OR spoken dialogue"
    }}
  ]
}}"""


FINALE_CG_PROMPT = """You are creating the **Finale Event CG** and memory summary to conclude a Visual Novel Meet-Up Scene between {user} and {char_names}.

Scene Title: {title}
Location: {location}
Character Appearance & Art Style:
{char_visuals}

Scene Transcript:
{transcript}

User's optional Finale CG hint: {cg_hint}

Distill the most memorable, cinematic climax or closing moment of this scene into:
1. `"visual_prompt"`: A rich 2-3 sentence Visual Novel Event CG illustration prompt showing {char_names} in this exact setting, lighting, pose, expression, and atmosphere.
2. `"camera_angle"`: Cinematic visual-novel CG framing (e.g. dramatic close-up, atmospheric two-shot POV, golden-hour window framing, rain-lit neon reflection).
3. `"finale_quote"`: The defining quote or 1-sentence caption written on the Finale CG card in the gallery.
4. `"chat_summary"`: A 1-2 sentence summary of what happened during this in-person meet-up so the characters remember it when they go back to texting on TeleChat.

Return ONLY a valid JSON object:
{{
  "visual_prompt": "...",
  "camera_angle": "...",
  "finale_quote": "...",
  "chat_summary": "..."
}}"""


def _call_vn_json(user, prompt, scene=None, generation="normal"):
    _, model = ai_client.resolve(user, "chat")
    thinks = thinking.needs_leash(model, "default")
    pack = vn_story.prepare(user, scene, prompt, generation) if scene is not None else None
    params = dict(pack["params"]) if pack else {}
    params.setdefault("max_tokens", 4500 + (thinking.LEASH_ROOM if thinks else 0))
    params.setdefault("temperature", 0.82)
    messages = pack["messages"] if pack else [{"role": "user", "content": prompt}]
    for attempt in range(2):
        raw = ai_client.complete(user, "chat", messages, **params)
        parsed = messenger._read_json(raw)
        if isinstance(parsed, dict) and set(parsed).intersection(
                {"beats", "blocks", "choices", "summary", "visual_prompt", "chat_summary", "camera_angle"}):
            return parsed
        # Recover fully received beats without guessing the missing prose or JSON values.
        match = re.search(r'"(?:beats|blocks)"\s*:\s*\[', raw)
        if match:
            tail = raw[match.end():].lstrip()
            complete = []
            decoder = json.JSONDecoder()
            while tail:
                try:
                    beat, end = decoder.raw_decode(tail)
                except ValueError:
                    break
                if isinstance(beat, dict) and beat.get("text"):
                    complete.append(beat)
                tail = tail[end:].lstrip()
                if not tail.startswith(","):
                    break
                tail = tail[1:].lstrip()
            if complete:
                return {"beats": complete, "handoff": "user_turn"}
        logging.getLogger(__name__).warning("VN response could not be parsed (attempt %s): %r", attempt + 1, raw[:2000])
        messages = [*messages, {"role": "user", "content": "Return valid JSON with at most 8 complete beats. The previous response could not be parsed."}]
    raise ai_client.AIError("The model returned incomplete or invalid scene JSON twice. Your saved episode and draft are preserved. Retry the request.")


def _look_lines(look, worn=""):
    """A person's moods and clothes for the storyteller. `worn` is the outfit the story has changed them into."""
    if not look:
        return ("  Moods: neutral (no episode look yet: the stage shows only their name)\n"
                f"  Outfit: {worn or 'as in their description'}\n")
    if worn and worn != look.outfit:
        return (f"  Moods: {', '.join(sorted(look.moods or {'neutral': {}}))}\n"
                f"  Outfit now: {worn}\n")
    return (f"  Moods: {', '.join(sorted(look.moods or {'neutral': {}}))}\n"
            f"  Outfit ({look.name}): {look.outfit or 'as in their description'}\n")


def _build_char_roster(chars, user=None, context=None, looks=None, worn=None):
    lines = []
    looks = looks or {}
    worn = worn if isinstance(worn, dict) else {}
    for c in chars:
        p = messenger.char_profile(c)
        context = context or {}
        persona = messenger._character_block(c, user or c.author, u_name=context.get("user_name"),
                                             share=context.get("share_memory") if c.author_id == (user or c.author).pk else False)
        app = p.get("appearance_notes") or (c.description or "")
        lines.append(
            f"- {p['display_name']} (slug: `{c.slug}`, mode: {p['mode']})\n"
            + _look_lines(looks.get(c.slug), str(worn.get(c.slug) or ""))
            + f"  Appearance: {app}\n"
            f"  Persona & voice: {persona}"
        )
    if "user" in looks:
        lines.append("- The user's character (slug: `user`)\n" + _look_lines(looks["user"], str(worn.get("user") or "")).rstrip())
    return "\n".join(lines)


def _match_track(tracks, name):
    if not tracks:
        return {"id": "none", "name": "Silence", "url": ""}
    key = str(name or "").strip().lower()
    for t in tracks:
        if t.get("id", "").lower() == key or t["name"].lower() == key or (key and key in t["name"].lower()):
            return t
    return {"id": "none", "name": "Silence", "url": ""}


def _match_bg(bgs, name):
    if not bgs:
        return {"id": "none", "name": "Midnight Stage", "url": ""}
    key = str(name or "").strip().lower()
    for b in bgs:
        if b.get("id", "").lower() == key or b["name"].lower() == key or (key and key in b["name"].lower()):
            return b
    return {"id": "none", "name": "No backdrop", "url": ""}


def _enrich_beats(user, chars, raw_beats, looks=None, continuity=None, initial_stage=None, authoring_mode="roleplay",
                  user_participant=None):
    """Blocks from the storyteller as stage beats. Pictures come only from the episode's looks: a mood a look
    doesn't have shows its closest one, and someone without a look is shown by name only."""
    if not isinstance(raw_beats, list):
        raise ai_client.AIError("The model returned invalid scene blocks. Try again.")
    char_by_slug = {c.slug: c for c in chars}
    current = copy.deepcopy(initial_stage or {"continuity": continuity or {}})
    user_participant = user_participant or vn_story.user_participant(user, vn_support.scene_context(user))
    tracks, bgs = available_music_tracks(chars), available_backgrounds(chars)
    boxes = []
    for rb in raw_beats:
        if not isinstance(rb, dict) or not str(rb.get("text") or "").strip():
            continue
        txt = str(rb["text"]).strip()
        before = copy.deepcopy(current)
        change = rb.get("stage") if isinstance(rb.get("stage"), dict) else {}
        outfit_changes = []
        raw_changes = change.get("outfit_change")
        if isinstance(raw_changes, dict):
            for slug, outfit in raw_changes.items():
                person = char_by_slug.get(str(slug)) if str(slug) != "user" else None
                outfit = " ".join(str(outfit or "").split())[:600]
                if outfit and (person or (str(slug) == "user" and authoring_mode == "director")):
                    outfit_changes.append({"slug": str(slug), "outfit": outfit, "name": (
                        messenger.char_profile(person)["display_name"] if person else user_participant["name"])})
            if outfit_changes:
                # The new clothes are a story fact from here on; the picture follows once the user draws it.
                patch = dict(change.get("continuity") or {}) if isinstance(change.get("continuity"), dict) else {}
                patch["outfits"] = {**(patch.get("outfits") if isinstance(patch.get("outfits"), dict) else {}),
                                    **{c["slug"]: c["outfit"] for c in outfit_changes}}
                change = {**change, "continuity": patch}
        current = vn_story.advance_stage(current, change, tracks, bgs)
        sp_raw = str(rb.get("speaker_slug") or rb.get("speaker") or "").strip().strip("`").strip()
        sp_low = sp_raw.casefold()
        narrator = rb.get("kind") == "narration" or sp_low in ("narrator", "narration", "system", "")
        user_speaks = sp_low in ("user", user_participant["name"].casefold()) and not narrator
        speaker_char = char_by_slug.get(sp_raw) or next((c for c in chars if sp_low in (
            c.slug.casefold(), c.name.casefold(), messenger.char_profile(c)["display_name"].casefold())), None)
        if user_speaks and authoring_mode != "director":
            break
        if not narrator and not user_speaks and speaker_char is None:
            txt = f"{sp_raw}: {txt}"
            narrator = True
        side_character = speaker_char is None and not user_speaks and not sp_low in ("narrator", "narration", "system", "")
        stage_slug = str(rb.get("character_slug") or ("user" if user_speaks else speaker_char.slug if speaker_char else chars[0].slug))
        if stage_slug == "user" and authoring_mode != "director":
            stage_slug = speaker_char.slug if speaker_char else chars[0].slug
        emotion = sprites.clean_name(rb.get("emotion") or "neutral") or "neutral"
        faces = dict(current.get("faces") or {})
        if narrator and emotion == "neutral" and faces.get(stage_slug):
            emotion = faces[stage_slug]  # narration keeps the face they last showed; no flip back to neutral
        current["faces"] = {**faces, stage_slug: emotion}
        if stage_slug == "user":
            stage_name = user_participant["name"]
        else:
            stage_char = char_by_slug.get(stage_slug) or speaker_char or chars[0]
            stage_slug = stage_char.slug
            stage_name = messenger.char_profile(stage_char)["display_name"]
        look = (looks or {}).get(stage_slug)
        picture, shown = episode_looks.url(look, emotion)
        sp_info = {"url": picture, "emotion": shown, "asked": emotion, "look_id": look.pk if look else None}
        block_id = "vnb_" + uuid.uuid4().hex[:8]
        speaker = "narrator" if narrator else "user" if user_speaks else speaker_char.slug
        speaker_name = "Narrator" if narrator else user_participant["name"] if user_speaks else messenger.char_profile(speaker_char)["display_name"]
        for i, part in enumerate(vn_support.split_display_text(txt)):
            boxes.append({"id": "vnb_" + uuid.uuid4().hex[:8], "block_id": block_id,
                          "kind": "narration" if narrator else "dialogue", "generated": True,
                          "speaker": speaker, "speaker_slug": speaker, "speaker_name": speaker_name,
                          "character_slug": stage_slug, "character_name": stage_name, "emotion": sp_info["emotion"],
                          "asked_emotion": sp_info["asked"], "look_id": sp_info["look_id"],
                          "sprite_url": "" if side_character else sp_info["url"], "hide_sprite": side_character,
                          "text": part, "block_text": txt if i == 0 else "",
                          **({"outfit_change": outfit_changes} if outfit_changes and i == 0 else {}),
                          "original_text": (rb.get("original_text") or "") if i == 0 else "",
                          "stage": copy.deepcopy(current), "stage_before": before})
    return boxes


def start_scene(user, thread=None, characters=None, location_hint="", looks=None,
                direction="", polish_enabled=False, interaction_mode="mixed", authoring_mode="roleplay", pulse_event=None, generate_background=False):
    """
    Launch a new Visual Novel Meet-Up Scene from a TeleChat `thread` (or selected `characters`).
    Selects music & backdrop, generates the opening narrative, resolves or generates character sprites,
    and saves `active_scene` into the user's VN state.
    """
    if get_vn_state(user).get("active_scene"):
        raise ai_client.AIError("An episode is already open. Resume or finish it before starting another.")
    chars = list(characters or (thread.characters.all() if thread else []))
    if not chars:
        raise ai_client.AIError("Pick at least one character for the scene.")

    context = vn_support.scene_context(user, thread)
    if pulse_event:
        # Freeze the plan at launch. Calendar edits cannot rewrite an episode already in progress.
        context["clock"] = pulse_event["when_label"]
        context["pulse_event"] = copy.deepcopy(pulse_event)
        location_hint = location_hint or pulse_event["location"]
        direction = (f"PULSE PLAN: {pulse_event['title']}\nScheduled time: {pulse_event['when_label']}\n"
                     f"Place: {pulse_event['location']}\nPurpose: {pulse_event['purpose']}\n"
                     "Stage this meeting at its scheduled time. Do not assume it already happened. "
                     "Only the scheduled participants are present; group membership alone does not put someone in the room. "
                     "This scene does not advance the phone's clock or mark the calendar plan completed.\n" + direction)
    u_name = context["user_name"]
    now_local = timezone.localtime(timezone.now())
    clock_str = context["clock"]

    tracks = available_music_tracks(chars)
    bgs = available_backgrounds(chars)
    picked_looks = pick_looks(user, chars, looks, director=authoring_mode == "director")
    roster_text = _build_char_roster(chars, user, context, scene_looks(user, {"looks": picked_looks}))

    telechat_context = ("Earlier memory:\n" + context["memory"] + "\nThread scenario:\n" + context["scenario"]
                        + "\nConversation:\n" + context["conversation"])

    model_rules = ""  # Writing instructions come from the selected preset, without a second hidden baseline.

    seed = {"thread_id": thread.id if thread else None, "context": context, "direction": direction,
            "character_slugs": [c.slug for c in chars], "beats": [], "looks": picked_looks,
            "interaction_mode": interaction_mode if interaction_mode in vn_story.INTERACTIONS else "mixed",
            "authoring_mode": authoring_mode if authoring_mode in vn_story.AUTHORING else "roleplay",
            "user_participant": vn_story.user_participant(user, context),
            "phone_snapshot": copy.deepcopy(thread.data or {}) if thread else {}}
    if pulse_event:
        seed["pulse_event"] = copy.deepcopy(pulse_event)
    prompt = VN_SCENE_PROMPT.format(
        user=u_name,
        clock=clock_str,
        model_rules=model_rules,
        music_list="\n".join(f"- {t['name']} (id: {t['id']})" for t in tracks) or "- Default Theme",
        bg_list="\n".join(f"- {b['name']} (id: {b['id']})" for b in bgs) or "- Default Backdrop",
        user_persona=context["persona"],
        char_roster=roster_text,
        telechat_context=telechat_context,
        scene_history="(Scene is just beginning — set the stage as they meet!)",
        step_input=(location_hint or "Begin the in-person scene right where the latest texts left off.")
                   + "\nUser's writing directions: " + direction,
    )

    parsed = _call_vn_json(user, prompt, seed)
    chosen_music = _match_track(tracks, parsed.get("music_id") or parsed.get("music"))
    chosen_bg = _match_bg(bgs, parsed.get("background_id") or parsed.get("background"))
    raw_blocks = parsed.get("blocks") or parsed.get("beats") or []
    raw_blocks, polish_error = vn_support.polish_blocks(user, raw_blocks, telechat_context, polish_enabled)
    continuity = {"time": context["clock"]}
    beats = _enrich_beats(user, chars, raw_blocks, looks=scene_looks(user, seed), continuity=continuity,
                        initial_stage={"background": chosen_bg, "music": chosen_music, "location": parsed.get("location") or location_hint,
                                       "continuity": continuity, "looks": dict(picked_looks)},
                        authoring_mode=seed["authoring_mode"], user_participant=seed["user_participant"])
    if not beats:
        raise ai_client.AIError("The model returned no scene text. Try starting the episode again.")

    scene = {
        **seed,
        "id": "vns_" + uuid.uuid4().hex[:8],
        "thread_id": thread.id if thread else None,
        "context": context,
        "direction": direction,
        "polish_enabled": bool(polish_enabled),
        "polish_error": polish_error,
        "continuity": continuity,
        "character_slugs": [c.slug for c in chars],
        "character_names": [messenger.char_profile(c)["display_name"] for c in chars],
        "title": str(parsed.get("title") or f"Meet-Up with {chars[0].name}").strip()[:120],
        "location": str(parsed.get("location") or location_hint or now_local.strftime("%H:%M")).strip()[:120],
        "background": chosen_bg,
        "music": chosen_music,
        "handoff": parsed.get("handoff") if parsed.get("handoff") in ("user_turn", "auto_continue", "climax_ready") else "user_turn",
        "handoff_prompt": str(parsed.get("handoff_prompt") or "What do you do or say?").strip()[:140],
        "choices": [str(ch).strip()[:120] for ch in (parsed.get("choices") or []) if str(ch or "").strip()][:3],
        "beats": list(beats),
        "current_beats": list(beats),
        "history": list(beats),
        "started_at": now_local.strftime("%d %b %H:%M"),
        "ts": time.time(),
    }
    if generate_background:
        opening = beats[0]["stage"]
        location = opening.get("location") or scene["location"]
        try:
            image, cost = messenger.make_picture(user, (
                f"Create an immersive visual novel background of {location}. "
                f"Scene context: {beats[0]['text']}\n"
                f"Setting details: {json.dumps(opening.get('continuity') or {}, ensure_ascii=False)}\n"
                "Environment only, no people, no portraits, no lettering. Wide establishing shot."
            ))
            path = default_storage.save(
                f"messenger/vn_backgrounds/{user.pk}/{uuid.uuid4().hex}.png", ContentFile(image))
            generated_bg = {"id": "generated_" + scene["id"], "name": location,
                            "url": default_storage.url(path)}
            original_bg = opening.get("background")
            for beat in beats:
                for key in ("stage", "stage_before"):
                    if beat[key].get("background") == original_bg:
                        beat[key]["background"] = copy.deepcopy(generated_bg)
        except ai_client.AIError as exc:
            scene["background_error"] = "Episode ready, but the background could not be generated: " + str(exc)
    scene["initial_stage"] = copy.deepcopy(beats[0]["stage_before"])
    scene["current_stage"] = vn_story.finish_timeline(beats, parsed.get("continuity"))
    scene["continuity"] = scene["current_stage"]["continuity"]
    scene.update({k: scene["current_stage"].get(k) for k in ("background", "music", "location")})
    if scene["interaction_mode"] == "write": scene["choices"] = []
    scene["choice_cache"] = list(scene["choices"])
    save_vn_state(user, {"active_scene": scene}, expected=("", 0))
    return scene


def step_scene(user, user_input="", base_scene=None, generation="normal", turn_direction="", save_updates=None):
    """
    Advance the active Visual Novel scene by one turn (either with `user_input` action/dialogue or
    continuing automatically when `user_input` is empty).
    """
    state = get_vn_state(user)
    scene = copy.deepcopy(base_scene or state.get("active_scene"))
    if not scene:
        raise ai_client.AIError("No active Visual Novel scene. Start a scene first.")
    expected = (scene["id"], scene.get("revision", 0))

    chars = vn_support.scene_characters(user, scene.get("character_slugs") or [])
    if not chars:
        raise ai_client.AIError("Scene characters not found.")


    context = scene.get("context") or vn_support.scene_context(user, vn_support.linked_thread(user, scene))
    scene["context"] = context
    u_name = context["user_name"]
    clock_str = (scene.get("continuity") or {}).get("time") or context["clock"]

    history = list(scene.get("beats") or scene.get("history") or [])
    if user_input and user_input.strip():
        directing = scene.get("authoring_mode") == "director"
        c0 = chars[0]
        last_beat = history[-1] if history else {}
        user_beat = {
            "id": "vnb_" + uuid.uuid4().hex[:8],
            "kind": "direction" if directing else "dialogue",
            "speaker": "director" if directing else "user",
            "speaker_slug": "director" if directing else "user",
            "speaker_name": "Director" if directing else u_name,
            "character_slug": last_beat.get("character_slug") or c0.slug,
            "character_name": last_beat.get("character_name") or c0.name,
            "emotion": last_beat.get("emotion") or "neutral",
            "sprite_url": last_beat.get("sprite_url") or "",
            "text": user_input.strip(),
            "generated": False, "stage": vn_story.stage_of(scene), "stage_before": vn_story.stage_of(scene),
        }
        history.append(user_beat)

    hist_lines = []
    for b in history[-40:]:
        emo_tag = f" [{b.get('emotion')}]" if b.get("speaker_slug") not in ("narrator", "user") else ""
        hist_lines.append(f"- {b.get('speaker_name') or b.get('speaker')}{emo_tag}: {b.get('text')}")

    tracks = available_music_tracks(chars)
    bgs = available_backgrounds(chars)
    looks = scene_looks(user, scene)
    roster_text = _build_char_roster(chars, user, context, looks, (scene.get("continuity") or {}).get("outfits"))
    model_rules = ""  # Writing instructions come from the selected preset, without a second hidden baseline.

    step_dir = (
        (f"Director's instruction (not spoken dialogue): {user_input.strip()}. Follow this direction in the scene."
         if scene.get("authoring_mode") == "director"
         else f"{u_name} just did/said: \"{user_input.strip()}\". Respond until the next natural opportunity for input.")
        if (user_input and user_input.strip())
        else "Continue unfolding the scene until the next natural opportunity for input."
    )

    prompt = VN_SCENE_PROMPT.format(
        user=u_name,
        clock=clock_str,
        model_rules=model_rules,
        music_list="\n".join(f"- {t['name']} (id: {t['id']})" for t in tracks) or "- Default Theme",
        bg_list="\n".join(f"- {b['name']} (id: {b['id']})" for b in bgs) or "- Default Backdrop",
        user_persona=context["persona"],
        char_roster=roster_text,
        telechat_context=json.dumps(context, ensure_ascii=False),
        scene_history=("Continuity record (carry earlier facts forward):\n"
                       + json.dumps(scene.get("continuity") or {}, ensure_ascii=False)
                       + "\nRecent transcript:\n" + "\n".join(hist_lines)),
        step_input=step_dir + "\nUser's writing directions: " + scene.get("direction", ""),
    )

    scene["beats"] = history
    parsed = _call_vn_json(user, prompt + "\n" + turn_direction, scene, generation)
    raw_blocks = parsed.get("blocks") or parsed.get("beats") or []
    raw_blocks, scene["polish_error"] = vn_support.polish_blocks(
        user, raw_blocks, prompt, scene.get("polish_enabled", False))
    continuity = vn_support.continuity_update(scene.get("continuity"), parsed.get("continuity"))
    new_beats = _enrich_beats(user, chars, raw_blocks, looks=looks, continuity=continuity,
                            initial_stage=vn_story.stage_of(scene), authoring_mode=scene.get("authoring_mode", "roleplay"),
                            user_participant=scene.get("user_participant"))
    if not new_beats:
        raise ai_client.AIError("The model returned no scene text. Your previous turn is still saved; try again.")
    history.extend(new_beats)
    scene["current_beats"] = new_beats
    scene["beats"] = history
    scene["history"] = history
    scene["current_stage"] = vn_story.finish_timeline(new_beats, parsed.get("continuity"))
    scene["continuity"] = scene["current_stage"]["continuity"]
    scene.update({k: scene["current_stage"].get(k) for k in ("background", "music", "location")})
    scene["handoff"] = parsed.get("handoff") if parsed.get("handoff") in ("user_turn", "auto_continue", "climax_ready") else "user_turn"
    scene["handoff_prompt"] = str(parsed.get("handoff_prompt") or "What do you do or say?").strip()[:140]
    scene["choices"] = [str(ch).strip()[:120] for ch in (parsed.get("choices") or []) if str(ch or "").strip()][:3]

    if scene.get("interaction_mode") == "write": scene["choices"] = []
    scene["choice_cache"] = list(scene["choices"])
    save_vn_state(user, {**(save_updates or {}), "active_scene": scene}, expected=expected)
    return scene, new_beats


def suggest_choices(user):
    """Offer options at the current endpoint without advancing the story or generating images."""
    from mainapp import vn_history
    _, scene = vn_history.current(user)
    if scene.get("interaction_mode") == "write":
        raise ai_client.AIError("Switch to choices or mixed mode before requesting options.")
    expected = (scene["id"], scene.get("revision", 0))
    prompt = ("Suggest up to three distinct, scene-specific actions or lines of dialogue the user could choose "
              "at the current moment. Preserve character, knowledge and authorship mode. Do not advance the scene, "
              "invent an event, change continuity or write a continuation. Return ONLY JSON {\"choices\": [\"option\"]}.")
    result = _call_vn_json(user, prompt, scene)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or any(not isinstance(c, str) or not c.strip() for c in choices):
        raise ai_client.AIError("The model returned no usable options. The episode is unchanged.")
    scene["choices"] = [c.strip()[:240] for c in choices[:3]]
    scene["choice_cache"] = list(scene["choices"])
    if scene.get("last_request"):
        scene["last_request"]["operation"] = "suggest_choices"
    save_vn_state(user, {"active_scene": scene}, expected=expected)
    return scene


def add_look_mood(user, beat_id="", emotion=""):
    """Draw one more mood for the look a beat shows, as an edit of that look's neutral picture (you press the
    button; it is never automatic). Beats of the same look that asked for this mood switch to it.

    Returns (scene, packed look, cost).
    """
    state = get_vn_state(user)
    scene = state.get("active_scene")
    if not scene:
        raise ai_client.AIError("No episode is open.")
    expected = (scene["id"], scene.get("revision", 0))
    beat = next((b for b in scene.get("beats", []) if b.get("id") == beat_id), None)
    if not beat or not beat.get("look_id"):
        raise ai_client.AIError("This passage has no episode look to add a mood to.")
    look = EpisodeLook.objects.filter(author=user, pk=beat["look_id"]).first()
    if not look:
        raise ai_client.AIError("That look no longer exists.")
    mood = episode_looks.clean_mood(emotion or beat.get("asked_emotion") or beat.get("emotion"))
    cost, errors = episode_looks.add_moods(user, look, [mood])
    if mood not in (look.moods or {}):
        raise ai_client.AIError(errors[0] if errors else "The mood could not be drawn.")
    picture, _ = episode_looks.url(look, mood)
    group = beat.get("block_id") or beat.get("id")
    for collection in (scene.get("beats") or [], scene.get("current_beats") or [], scene.get("history") or []):
        for b in collection:
            if b.get("look_id") != look.pk:
                continue
            if (b.get("block_id") or b.get("id")) == group or episode_looks.clean_mood(b.get("asked_emotion") or "") == mood:
                b["sprite_url"] = picture
                b["emotion"] = mood
    save_vn_state(user, {"active_scene": scene}, expected=expected)
    return scene, episode_looks.pack(look), cost


def change_look(user, beat_id, key, look_id=None, name="", outfit="", keep=False):
    """From one passage on, dress `key` (a character slug or "user") in another look.

    `look_id`: one of their existing looks in the same setting (no pictures drawn). `outfit`: a new look edited
    from the one they wear now (one picture per mood). `keep`: leave the picture as it is and only close the
    passage's outfit-change note. Earlier passages keep what they showed, so reading back stays true.
    Returns (scene, cost, errors).
    """
    state = get_vn_state(user)
    scene = state.get("active_scene")
    if not scene:
        raise ai_client.AIError("No episode is open.")
    expected = (scene["id"], scene.get("revision", 0))
    beats = scene.get("beats") or []
    start = next((i for i, b in enumerate(beats) if b.get("id") == beat_id), None)
    if start is None:
        raise ai_client.AIError("That passage isn't in this episode any more.")
    group = beats[start].get("block_id") or beats[start].get("id")
    start = next(i for i, b in enumerate(beats) if (b.get("block_id") or b.get("id")) == group)
    cost, errors = 0.0, []
    if not keep:
        worn_id = ((beats[start].get("stage") or {}).get("looks") or {}).get(key)
        worn = EpisodeLook.objects.filter(author=user, pk=worn_id or 0).first()
        if look_id:
            new = EpisodeLook.objects.filter(author=user, pk=look_id).first()
            if not new or (new.character.slug if new.character_id else "user") != key or (worn and new.setting != worn.setting):
                raise ai_client.AIError("Pick one of their own looks for this setting.")
        elif outfit.strip():
            if not worn:
                raise ai_client.AIError("They have no look in this episode yet: make one on the launch screen first.")
            new, cost, errors = episode_looks.restyle(user, worn, name, outfit)
        else:
            raise ai_client.AIError("Choose a look or describe the new outfit.")
        for i, b in enumerate(beats[start:], start):
            for field in ("stage", "stage_before") if i > start else ("stage",):
                if isinstance(b.get(field), dict):
                    b[field]["looks"] = {**(b[field].get("looks") or {}), key: new.pk}
            if b.get("character_slug") == key and not b.get("hide_sprite"):
                b["sprite_url"], b["emotion"] = episode_looks.url(new, b.get("asked_emotion") or b.get("emotion"))
                b["look_id"] = new.pk
        if isinstance(scene.get("current_stage"), dict):
            scene["current_stage"]["looks"] = {**(scene["current_stage"].get("looks") or {}), key: new.pk}
        scene["looks"] = {**(scene.get("looks") or {}), key: new.pk}
    for b in beats[start:]:
        if (b.get("block_id") or b.get("id")) == group and b.get("outfit_change"):
            b["outfit_change"] = [c for c in b["outfit_change"] if c.get("slug") != key]
    for collection in ("history", "current_beats"):
        by_id = {b["id"]: b for b in beats}
        scene[collection] = [by_id.get(b.get("id"), b) for b in scene.get(collection) or []]
    save_vn_state(user, {"active_scene": scene}, expected=expected)
    return scene, cost, errors


def finish_scene_with_cg(user, cg_hint="", capture_image=True):
    """
    End the active Visual Novel scene by generating a full widescreen Finale Event CG image
    (using the character's 1 neutral + up to 4 extra references and art style lock),
    saving the completed scene + CG into the Gallery, and logging a memory notice in the linked TeleChat thread.
    """
    state = get_vn_state(user)
    scene = state.get("active_scene")
    if not scene:
        raise ai_client.AIError("No active Visual Novel scene to finish.")
    expected = (scene["id"], scene.get("revision", 0))

    chars = vn_support.scene_characters(user, scene.get("character_slugs") or [])
    if not chars:
        raise ai_client.AIError("Scene character not found.")
    lead_char = chars[0]
    lead_prof = messenger.char_profile(lead_char)

    from mainapp.cards import user_name
    u_name = (scene.get("context") or {}).get("user_name") or user_name(user)

    transcript_lines = []
    transcript_lines.append("Cumulative continuity: " + json.dumps(scene.get("continuity") or {}, ensure_ascii=False))
    for b in (scene.get("beats") or scene.get("history") or [])[-40:]:
        if b.get("kind") == "direction":
            continue
        transcript_lines.append(f"{b.get('speaker_name') or b.get('speaker')}: {b.get('text')}")

    char_visuals = []
    for c in chars:
        p = messenger.char_profile(c)
        char_visuals.append(
            f"- {p['display_name']}: {p.get('appearance_notes') or (c.description or '')[:400]} "
            f"(Art style: {p.get('art_style_notes') or 'match reference portrait style'})"
        )

    prompt = FINALE_CG_PROMPT.format(
        user=u_name,
        char_names=", ".join(scene.get("character_names") or [lead_char.name]),
        title=scene.get("title"),
        location=scene.get("location"),
        char_visuals="\n".join(char_visuals),
        transcript="\n".join(transcript_lines) or "(Short meet-up scene)",
        cg_hint=cg_hint or "Capture the emotional peak or parting moment of this scene.",
    )

    try:
        cg_meta = _call_vn_json(user, prompt)
    except Exception:
        cg_meta = {}

    visual_prompt = str(cg_meta.get("visual_prompt") or cg_hint or f"Cinematic Visual Novel Event CG of {lead_char.name} at {scene.get('location')}").strip()
    camera_angle = str(cg_meta.get("camera_angle") or "cinematic widescreen visual novel event CG composition, expressive lighting and depth").strip()
    finale_quote = str(
        cg_meta.get("finale_quote")
        or cg_meta.get("quote")
        or (scene.get("beats")[-1].get("text") if scene.get("beats") else scene.get("title"))
    ).strip()[:220]
    chat_summary = str(
        cg_meta.get("chat_summary")
        or cg_meta.get("summary")
        or (scene.get("continuity") or {}).get("summary")
        or f"Met up in person at {scene.get('location')} ({scene.get('title')})."
    ).strip()

    art_style = lead_prof.get("art_style_notes") or "exact same visual art style, brushwork, linework, shading, and color palette as the attached reference image(s)"
    # Give every participant a primary reference before filling the remaining slots.
    refs = []
    extra_refs = []
    ref_labels = []
    looks = scene_looks(user, scene)
    for c in chars:
        worn = _look_reference(looks[c.slug]) if c.slug in looks else None
        images = ([worn] if worn else []) + episode_looks.references(user, c, episode_looks.setting_for(c))[:2]
        if images and len(refs) < 5:
            refs.append(images[0])
            ref_labels.append(f"Reference {len(refs)}: {messenger.char_profile(c)['display_name']}")
            extra_refs.extend(images[1:])
    player = scene.get("user_participant") or {}
    if player:
        char_visuals.append(f"- {player.get('name')}: {player.get('persona') or 'match their reference portrait'}")
        if (looks.get("user") or player.get("avatar_url")) and len(refs) < 5:
            reference = (_look_reference(looks["user"]) if looks.get("user") else None) or \
                messenger._read_storage_image(player.get("avatar_url") or "")
            if reference:
                refs.append(reference)
                ref_labels.append(f"Reference {len(refs)}: {player['name']} (the user's character)")
    refs.extend(extra_refs[:max(0, 5 - len(refs))])

    full_cg_prompt = (
        f"Create a full-scene Visual Novel Event CG illustration featuring {', '.join(scene.get('character_names') or [lead_char.name])} at {scene.get('location')}.\n"
        f"CRITICAL IDENTITY & STYLE LOCK: Keep the EXACT same face, hair, eyes, proportions, and visual art style ({art_style}) as the attached reference image(s).\n"
        f"Camera angle & framing: {camera_angle}.\n"
        f"Reference identities: {'; '.join(ref_labels)}. Additional references support these same identities.\n"
        f"Participant appearances: {'; '.join(char_visuals)}\n"
        f"Established setting, clothing, positions and story time (override reference outfits where changed): {json.dumps(scene.get('continuity') or {}, ensure_ascii=False)}\n"
        f"Event CG scene: {visual_prompt}"
    )

    cg_url, cost, image_error = "", 0, ""
    if capture_image:
        try:
            img_bytes, cost = messenger.make_picture(user, full_cg_prompt, references=refs)
            rel_path = f"messenger/vn_cg/{lead_char.slug}-cg-{uuid.uuid4().hex[:8]}.png"
            saved_path = default_storage.save(rel_path, ContentFile(img_bytes))
            cg_url = default_storage.url(saved_path)
        except ai_client.AIError as exc:
            image_error = str(exc)

    now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
    finished_str = timezone.localtime(timezone.now()).strftime("%d %b %Y · %H:%M")
    all_beats = scene.get("beats") or scene.get("history") or []
    gallery_entry = {
        "id": scene["id"],
        "episode": copy.deepcopy(scene),
        "thread_id": scene.get("thread_id"),
        "title": scene.get("title"),
        "location": scene.get("location"),
        "character_slugs": scene.get("character_slugs"),
        "character_names": scene.get("character_names"),
        "cg_url": cg_url,
        "image_error": image_error,
        "continuity": scene.get("continuity") or {},
        "cg_prompt": visual_prompt,
        "quote": finale_quote,
        "finale_quote": finale_quote,
        "summary": chat_summary,
        "chat_summary": chat_summary,
        "music": scene.get("music"),
        "background": scene.get("background"),
        "beats": all_beats,
        "transcript": all_beats,
        "finished_at": finished_str,
        "completed_at": finished_str,
        "ts": time.time(),
        "cost": cost,
    }

    with transaction.atomic():
        gallery = [gallery_entry] + [g for g in state["gallery"] if g.get("id") != scene["id"]]
        save_vn_state(user, {"active_scene": None, "gallery": gallery}, expected=expected)

        # Write a scene completion notice & CG bubble into the linked TeleChat thread so phone chat remembers the meet-up!
        if scene.get("thread_id"):
            thread = MessengerThread.objects.select_for_update().filter(user=user, id=scene["thread_id"]).prefetch_related("characters").first()
            if thread:
                td = messenger.thread_data(thread)
                td["messages"].append({
                    "id": uuid.uuid4().hex[:10],
                    "role": "system",
                    "text": f"🎬 Meet-Up Scene Completed: \"{scene.get('title')}\" ({scene.get('location')}) — {chat_summary}",
                    "time": now_hm,
                    "ts": time.time(),
                })
                if cg_url:
                    td["messages"].append({
                        "id": uuid.uuid4().hex[:10],
                        "role": "assistant",
                        "sender_slug": lead_char.slug,
                        "sender_name": lead_prof["display_name"],
                        "text": f"🎬 *{finale_quote}*",
                        "photo": {
                            "kind": "casual",
                            "prompt": visual_prompt,
                            "caption": f"🎬 Scene Finale CG · {scene.get('title')}",
                            "url": cg_url,
                        },
                        "time": now_hm,
                        "ts": time.time(),
                        "reactions": {"❤️": [lead_prof["display_name"]]},
                    })
                td["memory"] = (td.get("memory") or "") + (
                    f"\nCompleted in-person episode: {scene.get('title')} at {scene.get('location')}. "
                    f"{chat_summary}\nThe next phone exchange follows this meeting; do not replay it as a future plan."
                )
                messenger.save_thread_data(thread, td)

    return gallery_entry, float(cost or 0.0)
