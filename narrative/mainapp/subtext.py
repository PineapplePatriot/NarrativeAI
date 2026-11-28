"""
Subtext: the cast's social feed on the Screen, fed by the same story as the phone chats.

Every person (each character, and you) has a main account and a locked burner. Three kinds of post:
- main: public; everyone on Subtext sees it.
- burner: locked; only its followers (chosen per burner) and its owner see it.
- aita: an anonymous "AITA for…" thread; everyone sees it, but only the author knows who wrote it.

Who has seen what is the point: characters only react to, comment on, or bring up in the phone chats the posts they
could have seen. The user can tick a character as knowing a post "because of the story" (someone showed them, they
found the account): from then on that character counts as having seen it. Forwarding a post into a DM does the same.

The status updates (Moments) show here too, as a strip; they're still edited where they always were.
State lives in the user's ChatSettings.appearance["subtext"]: {"posts": [...], "burners": {key: {"followers": [...]}}}.
"""
import logging
import time
from datetime import datetime
import uuid

from django.utils import timezone

from mainapp import ai_client, messenger
from mainapp.models import ChatSettings, MessengerThread

log = logging.getLogger(__name__)

REACTIONS = ["❤️", "🔥", "💀", "👀", "🤡", "💔"]
SUBTEXT_REACTIONS = REACTIONS  # the old name, still imported elsewhere
ACCOUNTS = ("main", "burner", "aita")
VERDICTS = ("NTA", "YTA", "ESH")
MAX_POSTS = 150


# ---------------------------------------------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------------------------------------------

def _settings(user):
    obj, _ = ChatSettings.objects.get_or_create(author=user)
    if not isinstance(obj.appearance, dict):
        obj.appearance = {}
    return obj


def _upgrade(p):
    """Posts written by the first version (author_slug/visibility/names baked in) in today's shape."""
    if "author" in p and "account" in p:
        return p
    vis = p.get("visibility")
    p = {**p, "author": p.get("author_slug") or "user",
         "account": {"public": "main", "burner": "burner", "aita": "aita"}.get(vis, "main")}
    votes = p.get("aita_votes") or {}
    p.setdefault("votes", {k: int(votes.get(k) or 0) for k in ("nta", "yta", "esh")})
    p.setdefault("user_vote", votes.get("user_vote") or "")
    p["comments"] = [{**c, "author": c.get("author") or c.get("author_slug") or "user",
                      "account": c.get("account") or ("burner" if c.get("is_burner") else "main")}
                     for c in p.get("comments") or [] if isinstance(c, dict)]
    p.setdefault("knows", {})
    return p


def load(user):
    raw = (_settings(user).appearance or {}).get("subtext")
    raw = raw if isinstance(raw, dict) else {}
    posts = [_upgrade(p) for p in raw.get("posts") or [] if isinstance(p, dict)]
    burners = raw.get("burners") if isinstance(raw.get("burners"), dict) else {}
    return {"posts": posts[:MAX_POSTS], "burners": burners}


def save(user, state):
    obj = _settings(user)
    app = dict(obj.appearance or {})
    app["subtext"] = {"posts": state["posts"][:MAX_POSTS], "burners": state.get("burners") or {}}
    obj.appearance = app
    obj.save(update_fields=["appearance"])


def find(state, post_id):
    post = next((p for p in state["posts"] if p.get("id") == post_id), None)
    if post is None:
        raise ValueError("That post isn't on Subtext any more.")
    return post


# ---------------------------------------------------------------------------------------------------------------
# People and accounts
# ---------------------------------------------------------------------------------------------------------------

def burner_handle_for(character):
    """A character's locked burner handle (e.g. `@dr_zandik_priv`)."""
    custom = str((character.messenger_profile or {}).get("burner_handle") or "").strip()
    if custom:
        return custom if custom.startswith("@") else f"@{custom}"
    return "@" + messenger.char_profile(character).get("handle", "@character").lstrip("@") + "_priv"


def people(user, chars):
    """{key: {name, handle, burner, avatar}} for you and every character."""
    me = messenger.user_profile(user)
    from mainapp.cards import user_name
    handle = me.get("handle") or "@you"
    out = {"user": {"key": "user", "name": me.get("display_name") or user_name(user), "handle": handle,
                    "burner": "@" + handle.lstrip("@") + "_priv", "avatar": me.get("avatar_url") or ""}}
    for c in chars:
        p = messenger.char_profile(c)
        out[c.slug] = {"key": c.slug, "name": p["display_name"], "handle": p.get("handle") or "@" + c.slug,
                       "burner": burner_handle_for(c), "avatar": p.get("avatar_url") or ""}
    return out


def followers(state, owner):
    return [k for k in ((state.get("burners") or {}).get(owner) or {}).get("followers") or [] if isinstance(k, str)]


def can_see(state, post, key):
    """Whether `key` (a character slug or "user") has seen this post in the story."""
    if post.get("author") == key or post.get("account") in ("main", "aita"):
        return True
    return key in followers(state, post.get("author")) or key in (post.get("knows") or {})


def knows_author(state, post, key):
    """For an anonymous AITA thread: whether `key` knows who wrote it."""
    return post.get("account") != "aita" or post.get("author") == key or key in (post.get("knows") or {})


def seen_by(state, post, keys):
    return [k for k in keys if can_see(state, post, k)]


# ---------------------------------------------------------------------------------------------------------------
# For the page
# ---------------------------------------------------------------------------------------------------------------

def _when(ts):
    if not ts:
        return ""
    local = timezone.localtime(datetime.fromtimestamp(ts, tz=timezone.get_current_timezone()))
    now = timezone.localtime(timezone.now())
    return local.strftime("%H:%M") if local.date() == now.date() else local.strftime("%d %b, %H:%M")


def statuses(user, chars):
    """The status updates (Moments), newest first, for the strip at the top of the feed."""
    out = []
    me = messenger.user_profile(user)
    for s in me.get("stories") or []:
        out.append({"key": "user", "text": s.get("text") or "", "emoji": s.get("emoji") or me.get("status_emoji") or "",
                    "image": s.get("image_url") or "", "ts": s.get("ts") or 0})
    for c in chars:
        p = messenger.char_profile(c)
        for s in p.get("stories") or []:
            out.append({"key": c.slug, "text": s.get("text") or "", "emoji": s.get("emoji") or p.get("status_emoji") or "",
                        "image": s.get("image_url") or "", "ts": s.get("ts") or 0})
    out.sort(key=lambda s: s["ts"] or 0, reverse=True)
    return [{**s, "when": _when(s["ts"])} for s in out[:24]]


def payload(user, chars, state=None):
    state = state or load(user)
    keys = [c.slug for c in chars]
    posts = []
    for p in state["posts"]:
        p = dict(p)
        p["when"] = _when(p.get("ts"))
        p["seen_by"] = seen_by(state, p, keys)
        p["followers"] = followers(state, p.get("author")) if p.get("account") == "burner" else []
        p["you_see"] = can_see(state, p, "user")
        posts.append(p)
    return {"posts": posts, "people": people(user, chars), "statuses": statuses(user, chars),
            "burners": {k: {"followers": followers(state, k)} for k in ["user", *keys]}, "reactions": REACTIONS}


def get_subtext_state(user, characters=None):
    """The whole feed for the page (the Screen's first load reads it too)."""
    return payload(user, list(characters or []))


# ---------------------------------------------------------------------------------------------------------------
# What the cast has seen, for the phone chats
# ---------------------------------------------------------------------------------------------------------------

def seen_block(user, chars, limit=8):
    """SUBTEXT lately, for a phone chat: the recent posts its characters could have seen, each marked with who saw it,
    so nobody brings up a post they never saw."""
    if not chars:
        return ""
    state = load(user)
    ppl = people(user, chars)
    keys = [c.slug for c in chars]
    lines = []
    for p in state["posts"][:40]:
        who = seen_by(state, p, keys)
        if not who:
            continue
        author = ppl.get(p.get("author"), {"name": "someone", "handle": "@someone", "burner": "@someone_priv"})
        where = {"main": f"{author['name']} ({author['handle']}) posted",
                 "burner": f"{author['name']} posted on their LOCKED account {author['burner']}",
                 "aita": "an anonymous AITA thread was posted"}[p.get("account", "main")]
        if p.get("account") == "aita":
            in_on = [ppl[k]["name"] for k in who if knows_author(state, p, k) and k in ppl]
            if in_on:
                where += f" (written by {author['name']}; only {', '.join(in_on)} know that)"
        text = (p.get("title") + ": " if p.get("title") else "") + str(p.get("text") or "")
        replies = "; ".join(f"{ppl.get(c.get('author'), {}).get('name', 'someone')}: {str(c.get('text'))[:120]}"
                            for c in (p.get("comments") or [])[-3:])
        lines.append(f"- {_when(p.get('ts'))}, {where}: \"{text[:280]}\"" + (f" Replies: {replies}" if replies else "")
                     + f" [seen by: {', '.join(ppl[k]['name'] for k in who if k in ppl)}]")
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return ("ON SUBTEXT LATELY (the social app; a character knows only the posts marked as seen by them, and brings "
            "them up only if it would come up naturally):\n" + "\n".join(lines))


# ---------------------------------------------------------------------------------------------------------------
# Writing posts and replies
# ---------------------------------------------------------------------------------------------------------------

VOICE_RULES = """HOW SUBTEXT IS WRITTEN:
- Each person posts the way THEY would: their own pride, humour, habits and what they want people to think of them.
  Posting is a different voice from texting, but it's still them.
- No hashtag slop, motivational lines, therapy-speak or influencer voice. No asterisk actions or narration: only
  what they actually type.
- main: what they're willing to say in public. burner: what they'd only say to the few who follow it (venting,
  subtweets without names, things they'd deny). aita: an "AITA for…" written to sound anonymous and reasonable.
- People only react to and know about what they have seen (marked below). An anonymous AITA author is unknown to
  everyone who isn't marked as knowing; they may guess, they don't know."""

WAVE_PROMPT = """You write new posts on Subtext, the social app on {user}'s phone, where the people below post.
Story time: {clock}

{rules}

PEOPLE:
{roster}

WHAT HAPPENED IN THE PHONE CHATS LATELY (each person knows only the chats they're in):
{chats}

RECENT POSTS (with who has seen each):
{recent}

What to write: {mode}
{topic}

Write 1 or 2 new posts, each with 0 to 3 replies. Replies come only from people who can see the post: for a
burner post, only its followers ({followers_note}).
Return ONLY JSON:
{{"posts": [{{"author": "slug", "account": "main" | "burner" | "aita", "title": "'AITA for …' for aita, else ''",
             "text": "the post, 1 to 4 sentences", "photo": "if they'd attach a photo they took: what's in it, else ''",
             "replies": [{{"author": "slug", "verdict": "NTA|YTA|ESH for aita, else ''", "text": "1-2 sentences"}}]}}]}}
{steer}"""

REPLY_PROMPT = """You write replies on Subtext, the social app on {user}'s phone.
Story time: {clock}

{rules}

WHO MAY REPLY (they can all see this post):
{roster}

WHAT HAPPENED IN THE PHONE CHATS LATELY (each person knows only the chats they're in):
{chats}

THE POST ({kind}) by {author}{anon}:
{title}{text}
Replies so far:
{thread}

Write 1 to 3 new replies{to_user}. For an aita thread each reply has a verdict.
Return ONLY JSON: {{"replies": [{{"author": "slug", "verdict": "NTA|YTA|ESH or ''", "text": "1-2 sentences"}}],
                    "reactions": [{{"author": "slug", "emoji": "one of {reactions}"}}]}}
{steer}"""


def _steer(user):
    from mainapp.bulba import polish
    try:
        return polish.avoid_line(user)
    except Exception:
        return ""


def _clock():
    return timezone.localtime(timezone.now()).strftime("%A %H:%M")


def _roster(user, chars, state):
    lines = []
    for c in chars:
        p = messenger.char_profile(c)
        who = p.get("modern_persona") or c.personality or (c.description or "")[:400]
        fol = followers(state, c.slug)
        lines.append(f"- {p['display_name']} (slug `{c.slug}`; main {p.get('handle')}; burner {burner_handle_for(c)}, "
                     f"followed by: {', '.join(fol) or 'nobody yet'})\n  Who they are: {str(who)[:400]}\n"
                     f"  How they write: {str(p.get('texting_style') or 'their own voice')[:250]}")
    return "\n".join(lines)


def chats_digest(user, chars):
    """The last messages of the phone chats these characters are in, each chat with who's in it."""
    slugs = {c.slug for c in chars}
    parts = []
    for t in MessengerThread.objects.filter(user=user).prefetch_related("characters")[:10]:
        members = list(t.characters.all())
        if not slugs & {c.slug for c in members}:
            continue
        data = messenger.thread_data(t)
        lines = []
        for m in messenger.delivered(data.get("messages") or [])[-6:]:
            if m.get("role") == "system":
                continue
            text = (m.get("text") or "").strip()
            if m.get("photo"):
                text += f" [photo: {m['photo'].get('caption') or m['photo'].get('prompt') or 'a photo'}]"
            if text:
                lines.append(f"  {m.get('sender_name') or ('the user' if m.get('role') == 'user' else '?')}: {text[:160]}")
        if lines:
            parts.append(f"Chat \"{t.title}\" (in it: {', '.join(c.name for c in members)}):\n" + "\n".join(lines))
        if len(parts) == 4:
            break
    return "\n\n".join(parts) or "(no recent chats)"


def _recent(user, state, chars):
    ppl = people(user, chars)
    keys = [c.slug for c in chars]
    lines = []
    for p in state["posts"][:10]:
        a = ppl.get(p.get("author"), {"name": "someone"})
        lines.append(f"- [{p.get('account')}] {a['name']}: {(p.get('title') or '')} {str(p.get('text'))[:200]} "
                     f"(seen by: {', '.join(ppl[k]['name'] for k in seen_by(state, p, keys) if k in ppl) or 'nobody'})")
    return "\n".join(lines) or "(none yet)"


def _clean_text(v, n):
    return messenger.strip_stage_directions(" ".join(str(v or "").split()))[:n]


def _strip_name(text, names):
    """'Mira: so anyway' -> 'so anyway' (models like to label their lines)."""
    for name in names:
        for prefix in (f"{name}:", f"**{name}:**", f"{name} :"):
            if text.lower().startswith(prefix.lower()):
                return text[len(prefix):].strip()
    return text


def _reply(state, post, raw, by_slug, ppl):
    """A reply from the model, or None when its author couldn't have seen the post."""
    if not isinstance(raw, dict):
        return None
    c = by_slug.get(str(raw.get("author") or "").strip())
    if c is None or not can_see(state, post, c.slug):
        return None
    text = _strip_name(_clean_text(raw.get("text"), 600), [ppl[c.slug]["name"], c.name])
    if not text:
        return None
    verdict = str(raw.get("verdict") or "").strip().upper()
    verdict = verdict if post.get("account") == "aita" and verdict in VERDICTS else ""
    if verdict:
        post.setdefault("votes", {"nta": 0, "yta": 0, "esh": 0})[verdict.lower()] = int(post["votes"].get(verdict.lower()) or 0) + 1
    return {"id": "stc_" + uuid.uuid4().hex[:8], "author": c.slug,
            "account": "burner" if post.get("account") == "burner" else "main", "verdict": verdict, "text": text,
            "ts": time.time()}


def _new_post(author, account, title, text, photo=None):
    return {"id": "st_" + uuid.uuid4().hex[:8], "author": author, "account": account,
            "title": title if account == "aita" else "", "text": text, "photo": photo,
            "votes": {"nta": 0, "yta": 0, "esh": 0}, "user_vote": "", "reactions": {}, "comments": [], "knows": {},
            "ts": time.time()}


MODES = {"any": "whatever these people would post right now: mostly main posts, a burner post if someone has "
                "something they'd only tell their followers",
         "main": "main (public) posts only", "burner": "burner (locked) posts only",
         "aita": "one anonymous aita thread"}


def generate_wave(user, chars, mode="any", topic=""):
    """1-2 new posts from these characters, with replies from people who can see them. Returns the new posts."""
    if not chars:
        raise ai_client.AIError("Pick at least one character first.")
    from mainapp.cards import user_name
    state = load(user)
    ppl = people(user, chars)
    raw = messenger.ask_json(user, WAVE_PROMPT.format(
        user=user_name(user), clock=_clock(), rules=VOICE_RULES, roster=_roster(user, chars, state),
        chats=chats_digest(user, chars), recent=_recent(user, state, chars), mode=MODES.get(mode, MODES["any"]),
        topic=f"The user would like: {str(topic)[:400]}" if str(topic or "").strip() else "",
        followers_note="listed after each person's burner", steer=_steer(user)),
        need=("posts",), max_tokens=1800, task="chat", temperature=0.85)
    by_slug = {c.slug: c for c in chars}
    made = []
    for rp in (raw.get("posts") if isinstance(raw.get("posts"), list) else [])[:3]:
        if not isinstance(rp, dict):
            continue
        author = by_slug.get(str(rp.get("author") or "").strip())
        if author is None:
            continue
        account = rp.get("account") if rp.get("account") in ACCOUNTS else "main"
        if mode in ("main", "burner", "aita"):
            account = mode
        text = _strip_name(_clean_text(rp.get("text"), 1200), [ppl[author.slug]["name"], author.name])
        if not text:
            continue
        title = _clean_text(rp.get("title"), 220) or ("AITA for how I handled today?" if account == "aita" else "")
        photo = {"prompt": _clean_text(rp.get("photo"), 400), "url": ""} if _clean_text(rp.get("photo"), 10) else None
        post = _new_post(author.slug, account, title, text, photo)
        state["posts"].insert(0, post)  # replies are checked against the state that has it
        for r in (rp.get("replies") or [])[:4] if isinstance(rp.get("replies"), list) else []:
            reply = _reply(state, post, r, by_slug, ppl)
            if reply:
                post["comments"].append(reply)
        made.append(post)
    if not made:
        raise ai_client.AIError("The model wrote no usable posts. Try again.")
    save(user, state)
    return made


def generate_replies(user, post, chars, state):
    """1-3 replies on `post` from those of `chars` who can see it. Mutates post; returns the new replies."""
    eligible = [c for c in chars if can_see(state, post, c.slug)]
    if not eligible:
        raise ai_client.AIError("None of them can see this post: a locked post needs followers, or someone who knows.")
    from mainapp.cards import user_name
    ppl = people(user, chars)
    author = ppl.get(post.get("author"), {"name": "someone"})
    thread = "\n".join(f"  {ppl.get(c.get('author'), {}).get('name', 'someone')}"
                       + (f" [{c['verdict']}]" if c.get("verdict") else "") + f": {c.get('text')}"
                       for c in (post.get("comments") or [])[-10:]) or "  (none)"
    last = (post.get("comments") or [{}])[-1]
    raw = messenger.ask_json(user, REPLY_PROMPT.format(
        user=user_name(user), clock=_clock(), rules=VOICE_RULES, roster=_roster(user, eligible, state),
        chats=chats_digest(user, eligible), kind=post.get("account"), author=author["name"],
        anon=" (anonymous: only the author and those marked as knowing know who wrote it)" if post.get("account") == "aita" else "",
        title=(post.get("title") + "\n") if post.get("title") else "", text=post.get("text"), thread=thread,
        to_user=f", answering {ppl['user']['name']}'s latest reply first" if last.get("author") == "user" else "",
        reactions=" ".join(REACTIONS), steer=_steer(user)),
        need=("replies",), max_tokens=1000, task="chat", temperature=0.85)
    by_slug = {c.slug: c for c in eligible}
    added = []
    for r in (raw.get("replies") if isinstance(raw.get("replies"), list) else [])[:3]:
        reply = _reply(state, post, r, by_slug, ppl)
        if reply:
            post.setdefault("comments", []).append(reply)
            added.append(reply)
    for r in (raw.get("reactions") if isinstance(raw.get("reactions"), list) else [])[:3]:
        if isinstance(r, dict) and r.get("emoji") in REACTIONS and r.get("author") in by_slug:
            who = post.setdefault("reactions", {}).setdefault(r["emoji"], [])
            if r["author"] not in who:
                who.append(r["author"])
    return added


# ---------------------------------------------------------------------------------------------------------------
# What the user does
# ---------------------------------------------------------------------------------------------------------------

def post_as_user(user, text, account="main", title=""):
    state = load(user)
    account = account if account in ACCOUNTS else "main"
    text = str(text or "").strip()[:1200]
    if not text:
        raise ValueError("Write something to post first.")
    post = _new_post("user", account, str(title or "").strip()[:220] or ("AITA?" if account == "aita" else ""), text)
    state["posts"].insert(0, post)
    save(user, state)
    return post, state


def comment_as_user(user, state, post, text, verdict=""):
    if not can_see(state, post, "user"):
        raise ValueError("You don't follow this locked account, so your character can't see it to reply.")
    text = str(text or "").strip()[:600]
    if not text:
        raise ValueError("The reply is empty.")
    verdict = str(verdict or "").upper()
    verdict = verdict if post.get("account") == "aita" and verdict in VERDICTS else ""
    if verdict:
        vote(post, verdict)
    reply = {"id": "stc_" + uuid.uuid4().hex[:8], "author": "user",
             "account": "burner" if post.get("account") == "burner" and post.get("author") == "user" else "main",
             "verdict": verdict, "text": text, "ts": time.time()}
    post.setdefault("comments", []).append(reply)
    return reply


def react(post, emoji, key="user"):
    if emoji not in REACTIONS:
        raise ValueError("Pick one of the reactions.")
    who = post.setdefault("reactions", {}).setdefault(emoji, [])
    if key in who:
        who.remove(key)
    else:
        who.append(key)
    if not who:
        post["reactions"].pop(emoji, None)


def vote(post, verdict):
    votes = post.setdefault("votes", {"nta": 0, "yta": 0, "esh": 0})
    before = post.get("user_vote") or ""
    if before.lower() in votes:
        votes[before.lower()] = max(0, int(votes[before.lower()]) - 1)
    votes[verdict.lower()] = int(votes.get(verdict.lower()) or 0) + 1
    post["user_vote"] = verdict


def set_followers(state, owner, keys, valid):
    """Who follows `owner`'s burner (characters and/or "user")."""
    state.setdefault("burners", {})[owner] = {"followers": [k for k in dict.fromkeys(keys or []) if k in valid and k != owner]}


def set_knows(state, post, key, knows=True, how=""):
    """✓ knows: this character has seen the post because of the story (or, for aita, knows who wrote it)."""
    knows_map = dict(post.get("knows") or {})
    if knows:
        knows_map[key] = " ".join(str(how or "").split())[:200]
    else:
        knows_map.pop(key, None)
    post["knows"] = knows_map


def forward(user, state, post, char_obj, chars, comment=""):
    """Send a post into the DM with `char_obj` and get their reply. Seeing it there, they now know it."""
    author_name = people(user, chars).get(post.get("author"), {}).get("name") or "someone"
    had_seen = can_see(state, post, char_obj.slug)
    if not had_seen or (post.get("account") == "aita" and not knows_author(state, post, char_obj.slug)):
        set_knows(state, post, char_obj.slug, True, "The user sent it to them in a DM")
    save(user, state)
    label = {"main": "Subtext post", "burner": "post from a locked Subtext account", "aita": "anonymous AITA thread"}[post.get("account", "main")]
    quoted = (post.get("title") + " — " if post.get("title") else "") + str(post.get("text") or "")
    thread = messenger.ensure_thread_for_character(user, char_obj)
    data = messenger.thread_data(thread)
    me = messenger.user_profile(user)
    text = f"> {label}" + (f" by {author_name}" if post.get("account") != "aita" else "") + f"\n> \"{quoted[:300]}\"\n\n" \
        + (comment.strip() or "Saw this.")
    msg = {"id": uuid.uuid4().hex[:10], "role": "user", "sender_slug": "user",
           "sender_name": me.get("display_name") or user.username, "text": text,
           "time": timezone.localtime(timezone.now()).strftime("%H:%M"), "ts": time.time(), "reactions": {}}
    data["messages"].append(msg)
    messenger.save_thread_data(thread, data)
    mine = post.get("author") == char_obj.slug
    note = (f"The user just sent you a {label}" + (" that YOU wrote" if mine else f" by {author_name}" if post.get("account") != "aita" else "")
            + f": \"{quoted[:220]}\"." + ("" if had_seen else " You hadn't seen it before.")
            + (" It was posted on your locked account: they shouldn't have been able to see it, unless they follow it."
               if mine and post.get("account") == "burner" and not can_see(state, post, "user") else "")
            + " React as yourself.")
    turn = messenger.generate_turn(user, thread, extra_instruction=note)
    return thread, msg, turn
