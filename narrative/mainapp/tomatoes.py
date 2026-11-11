"""
🍅 Tomatoes thrown "in the wild": at a chat or at Bulba while waiting for a reply (static/js/tomato.js). They're
what the leaderboard ranks and, later, what pays for spins. Throws in the Tomato Pit's own field and on the splat
wall count only towards the personal total (views.tomato_state), so an auto-clicker on the Pit wins nothing.

The browser says how many it threw, so the server only believes what a person could do:
- RATE throws a second since the last sync, plus a small BURST (several tabs, a sync that failed and came later);
- at most DAY_MAX a day (UTC). An honest heavy day of chatting stays well under it.
What goes over is dropped, and the browser takes the server's number back on its next sync.
"""
import json as _json
import re as _re
from pathlib import Path as _Path

from django.db import transaction
from django.utils import timezone

RATE = 12       # throws a second: faster than anyone's clicking, slower than a script's
BURST = 60      # allowed on top, whatever the time since the last sync
DAY_MAX = 5000  # chat + Bulba throws counted per day
BOARD_SIZE = 20


def score_of(user):
    from mainapp.models import TomatoScore
    obj, _ = TomatoScore.objects.get_or_create(user=user)
    return obj


def allowed(score, now):
    """How many chat + Bulba throws one sync may add right now."""
    if score.synced_at is None:
        by_time = BURST * 5  # the first sync ever: a few minutes' worth thrown before syncs began
    else:
        by_time = BURST + int(max(0.0, (now - score.synced_at).total_seconds()) * RATE)
    today = now.date()
    used = score.day_wild if score.day == today else 0
    return max(0, min(by_time, DAY_MAX - used))


def add_wild(user, sent):
    """Count `sent` chat + Bulba throws (bounded as above); returns the saved score."""
    from mainapp.models import TomatoScore
    now = timezone.now()
    with transaction.atomic():
        score_of(user)  # make sure the row exists before locking it
        score = TomatoScore.objects.select_for_update().get(user=user)
        add = min(max(0, sent), allowed(score, now))
        today = now.date()
        if score.day != today:
            score.day, score.day_wild = today, 0
        score.wild += add
        score.day_wild += add
        score.synced_at = now
        from mainapp import tomato_garden
        tomato_garden.water(score, add)  # 🌻 chat tomatoes water the garden
        score.save()
    return score


def board(user):
    """The leaderboard: the top BOARD_SIZE who joined, and where this user stands (or would stand if they joined)."""
    from mainapp.models import TomatoScore
    me = score_of(user)
    joined = TomatoScore.objects.filter(on_board=True, wild__gt=0).select_related("user")
    from mainapp import tomato_machine
    top = [{"name": s.user.username, "wild": s.wild, "me": s.user_id == user.id,
            "badge": tomato_machine.worn(s).get("badge", "")}
           for s in joined.order_by("-wild", "synced_at", "id")[:BOARD_SIZE]]
    ahead = joined.filter(wild__gt=me.wild).exclude(user=user).count()
    return {"top": top, "me": {"wild": me.wild, "on_board": me.on_board, "rank": ahead + 1 if me.wild else None,
                               "today": me.day_wild if me.day == timezone.now().date() else 0},
            "players": joined.count(), "day_max": DAY_MAX}


def join(user, on):
    score = score_of(user)
    score.on_board = bool(on)
    score.save(update_fields=["on_board"])
    return score


# --- 🖼 The gallery: saved splat walls (TomatoArt) -----------------------------------------------------------
# A piece is its splats, drawn in the browser (static/mainapp/js/splat_art.js): nothing uploaded, so everything a
# shared piece can show is a vegetable, a colour and a background from the lists below.
WALL_W, WALL_H = 1200, 750
MAX_SPLATS = 4000
MAX_ART = 60          # pieces one account can keep
PAGE = 12
TEXTURES = ("night", "plaster", "brick", "chalk", "sky", "grass", "wood", "paper", "tiles", "canvas")
SHAPES = ("splat", "drip", "spray", "stamp")
COLOR = _re.compile(r"^(#[0-9a-fA-F]{3,8}|hsla?\(\s*\d{1,3}(\.\d+)?\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%\s*(,\s*[\d.]+\s*)?\)"
                    r"|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(,\s*[\d.]+\s*)?\))$")
# hue-rotate(38deg) saturate(1.6)...: the colour effects skins use, nothing that could load anything (no url())
FILTER = _re.compile(r"^((hue-rotate|saturate|brightness|grayscale|opacity|contrast|sepia|invert)\((\d{1,3}(\.\d+)?|\.\d+)(deg|%)?\)\s*){0,6}$")
ASCII_WORD = _re.compile(r"[A-Za-z0-9<>&\"'`\\/]")


def scene_choices():
    """The app's built-in story backgrounds, usable as a wall ("scene:<file>"): [{"file", "name"}]."""
    try:
        from django.conf import settings
        path = _Path(settings.BASE_DIR) / "static" / "defaults" / "catalog.json"
        return [{"file": b["file"], "name": b.get("name") or b["file"]}
                for b in _json.loads(path.read_text(encoding="utf-8")).get("backgrounds", [])]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def scene_backgrounds():
    return [b["file"] for b in scene_choices()]


def clean_bg(bg):
    bg = str(bg or "")
    if bg in TEXTURES or (bg.startswith("scene:") and bg[6:] in scene_backgrounds()):
        return bg
    return "night"


def _num(v, lo, hi, cast=float):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return cast(min(hi, max(lo, v)))


def clean_splat(sp):
    """One splat as the wall draws it, or None if it isn't one."""
    if not isinstance(sp, dict):
        return None
    x, y, r = _num(sp.get("x"), 0, WALL_W, int), _num(sp.get("y"), 0, WALL_H, int), _num(sp.get("r"), 4, 160, int)
    c, k = str(sp.get("c") or ""), str(sp.get("k") or "")
    if None in (x, y, r) or not COLOR.match(c) or not k or len(k) > 8 or ASCII_WORD.search(k):
        return None
    f = str(sp.get("f") or "")
    return {"x": x, "y": y, "r": r, "c": c, "k": k, "f": f if len(f) <= 160 and FILTER.match(f) else "", "e": bool(sp.get("e")),
            "rot": round(_num(sp.get("rot"), 0, 7) or 0, 2), "seed": _num(sp.get("seed"), 0, 233279, int) or 0,
            "t": sp.get("t") if sp.get("t") in SHAPES else "splat"}


def clean_art(splats):
    if not isinstance(splats, list):
        return []
    return [s for s in (clean_splat(sp) for sp in splats[-MAX_SPLATS:]) if s]


def clean_title(title):
    return " ".join(str(title or "").split())[:60]


def art_item(art, user, full=False):
    item = {"id": art.id, "title": art.title, "bg": art.bg, "shared": art.shared, "mine": art.user_id == user.id,
            "artist": art.user.username, "created": art.created.isoformat(), "count": len(art.splats or []),
            "likes": getattr(art, "n_likes", None), "liked": getattr(art, "i_liked", None)}
    if item["likes"] is None:
        item["likes"] = art.likes.count()
        item["liked"] = art.likes.filter(id=user.id).exists()
    if full:
        item["splats"] = art.splats
    return item


def art_list(user, scope="mine", sort="new", page=1):
    from django.db.models import Count, Exists, OuterRef
    from mainapp.models import TomatoArt
    qs = TomatoArt.objects.select_related("user").annotate(
        n_likes=Count("likes", distinct=True),
        i_liked=Exists(TomatoArt.likes.through.objects.filter(tomatoart_id=OuterRef("pk"), user_id=user.id)))
    qs = qs.filter(user=user) if scope == "mine" else qs.filter(shared=True)
    qs = qs.order_by("-n_likes", "-created") if sort == "liked" else qs.order_by("-created")
    page = max(1, page)
    rows = list(qs[(page - 1) * PAGE: page * PAGE + 1])
    return {"items": [art_item(a, user) for a in rows[:PAGE]], "more": len(rows) > PAGE, "page": page}
