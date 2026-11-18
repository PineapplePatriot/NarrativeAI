"""
Subtext / Chirp — Micro-Community, Locked Burner Accounts & AITA Social Feed for the Digital Screen Hub.

Connects directly to TeleChat (`mainapp/messenger.py`):
- Reads recent TeleChat conversations and the real-time clock so characters subtweet what just happened in chat.
- Supports 3 post types:
  * 🌐 Public Main (`public`) — the character's public @handle
  * 🔒 Locked Burner / Close Friends (`burner`) — unfiltered 2 AM thoughts, petty subtweets, vulnerable rants (`@handle_priv`)
  * ⚖️ AITA & Confessions (`aita`) — "AITA for..." threads with NTA / YTA / ESH voting & cross-character comment wars
- Includes "✈️ Slide into DMs (Forward to TeleChat)" so the user can forward any post or burner subtweet straight into a TeleChat DM and confront or tease the character.
"""

import json
import logging
import re
import time
import uuid

from django.utils import timezone

from mainapp import ai_client, messenger
from mainapp.models import Character, ChatSettings, MessengerThread

log = logging.getLogger(__name__)

SUBTEXT_REACTIONS = ["❤️", "🔥", "💀", "👀", "🤡", "💔"]


def _get_settings_obj(user):
    settings_obj, _ = ChatSettings.objects.get_or_create(author=user)
    if not isinstance(settings_obj.appearance, dict):
        settings_obj.appearance = {}
    return settings_obj


def burner_handle_for(character):
    """Return a character's locked burner handle (e.g. `@dr_zandik_priv`)."""
    prof = messenger.char_profile(character)
    custom = str((character.messenger_profile or {}).get("burner_handle") or "").strip()
    if custom:
        return custom if custom.startswith("@") else f"@{custom}"
    base = prof.get("handle", "@character").lstrip("@")
    return f"@{base}_priv"


def get_subtext_state(user, characters=None):
    """Return `{posts: [...], burner_handles: {slug: handle}}` for the user."""
    settings_obj = _get_settings_obj(user)
    raw = (settings_obj.appearance or {}).get("subtext")
    if not isinstance(raw, dict):
        raw = {}
    posts = [p for p in (raw.get("posts") or []) if isinstance(p, dict)]

    # Seed an initial welcome post from the user's first character if the feed is completely empty
    if not posts and characters:
        c0 = characters[0]
        p0 = messenger.char_profile(c0)
        now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
        seed_post = {
            "id": "st_" + uuid.uuid4().hex[:8],
            "author_slug": c0.slug,
            "author_name": p0["display_name"],
            "author_avatar": p0["avatar_url"],
            "status_emoji": p0["status_emoji"],
            "handle": burner_handle_for(c0),
            "visibility": "burner",
            "title": "",
            "text": p0.get("bio") or f"Set up this account so fewer people bother me during work hours.",
            "subtweet_note": "Locked Close-Friends Burner",
            "photo": None,
            "aita_votes": {"nta": 0, "yta": 0, "esh": 0, "user_vote": ""},
            "reactions": {"👀": [p0["display_name"]]},
            "comments": [],
            "time": now_hm,
            "ts": time.time(),
        }
        posts = [seed_post]
        save_subtext_state(user, {"posts": posts})

    burner_map = {}
    for c in (characters or []):
        burner_map[c.slug] = burner_handle_for(c)

    return {
        "posts": posts[:80],
        "burner_handles": burner_map,
        "reactions_palette": SUBTEXT_REACTIONS,
    }


def save_subtext_state(user, state_updates):
    settings_obj = _get_settings_obj(user)
    app = dict(settings_obj.appearance or {})
    cur = dict(app.get("subtext") or {})
    cur.update(state_updates)
    if "posts" in cur and isinstance(cur["posts"], list):
        cur["posts"] = cur["posts"][:80]
    app["subtext"] = cur
    settings_obj.appearance = app
    settings_obj.save(update_fields=["appearance"])
    return cur


def recent_telechat_digest(user, chars):
    """
    Build a concise digest of recent TeleChat messages involving `chars` so Subtext posts
    can subtweet, complain about, or reference what just happened in chat.
    """
    slug_set = {c.slug for c in chars}
    threads = list(MessengerThread.objects.filter(user=user).prefetch_related("characters")[:8])
    snippets = []
    for t in threads:
        t_chars = list(t.characters.all())
        if not any(c.slug in slug_set for c in t_chars):
            continue
        td = messenger.thread_data(t)
        msgs = (td.get("messages") or [])[-6:]
        if not msgs:
            continue
        lines = []
        for m in msgs:
            if m.get("role") == "system":
                continue
            sender = m.get("sender_name") or ("User" if m.get("role") == "user" else "Character")
            txt = (m.get("text") or "").strip()
            if m.get("photo"):
                txt += f" [sent photo: {m['photo'].get('caption') or m['photo'].get('prompt') or 'photo'}]"
            if txt:
                lines.append(f"  - [{m.get('time', '')}] {sender}: {txt[:160]}")
        if lines:
            rt = messenger.real_time_context(t)
            snippets.append(
                f"Recent TeleChat thread '{t.title}' (last activity: {rt['elapsed_text']}):\n" + "\n".join(lines)
            )
    return "\n\n".join(snippets[:3]) if snippets else "No recent TeleChat messages yet."


SUBTEXT_SAFEGUARDS = """SUBTEXT SOCIAL FEED & FRANKENWIRE SAFEGUARDS:
1. METHOD ACTING & AUTHENTIC INTERNET VOICE:
   - [Embody_Before_Posting]: Lock onto each character's actual pride, pettiness, dry humour, current mood, and relationship with {user} and the other characters before writing.
   - NO CORPORATE / AI INFLUENCER SLOP: Never write generic hashtags (#blessed, #livingmylife, #grindset), motivational quotes, or therapy-speak ("Reminder that your feelings are valid!").
   - NO STAGE DIRECTIONS: Never write third-person narration or actions in asterisks (*sighs and types*, *rolls eyes*). Write ONLY the actual post text and comment text.
   - DISTINCT ACCOUNT MODES:
     * `public` (🌐 Main Account): What the character is willing to say in public—dry observations, complaints about work/people, subtle flexes, announcements, or snapshots of their food/desk/scenery.
     * `burner` (🔒 Locked Alt / Close Friends): What they post at 2 AM on their locked private account—unfiltered venting, obvious subtweets about {user} or another character without naming them directly, petty grievances, or vulnerable admissions they would deny on main.
     * `aita` (⚖️ AITA / Anonymous Board): An overly specific "AITA for..." post where the character tries to sound anonymous or reasonable while describing a ridiculous or petty situation, and other characters immediately clock who wrote it in the comments and vote `NTA`, `YTA`, or `ESH`.
2. CROSS-CHARACTER COLLISIONS:
   - In the `comments` array, have other characters reply in their own distinct voice—roasting, correcting, exposing, agreeing, or starting petty arguments in the replies."""


GENERATE_WAVE_PROMPT = """You are generating a wave of new posts and cross-character reply threads on **Subtext** (the micro-blogging & burner-account app on {user}'s Digital Screen).

Current Real-World Clock: {clock}
{safeguards}

{model_rules}

USER PROFILE:
- Name: {user} ({user_handle}) — Bio: {user_bio}
- Who {user} is: {user_persona}

CHARACTERS AVAILABLE FOR THIS WAVE:
{char_roster}

RECENT TELECHAT CONVERSATIONS (characters can subtweet or react to what happened here!):
{telechat_digest}

REQUESTED FEED MODE: {feed_mode}
USER TOPIC / VIBE HINT: {topic_hint}

Generate 1 to 2 posts (and 1 to 3 cross-character comments on each post).
Return ONLY a valid JSON object matching this exact structure (no markdown fences):
{{
  "posts": [
    {{
      "author_slug": "exact slug of the posting character",
      "visibility": "public" | "burner" | "aita",
      "title": "Empty string for public/burner, OR 'AITA for ...' title when visibility is 'aita'",
      "text": "The post body (1 to 4 sentences, pure in-character social post, no *asterisks*)",
      "subtweet_note": "Short 3-6 word badge explaining the vibe, e.g. 'Subtweeting last night\\'s chat', 'Locked 2 AM rant', 'Public announcement', 'Anonymous AITA thread'",
      "photo_prompt": "Optional: if this post naturally includes a photo they snapped (food, coffee, messy desk, scenery, or candid selfie), describe the concrete visual scene in 1 sentence; otherwise empty string",
      "comments": [
        {{
          "author_slug": "exact slug of a character replying",
          "is_burner": false,
          "verdict": "NTA" | "YTA" | "ESH" | "",
          "text": "Their reply in the comments (1-2 sharp sentences, no *asterisks*)"
        }}
      ]
    }}
  ]
}}"""


GENERATE_REPLIES_PROMPT = """You are generating in-character comment replies on **Subtext** (the social & burner-account feed on {user}'s Digital Screen).

Current Real-World Clock: {clock}
{safeguards}

{model_rules}

CHARACTERS AVAILABLE TO REPLY:
{char_roster}

RECENT TELECHAT CONTEXT:
{telechat_digest}

TARGET POST BEING REPLIED TO:
- Author: {post_author} ({post_handle}) [{post_visibility}]
- Title: {post_title}
- Text: "{post_text}"
- Existing comments so far:
{existing_comments}

Generate 1 to 3 new comment replies from the available characters reacting to the post (and/or replying to the latest comment from {user}).
If the post visibility is `aita`, each commenter should include a `"verdict"` (`"NTA"`, `"YTA"`, or `"ESH"`).
Return ONLY a valid JSON object (no markdown fences):
{{
  "comments": [
    {{
      "author_slug": "exact character slug",
      "is_burner": false,
      "verdict": "NTA" | "YTA" | "ESH" | "",
      "text": "1-2 sentences of in-character comment reply, no *asterisks*"
    }}
  ],
  "reactions": ["🔥", "💀"]
}}"""


def _build_roster_block(chars, user):
    lines = []
    for c in chars:
        p = messenger.char_profile(c)
        b_handle = burner_handle_for(c)
        persona = p.get("modern_persona") or c.personality or (c.description or "")[:350]
        style = p.get("texting_style") or "Distinct in-character voice."
        lines.append(
            f"- {p['display_name']} (slug: `{c.slug}`, main handle: `{p['handle']}`, burner handle: `{b_handle}`)\n"
            f"  Bio: {p.get('bio') or 'No bio'}\n"
            f"  Persona: {persona[:400]}\n"
            f"  Texting/posting fingerprint: {style[:250]}"
        )
    return "\n".join(lines)


def _match_char_by_slug_or_name(chars, key):
    if not key:
        return chars[0]
    k = str(key).strip().lower().lstrip("@")
    for c in chars:
        p = messenger.char_profile(c)
        if (
            c.slug.lower() == k
            or c.name.lower() == k
            or p["display_name"].lower() == k
            or p["handle"].lower().lstrip("@") == k
            or burner_handle_for(c).lower().lstrip("@") == k
        ):
            return c
    return chars[0]


def generate_wave(user, chars, mode="mix", topic_hint=""):
    """
    Call the user's active chat model to generate 1–2 new Subtext posts (public, locked burner, or AITA)
    with cross-character comment threads, save them to the top of the user's feed, and return the new posts.
    """
    if not chars:
        raise ai_client.AIError("Add or select at least one character first.")
    from mainapp.cards import user_name
    u_name = user_name(user)
    u_prof = messenger.user_profile(user)
    now_local = timezone.localtime(timezone.now())
    clock_str = now_local.strftime("%A %H:%M")
    now_hm = now_local.strftime("%H:%M")

    model_info = messenger.active_model_texting_rules(user)
    model_rules = f"ACTIVE MODEL CALIBRATION ({model_info['label']}):\n{model_info['rules']}" if model_info.get("rules") else ""

    mode_desc = {
        "mix": "Mix of 🌐 Public Main posts and 🔒 Locked Burner subtweets.",
        "burner": "ONLY 🔒 Locked Burner (`burner`) posts — unfiltered 2 AM thoughts, subtweeting recent TeleChat messages or other characters.",
        "aita": "An `aita` ('AITA for...') thread where a character describes a petty or dramatic situation and other characters roast/judge them with NTA/YTA/ESH verdicts.",
        "subtweet": "Directly subtweet or react to the recent TeleChat conversation digest without naming the user outright.",
    }.get(mode, "Mix of public and burner posts.")

    prompt = GENERATE_WAVE_PROMPT.format(
        user=u_name,
        clock=clock_str,
        safeguards=SUBTEXT_SAFEGUARDS.format(user=u_name),
        model_rules=model_rules,
        user_handle=u_prof.get("handle", "@you"),
        user_bio=u_prof.get("bio", ""),
        user_persona=(getattr(user, "persona_description", "") or "")[:400],
        char_roster=_build_roster_block(chars, user),
        telechat_digest=recent_telechat_digest(user, chars),
        feed_mode=mode_desc,
        topic_hint=(topic_hint or "Follow current time of day, character rivalries, and recent TeleChat activity.")[:500],
    )

    raw_reply = ai_client.complete(user, "chat", [{"role": "user", "content": prompt}], max_tokens=1500, temperature=0.85)
    match = re.search(r"\{.*\}", raw_reply or "", re.S)
    if not match:
        raise ai_client.AIError("Could not parse Subtext feed response. Try again.")
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        raise ai_client.AIError("Model returned malformed JSON for Subtext feed. Try again.")

    raw_posts = parsed.get("posts")
    if not isinstance(raw_posts, list) or not raw_posts:
        raise ai_client.AIError("No posts were generated. Try again.")

    created_posts = []
    for rp in raw_posts[:3]:
        if not isinstance(rp, dict):
            continue
        c_obj = _match_char_by_slug_or_name(chars, rp.get("author_slug"))
        c_prof = messenger.char_profile(c_obj)
        vis = rp.get("visibility") if rp.get("visibility") in ("public", "burner", "aita") else ("burner" if mode == "burner" else "public")
        if mode == "aita":
            vis = "aita"
        elif mode == "burner":
            vis = "burner"

        if vis == "burner":
            handle = burner_handle_for(c_obj)
        elif vis == "aita":
            handle = f"u/Throwaway_{c_obj.slug.split('-')[-1][:6]}"
        else:
            handle = c_prof["handle"]

        text = messenger.strip_stage_directions(str(rp.get("text") or "").strip())
        if not text:
            continue

        title = messenger.strip_stage_directions(str(rp.get("title") or "").strip()) if vis == "aita" else ""
        if vis == "aita" and not title:
            title = f"AITA for how I handled things today?"

        photo_prompt = str(rp.get("photo_prompt") or "").strip()
        photo_obj = None
        if photo_prompt:
            photo_obj = {
                "prompt": photo_prompt[:400],
                "url": "",
                "kind": "casual",
            }
            if u_prof.get("auto_photos"):
                try:
                    p_url, _ = messenger.generate_messenger_photo(user, c_obj, description=photo_prompt, kind="casual")
                    photo_obj["url"] = p_url
                except Exception as e:
                    log.info("Auto Subtext photo generation skipped: %s", e)

        votes = {"nta": 0, "yta": 0, "esh": 0, "user_vote": ""}
        comments_list = []
        for rc in (rp.get("comments") or [])[:5]:
            if not isinstance(rc, dict):
                continue
            rc_char = _match_char_by_slug_or_name(chars, rc.get("author_slug"))
            rc_prof = messenger.char_profile(rc_char)
            rc_text = messenger.strip_stage_directions(str(rc.get("text") or "").strip())
            if not rc_text:
                continue
            verdict = str(rc.get("verdict") or "").strip().upper()
            if verdict not in ("NTA", "YTA", "ESH"):
                verdict = ""
            if vis == "aita" and verdict:
                v_key = verdict.lower()
                votes[v_key] = votes.get(v_key, 0) + 1
            is_b = bool(rc.get("is_burner"))
            comments_list.append({
                "id": "stc_" + uuid.uuid4().hex[:8],
                "author_slug": rc_char.slug,
                "author_name": rc_prof["display_name"],
                "author_avatar": rc_prof["avatar_url"],
                "handle": burner_handle_for(rc_char) if is_b else rc_prof["handle"],
                "is_burner": is_b,
                "verdict": verdict,
                "text": rc_text[:600],
                "time": now_hm,
                "ts": time.time(),
            })

        post_item = {
            "id": "st_" + uuid.uuid4().hex[:8],
            "author_slug": c_obj.slug,
            "author_name": c_prof["display_name"],
            "author_avatar": c_prof["avatar_url"],
            "status_emoji": c_prof["status_emoji"],
            "handle": handle,
            "visibility": vis,
            "title": title[:220],
            "text": text[:1200],
            "subtweet_note": str(rp.get("subtweet_note") or ("Locked Burner" if vis == "burner" else "Subtext")).strip()[:70],
            "photo": photo_obj,
            "aita_votes": votes,
            "reactions": {},
            "comments": comments_list,
            "time": now_hm,
            "ts": time.time(),
        }
        created_posts.append(post_item)

    state = get_subtext_state(user, chars)
    all_posts = created_posts + state["posts"]
    save_subtext_state(user, {"posts": all_posts})
    return created_posts


def generate_replies_for_post(user, post, chars):
    """Have 1–3 characters jump into the comments of `post`."""
    if not chars:
        return []
    from mainapp.cards import user_name
    u_name = user_name(user)
    now_local = timezone.localtime(timezone.now())
    clock_str = now_local.strftime("%A %H:%M")
    now_hm = now_local.strftime("%H:%M")

    model_info = messenger.active_model_texting_rules(user)
    model_rules = f"ACTIVE MODEL CALIBRATION ({model_info['label']}):\n{model_info['rules']}" if model_info.get("rules") else ""

    existing_lines = []
    for c in (post.get("comments") or [])[-8:]:
        v_tag = f"[{c['verdict']}] " if c.get("verdict") else ""
        existing_lines.append(f"  - {c.get('author_name')} ({c.get('handle')}): {v_tag}{c.get('text')}")

    prompt = GENERATE_REPLIES_PROMPT.format(
        user=u_name,
        clock=clock_str,
        safeguards=SUBTEXT_SAFEGUARDS.format(user=u_name),
        model_rules=model_rules,
        char_roster=_build_roster_block(chars, user),
        telechat_digest=recent_telechat_digest(user, chars),
        post_author=post.get("author_name"),
        post_handle=post.get("handle"),
        post_visibility=post.get("visibility"),
        post_title=post.get("title") or "(no title)",
        post_text=post.get("text"),
        existing_comments="\n".join(existing_lines) if existing_lines else "  (No comments yet)",
    )

    raw_reply = ai_client.complete(user, "chat", [{"role": "user", "content": prompt}], max_tokens=900, temperature=0.85)
    match = re.search(r"\{.*\}", raw_reply or "", re.S)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return []

    added = []
    votes = post.setdefault("aita_votes", {"nta": 0, "yta": 0, "esh": 0, "user_vote": ""})
    for rc in (parsed.get("comments") or [])[:3]:
        if not isinstance(rc, dict):
            continue
        rc_char = _match_char_by_slug_or_name(chars, rc.get("author_slug"))
        rc_prof = messenger.char_profile(rc_char)
        rc_text = messenger.strip_stage_directions(str(rc.get("text") or "").strip())
        if not rc_text:
            continue
        verdict = str(rc.get("verdict") or "").strip().upper()
        if verdict not in ("NTA", "YTA", "ESH"):
            verdict = ""
        if post.get("visibility") == "aita" and verdict:
            v_key = verdict.lower()
            votes[v_key] = votes.get(v_key, 0) + 1
        is_b = bool(rc.get("is_burner"))
        c_item = {
            "id": "stc_" + uuid.uuid4().hex[:8],
            "author_slug": rc_char.slug,
            "author_name": rc_prof["display_name"],
            "author_avatar": rc_prof["avatar_url"],
            "handle": burner_handle_for(rc_char) if is_b else rc_prof["handle"],
            "is_burner": is_b,
            "verdict": verdict,
            "text": rc_text[:600],
            "time": now_hm,
            "ts": time.time(),
        }
        post.setdefault("comments", []).append(c_item)
        added.append(c_item)

    reacts = post.setdefault("reactions", {})
    for emo in (parsed.get("reactions") or [])[:2]:
        if emo in SUBTEXT_REACTIONS and chars:
            who = messenger.char_profile(chars[0])["display_name"]
            lst = list(reacts.get(emo) or [])
            if who not in lst:
                lst.append(who)
            reacts[emo] = lst

    return added


def create_user_post(user, text, visibility="public", title="", chars_for_replies=None):
    """Create a Subtext post authored by the user (Main, Locked Burner, or AITA) and optionally trigger character replies."""
    u_prof = messenger.user_profile(user)
    now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
    vis = visibility if visibility in ("public", "burner", "aita") else "public"
    base_h = u_prof.get("handle", "@you").lstrip("@")
    if vis == "burner":
        handle = f"@{base_h}_priv"
    elif vis == "aita":
        handle = f"u/Throwaway_{base_h[:8]}"
    else:
        handle = u_prof.get("handle", "@you")

    post_item = {
        "id": "st_" + uuid.uuid4().hex[:8],
        "author_slug": "user",
        "author_name": u_prof.get("display_name") or user.username,
        "author_avatar": u_prof.get("avatar_url") or "",
        "status_emoji": u_prof.get("status_emoji") or "✨",
        "handle": handle,
        "visibility": vis,
        "title": str(title or "").strip()[:220] if vis == "aita" else "",
        "text": str(text or "").strip()[:1200],
        "subtweet_note": "My Locked Burner" if vis == "burner" else ("AITA Thread" if vis == "aita" else "Posted by you"),
        "photo": None,
        "aita_votes": {"nta": 0, "yta": 0, "esh": 0, "user_vote": ""},
        "reactions": {},
        "comments": [],
        "time": now_hm,
        "ts": time.time(),
    }

    if chars_for_replies:
        try:
            generate_replies_for_post(user, post_item, chars_for_replies)
        except Exception as e:
            log.info("Auto replies on user Subtext post skipped: %s", e)

    state = get_subtext_state(user)
    all_posts = [post_item] + state["posts"]
    save_subtext_state(user, {"posts": all_posts})
    return post_item


def forward_post_to_telechat(user, post, char_obj, user_comment=""):
    """
    Forward a Subtext post (public, locked burner, or AITA thread) straight into the user's TeleChat DM
    with `char_obj`, and generate the character's immediate TeleChat reaction!
    """
    thread = messenger.ensure_thread_for_character(user, char_obj)
    u_prof = messenger.user_profile(user)
    td = messenger.thread_data(thread)
    now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")

    vis_badge = {
        "burner": "🔒 Locked Burner Post",
        "aita": "⚖️ AITA Thread",
        "public": "🌐 Subtext Post",
    }.get(post.get("visibility"), "🌐 Subtext Post")

    quoted = post.get("text") or ""
    if post.get("title"):
        quoted = f"{post['title']} — {quoted}"

    msg_text = f"> **{vis_badge} by {post.get('handle')}**\n> \"{quoted[:300]}\"\n\n"
    if user_comment and user_comment.strip():
        msg_text += user_comment.strip()
    else:
        msg_text += "Care to explain this post?" if post.get("visibility") != "public" else "Saw your post on Subtext."

    user_msg = {
        "id": uuid.uuid4().hex[:10],
        "role": "user",
        "sender_slug": "user",
        "sender_name": u_prof.get("display_name") or user.username,
        "text": msg_text,
        "time": now_hm,
        "ts": time.time(),
        "reactions": {},
    }
    td["messages"].append(user_msg)
    messenger.save_thread_data(thread, td)

    extra_dir = (
        f"{u_prof.get('display_name') or user.username} just forwarded your {vis_badge} ({post.get('handle')}: \"{quoted[:220]}\") "
        f"into your private TeleChat DMs and said: \"{user_comment or 'Care to explain this?'}\". "
        f"React naturally in-character (especially if you got caught subtweeting on your locked burner or posting an 'anonymous' AITA thread!)."
    )
    turn = messenger.generate_turn(user, thread, extra_instruction=extra_dir)
    return thread, user_msg, turn
