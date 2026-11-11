"""
🎰 The Sauce-o-Matic: a prize machine in the Tomato Pit that runs on tomatoes, never money.

Spins
- One for every SPIN_COST tomatoes thrown at chats and Bulba (TomatoScore.wild, mainapp/tomatoes.py), plus:
- a free one for each golden splat (1 in 500) thrown at a chat or Bulba, and
- one for every COMPOST_SPIN compost (what duplicates turn into).

A draw (all on the server, so nobody can rig it from the browser)
- Tiers: common 75%, rare 21%, legendary 4% (ODDS).
- Pity: a rare or better at least every RARE_PITY spins; a legendary at the latest on spin LEGEND_PITY.
- Bulba's Promise: they pick one legendary. A legendary is the picked one half the time; when it isn't, the
  next legendary is guaranteed to be.
- Seasonal skins are only in the machine during their season (season()).
- Things you keep one of (skins, perks, gardeners, oddities) turn into compost when drawn again; seeds and
  garden decorations stack (for the garden).

Everything lives in TomatoScore.machine (JSON): used, bonus, golden, compost, pity_rare, pity_legend, promise,
promise_sure, items {id: count}, equipped {badge, trail, hat}, history [last pulls].
"""
import random

from django.db import transaction
from django.utils import timezone

SPIN_COST = 300
COMPOST_SPIN = 10
ODDS = {"common": 75, "rare": 21, "legendary": 4}
RARE_PITY = 8
LEGEND_PITY = 25
HISTORY = 40
COMPOST_FOR = {"common": 1, "rare": 3, "legendary": 10}
SEASONS = {"winter": (12, 1, 2), "spring": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11)}

# kind: oddity (a shelf of nonsense) · seed / decor (garden, stack) · skin (tomato.js SKINS has its look) ·
# badge (by your name on the leaderboard) · trail (follows the cursor) · hat (on Bulba) · gardener (the garden)
PRIZES = [
    # --- Common ---
    {"id": "bean", "tier": "common", "kind": "oddity", "emoji": "🫘", "name": "A single bean",
     "note": "One. Bean. Bulba counted twice."},
    {"id": "disappointment", "tier": "common", "kind": "oddity", "emoji": "🖼️", "name": "Bulba's disappointment (framed)",
     "note": "Hang it somewhere you'll see it every day."},
    {"id": "napkin", "tier": "common", "kind": "oddity", "emoji": "🧻", "name": "A slightly used napkin",
     "note": "Slightly. Don't ask what for."},
    {"id": "pebble", "tier": "common", "kind": "oddity", "emoji": "🪨", "name": "A pebble",
     "note": "It's a good pebble. Bulba checked."},
    {"id": "receipt", "tier": "common", "kind": "oddity", "emoji": "🧾", "name": "A receipt for 300 tomatoes",
     "note": "Proof of purchase. No refunds."},
    {"id": "glove", "tier": "common", "kind": "oddity", "emoji": "🧤", "name": "One gardening glove",
     "note": "The left one. The right one is in another machine."},
    {"id": "seed_tomato", "tier": "common", "kind": "seed", "emoji": "🌱", "name": "Tomato seeds",
     "note": "Plant them. Grow ammunition."},
    {"id": "seed_carrot", "tier": "common", "kind": "seed", "emoji": "🥕", "name": "Carrot seeds",
     "note": "Orange, pointy, honest."},
    {"id": "seed_sunflower", "tier": "common", "kind": "seed", "emoji": "🌻", "name": "Sunflower seeds",
     "note": "It will stare at the sun. Let it."},
    {"id": "gnome", "tier": "common", "kind": "decor", "emoji": "🗿", "name": "Garden gnome, unimpressed",
     "note": "He has seen your throwing. He is not impressed."},
    # --- Rare ---
    {"id": "seed_pumpkin", "tier": "rare", "kind": "seed", "emoji": "🎃", "name": "Pumpkin seeds",
     "note": "Grows slowly, grows big, judges you."},
    {"id": "bench", "tier": "rare", "kind": "decor", "emoji": "🪑", "name": "Garden bench",
     "note": "For sitting while your tomatoes grow. Slowly."},
    {"id": "scarecrow", "tier": "rare", "kind": "decor", "emoji": "🌾", "name": "Scarecrow",
     "note": "Scares crows. Doesn't scare Bulba."},
    {"id": "pond", "tier": "rare", "kind": "decor", "emoji": "💧", "name": "A small pond",
     "note": "Frogs will hear about this."},
    {"id": "lantern", "tier": "rare", "kind": "decor", "emoji": "🏮", "name": "Paper lantern",
     "note": "Lights up the garden at night."},
    {"id": "pickle", "tier": "rare", "kind": "skin", "emoji": "🥒", "name": "Pickle", "note": "Briny. Aerodynamic."},
    {"id": "dumpling", "tier": "rare", "kind": "skin", "emoji": "🥟", "name": "Dumpling", "note": "Too cute to throw. Throw it anyway."},
    {"id": "duckling", "tier": "rare", "kind": "skin", "emoji": "🐤", "name": "Rubber duckling", "note": "Squeaks on impact."},
    {"id": "badge_chef", "tier": "rare", "kind": "badge", "emoji": "🧑‍🍳", "name": "Badge: Sauce chef",
     "note": "Shown by your name on the leaderboard."},
    {"id": "badge_fire", "tier": "rare", "kind": "badge", "emoji": "🔥", "name": "Badge: On fire",
     "note": "Shown by your name on the leaderboard."},
    {"id": "badge_sprout", "tier": "rare", "kind": "badge", "emoji": "🌿", "name": "Badge: Green thumb",
     "note": "Shown by your name on the leaderboard."},
    {"id": "trail_sparkle", "tier": "rare", "kind": "trail", "emoji": "✨", "name": "Cursor trail: sparkles",
     "note": "Your cursor leaves sparkles everywhere in the app."},
    {"id": "trail_ketchup", "tier": "rare", "kind": "trail", "emoji": "🍅", "name": "Cursor trail: ketchup drips",
     "note": "Your cursor drips. Everywhere."},
    {"id": "trail_leaves", "tier": "rare", "kind": "trail", "emoji": "🍃", "name": "Cursor trail: leaves",
     "note": "A little breeze follows your cursor."},
    {"id": "hat_straw", "tier": "rare", "kind": "hat", "emoji": "👒", "name": "Bulba's hat: straw hat",
     "note": "Bulba wears it. Bulba does not admit to liking it."},
    {"id": "hat_crown", "tier": "rare", "kind": "hat", "emoji": "👑", "name": "Bulba's hat: crown",
     "note": "Bulba was always royalty. Now it's official."},
    {"id": "hat_top", "tier": "rare", "kind": "hat", "emoji": "🎩", "name": "Bulba's hat: top hat",
     "note": "A potato of means."},
    # --- Legendary ---
    {"id": "gardener_farmer", "tier": "legendary", "kind": "gardener", "emoji": "🧑‍🌾", "name": "Grandpa Pomodoro",
     "note": "An old farmer who waters everything, including things that are not plants."},
    {"id": "gardener_frog", "tier": "legendary", "kind": "gardener", "emoji": "🐸", "name": "Ribbit, in overalls",
     "note": "A frog with a job. Takes it very seriously."},
    {"id": "gardener_robot", "tier": "legendary", "kind": "gardener", "emoji": "🤖", "name": "Hoe-Bot 3000",
     "note": "Harvests on schedule. Beeps at weeds."},
    {"id": "gardener_witch", "tier": "legendary", "kind": "gardener", "emoji": "🧙‍♀️", "name": "Basil the hedge witch",
     "note": "Plants grow faster when she hums. Nobody knows the song."},
    {"id": "snow", "tier": "legendary", "kind": "skin", "emoji": "❄️", "name": "Snow tomato", "season": "winter",
     "note": "Only falls from the machine in winter."},
    {"id": "blossom", "tier": "legendary", "kind": "skin", "emoji": "🌸", "name": "Blossom tomato", "season": "spring",
     "note": "Only blooms in the machine in spring."},
    {"id": "sunburnt", "tier": "legendary", "kind": "skin", "emoji": "☀️", "name": "Sunburnt tomato", "season": "summer",
     "note": "Only in the machine in summer. Wear sunscreen."},
    {"id": "jack", "tier": "legendary", "kind": "skin", "emoji": "🎃", "name": "Jack-o'-tomato", "season": "autumn",
     "note": "Only in the machine in autumn. Spooky and juicy."},
]
BY_ID = {p["id"]: p for p in PRIZES}
STACKS = ("seed", "decor")          # you can own many
EQUIP = ("badge", "trail", "hat")   # one of each worn at a time


def season(today=None):
    month = (today or timezone.now().date()).month
    return next(name for name, months in SEASONS.items() if month in months)


def pool(tier, today=None):
    now = season(today)
    return [p for p in PRIZES if p["tier"] == tier and p.get("season") in (None, now)]


def _state(score):
    m = dict(score.machine or {})
    for k in ("used", "bonus", "golden", "compost", "pity_rare", "pity_legend"):
        m[k] = int(m.get(k) or 0)
    m["items"] = dict(m.get("items") or {})
    m["equipped"] = dict(m.get("equipped") or {})
    m["history"] = list(m.get("history") or [])
    m["promise"] = m.get("promise") if m.get("promise") in BY_ID else None
    m["promise_sure"] = bool(m.get("promise_sure"))
    return m


def spins_left(score, m=None):
    m = m or _state(score)
    return max(0, score.wild // SPIN_COST + m["bonus"] - m["used"])


def add_golden(score, n):
    """Free spins for golden splats thrown at chats or Bulba. At most about one per 250 such throws (they're 1 in
    500), so a browser can't simply claim them."""
    m = _state(score)
    room = max(0, score.wild // 250 + 1 - m["golden"])
    got = max(0, min(int(n), room))
    if got:
        m["golden"] += got
        m["bonus"] += got
        score.machine = m
    return got


def _tier(m, rng):
    if m["pity_legend"] + 1 >= LEGEND_PITY:
        return "legendary"
    roll = rng.random() * 100
    tier = "legendary" if roll < ODDS["legendary"] else "rare" if roll < ODDS["legendary"] + ODDS["rare"] else "common"
    if tier == "common" and m["pity_rare"] + 1 >= RARE_PITY:
        tier = "rare"
    return tier


def _legendary(m, rng, today):
    choices = pool("legendary", today)
    promised = BY_ID.get(m["promise"]) if m["promise"] else None
    if promised and promised in choices:
        if m["promise_sure"] or rng.random() < .5:
            m["promise_sure"] = False
            return promised, "promise"
        m["promise_sure"] = True  # lost the 50/50: the next legendary is the promised one
        others = [p for p in choices if p["id"] != promised["id"]]
        return rng.choice(others or choices), "lost"
    return rng.choice(choices), ""


def _draw(m, rng, today):
    tier = _tier(m, rng)
    how = ""
    if tier == "legendary":
        prize, how = _legendary(m, rng, today)
        m["pity_legend"], m["pity_rare"] = 0, 0
    else:
        prize = rng.choice(pool(tier, today))
        m["pity_legend"] += 1
        m["pity_rare"] = 0 if tier == "rare" else m["pity_rare"] + 1
    had = m["items"].get(prize["id"], 0)
    dup = had > 0 and prize["kind"] not in STACKS
    compost = COMPOST_FOR[tier] if dup else 0
    if dup:
        m["compost"] += compost
    else:
        m["items"][prize["id"]] = had + 1
    return {"id": prize["id"], "tier": tier, "dup": dup, "compost": compost, "promise": how}


def spin(user, n=1, rng=None, today=None):
    """Spend `n` spins (1 or 10). Returns (results, state) or raises ValueError with a message for the person."""
    from mainapp import tomatoes
    from mainapp.models import TomatoScore
    if n not in (1, 10):
        raise ValueError("One spin or ten.")
    rng = rng or random.SystemRandom()
    with transaction.atomic():
        tomatoes.score_of(user)
        score = TomatoScore.objects.select_for_update().get(user=user)
        m = _state(score)
        left = spins_left(score, m)
        if left < n:
            raise ValueError("Not enough spins. Throw more tomatoes at slow replies." if not left
                             else f"You have {left} spin{'s' if left != 1 else ''}, not {n}.")
        results = []
        for _ in range(n):
            m["used"] += 1
            results.append(_draw(m, rng, today))
        when = timezone.now().isoformat(timespec="seconds")
        m["history"] = ([{**r, "at": when} for r in reversed(results)] + m["history"])[:HISTORY]
        score.machine = m
        score.save(update_fields=["machine"])
    return results, public(score)


def _change(user, fn):
    from mainapp import tomatoes
    from mainapp.models import TomatoScore
    with transaction.atomic():
        tomatoes.score_of(user)
        score = TomatoScore.objects.select_for_update().get(user=user)
        m = _state(score)
        fn(m)
        score.machine = m
        score.save(update_fields=["machine"])
    return public(score)


def promise(user, prize_id):
    """Pick (or, with None, drop) the legendary Bulba promises."""
    if prize_id is not None and (BY_ID.get(prize_id) or {}).get("tier") != "legendary":
        raise ValueError("Bulba only promises legendaries.")

    def go(m):
        if m["promise"] != prize_id:
            m["promise"], m["promise_sure"] = prize_id, False  # a new pick starts a fresh 50/50
    return _change(user, go)


def compost_spin(user):
    def go(m):
        if m["compost"] < COMPOST_SPIN:
            raise ValueError(f"It takes {COMPOST_SPIN} compost to make a spin.")
        m["compost"] -= COMPOST_SPIN
        m["bonus"] += 1
    return _change(user, go)


def equip(user, slot, prize_id):
    if slot not in EQUIP:
        raise ValueError("Nothing to wear there.")

    def go(m):
        if prize_id is None:
            m["equipped"].pop(slot, None)
            return
        p = BY_ID.get(prize_id)
        if not p or p["kind"] != slot or not m["items"].get(prize_id):
            raise ValueError("You don't have that one.")
        m["equipped"][slot] = prize_id
    return _change(user, go)


def worn(score):
    """What they wear, as emoji: {"badge": "🔥", "trail": "trail_sparkle", "hat": "👑"} (empty slots left out)."""
    m = _state(score)
    out = {}
    for slot, pid in m["equipped"].items():
        p = BY_ID.get(pid)
        if p and slot in EQUIP and m["items"].get(pid):
            out[slot] = pid if slot == "trail" else p["emoji"]
    return out


def owned_skins(score):
    m = _state(score)
    return [pid for pid, n in m["items"].items() if n and (BY_ID.get(pid) or {}).get("kind") == "skin"]


def public(score, today=None):
    """What the Pit shows: spins, progress to the next one, pity, the promise, the collection, the odds."""
    m = _state(score)
    now = season(today)
    return {
        "spins": spins_left(score, m), "cost": SPIN_COST, "toward": score.wild % SPIN_COST,
        "compost": m["compost"], "compost_spin": COMPOST_SPIN, "golden": m["golden"],
        "pity": {"rare": m["pity_rare"], "rare_at": RARE_PITY, "legend": m["pity_legend"], "legend_at": LEGEND_PITY},
        "promise": m["promise"], "promise_sure": m["promise_sure"],
        "items": m["items"], "equipped": m["equipped"], "history": m["history"][:20],
        "odds": ODDS, "season": now,
        "prizes": [{**p, "now": p.get("season") in (None, now)} for p in PRIZES],
    }
