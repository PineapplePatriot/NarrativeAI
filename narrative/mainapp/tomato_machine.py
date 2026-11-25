"""
🎰 The Sauce-o-Matic: a prize machine in the Tomato Pit that runs on tomatoes, never money.

Spins
- One on the house (START_SPINS), then one for every SPIN_COST tomatoes thrown at chats and Bulba (TomatoScore.wild, mainapp/tomatoes.py), plus:
- a free one for each golden splat (1 in 500) thrown at a chat or Bulba, and
- one for every COMPOST_SPIN compost (what duplicates turn into), and
- the garden's tomatoes: filled orders pay tomatoes ("earned", counted with the thrown ones toward spins, not on the
  leaderboard), and a rare mutation is a free spin (mainapp/tomato_garden.py).

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
START_SPINS = 1     # everyone gets one pull on the house
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
    {"id": "seed_peas", "tier": "common", "kind": "seed", "emoji": "🫛", "name": "Pea seeds",
     "note": "They climb. They have ambitions."},
    {"id": "seed_beet", "tier": "common", "kind": "seed", "emoji": "🍠", "name": "Beetroot seeds",
     "note": "Nonna Lyuba has opinions about what these are for."},
    {"id": "seed_basil", "tier": "common", "kind": "seed", "emoji": "🌿", "name": "Basil seeds",
     "note": "Not to be confused with Basil. She'll tell you."},
    {"id": "seed_garlic", "tier": "common", "kind": "seed", "emoji": "🧄", "name": "Garlic cloves",
     "note": "Plant one, get a whole bulb. Crows hate it."},
    {"id": "seed_strawberry", "tier": "common", "kind": "seed", "emoji": "🍓", "name": "Strawberry runners",
     "note": "Sweet, red, and gone before you get them indoors."},
    {"id": "birdbath", "tier": "common", "kind": "decor", "emoji": "🐦", "img": "/static/img/tomato/deco_birdbath.svg", "name": "Birdbath",
     "note": "A robin comes to visit. Sir Corvin pretends not to care."},
    {"id": "wheelbarrow", "tier": "common", "kind": "decor", "emoji": "🛒", "img": "/static/img/tomato/deco_wheelbarrow.svg",
     "name": "Wheelbarrow", "note": "Full of soil. Leaning slightly. Like all of us."},
    {"id": "watering_can", "tier": "common", "kind": "decor", "emoji": "🚿", "img": "/static/img/tomato/deco_watering_can.svg",
     "name": "Watering can", "note": "Blue, with a pink heart. Grandpa Pomodoro won't let anyone else hold it."},
    {"id": "gnome", "tier": "common", "kind": "decor", "emoji": "🗿", "name": "Garden gnome, unimpressed",
     "note": "He has seen your throwing. He is not impressed."},
    # --- Rare ---
    {"id": "seed_pumpkin", "tier": "rare", "kind": "seed", "emoji": "🎃", "name": "Pumpkin seeds",
     "note": "Grows slowly, grows big, judges you."},
    {"id": "sundial", "tier": "rare", "kind": "decor", "emoji": "🕰️", "img": "/static/img/tomato/deco_sundial.svg", "name": "Sundial",
     "note": "Tells the time, but only when it's sunny. Very principled."},
    {"id": "beehive", "tier": "rare", "kind": "decor", "emoji": "🐝", "img": "/static/img/tomato/deco_beehive.svg", "name": "Beehive",
     "note": "Old Man Pepper approves. The bees approve of nobody."},
    {"id": "fairy_arch", "tier": "rare", "kind": "decor", "emoji": "✨", "img": "/static/img/tomato/deco_fairy_arch.svg",
     "name": "Fairy-light arch", "note": "Lights up at night. Something lives in it. Probably moths."},
    {"id": "seed_eggplant", "tier": "rare", "kind": "seed", "emoji": "🍆", "name": "Eggplant seeds",
     "note": "Glossy. Purple. Knows it."},
    {"id": "seed_pepper", "tier": "rare", "kind": "seed", "emoji": "🫑", "name": "Bell pepper seeds",
     "note": "Hollow inside, like a good joke."},
    {"id": "seed_chili", "tier": "rare", "kind": "seed", "emoji": "🌶️", "name": "Chili seeds",
     "note": "Handle with gloves. You have one."},
    {"id": "seed_blueberry", "tier": "rare", "kind": "seed", "emoji": "🫐", "name": "Blueberry bush",
     "note": "Old Man Pepper's bees will thank you."},
    {"id": "seed_watermelon", "tier": "rare", "kind": "seed", "emoji": "🍉", "name": "Watermelon seeds",
     "note": "Takes forever. Worth it. Ask anyone in August."},
    {"id": "seed_mandrake", "tier": "rare", "kind": "seed", "emoji": "🫚", "name": "Mandrake seeds",
     "note": "Earmuffs not included. Bulba suggests earmuffs."},
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
    # --- 🏮 Lantern Night (the autumn banner): only from its banner, while it runs ---
    {"id": "lantern_tomato", "tier": "legendary", "kind": "skin", "emoji": "🏮", "name": "Lantern tomato", "banner": "lantern",
     "note": "Glows from the inside. Lights your way to the slow replies."},
    {"id": "gardener_death", "tier": "legendary", "kind": "gardener", "emoji": "💀", "name": "Mr. Death", "banner": "lantern",
     "note": "Very polite. Collects his dues: every third harvest brings three extra compost."},
    {"id": "seed_monster", "tier": "rare", "kind": "seed", "emoji": "🌺", "name": "Monstrous flower seeds", "banner": "lantern",
     "note": "Grows big, grows teeth. Don't feed it after midnight. Do feed it before."},
    {"id": "trail_wisp", "tier": "rare", "kind": "trail", "emoji": "🔥", "name": "Cursor trail: will-o'-wisps", "banner": "lantern",
     "note": "Little blue flames follow your cursor. Don't follow them back."},
    {"id": "companion_lantern", "tier": "rare", "kind": "companion", "emoji": "🏮", "name": "Corner lantern", "banner": "lantern",
     "note": "A small paper lantern hangs in the corner of every page and sways. Tap it."},
    # --- ❄️ First Snow (the winter banner): only from its banner, while it runs ---
    {"id": "globe_tomato", "tier": "legendary", "kind": "skin", "emoji": "🔮", "img": "/static/img/tomato/snow_globe.png",
     "name": "Snow globe tomato", "banner": "winter",
     "note": "A whole winter inside a tomato. Shake well before throwing."},
    {"id": "gardener_babbo", "tier": "legendary", "kind": "gardener", "emoji": "🎅", "name": "Babbo Natale", "banner": "winter",
     "note": "Not that other one. Once a day he leaves a present in the shed: seeds, wrapped badly, with love."},
    {"id": "snowman", "tier": "rare", "kind": "decor", "emoji": "⛄", "name": "Snowman", "banner": "winter",
     "note": "Carrot nose, coal smile, no opinions. Bulba is suspicious anyway."},
    {"id": "trail_snow", "tier": "rare", "kind": "trail", "emoji": "❄️", "name": "Cursor trail: snowflakes", "banner": "winter",
     "note": "Snowflakes drift down wherever your cursor goes."},
    {"id": "companion_globe", "tier": "rare", "kind": "companion", "emoji": "🌨️", "name": "Corner snow globe", "banner": "winter",
     "note": "A tiny snow globe sits in the corner of every page. Tap it, and it snows."},
]
BY_ID = {p["id"]: p for p in PRIZES}
STACKS = ("seed", "decor")          # you can own many
EQUIP = ("badge", "trail", "hat", "companion")   # one of each worn at a time

# Banners: the standard one holds everything that isn't a banner's own; a seasonal banner runs for its month
# (Lantern Night in November, First Snow in December), with its featured things at a rate-up: a legendary from it is a featured one half the time (and surely
# the next time, after a miss); a rare is a featured one half the time too (surely after a miss). Bulba's Promise
# there picks which featured legendary.
BANNERS = {
    "standard": {"name": "Standard", "emoji": "🎰", "tagline": "Everything the machine always has.", "months": None},
    "lantern": {"name": "Lantern Night", "emoji": "🏮", "months": (11,),
                "tagline": "When the lanterns are lit, something tall and polite comes to tend the garden.",
                "featured": {"legendary": ["lantern_tomato", "gardener_death"],
                             "rare": ["seed_monster", "trail_wisp", "companion_lantern"]}},
    "winter": {"name": "First Snow", "emoji": "❄️", "months": (12,), "art": "/static/img/tomato/snow_globe.png",
               "tagline": "The snow came early, and someone in a red coat is humming in the garden. Not that one. The other one.",
               "featured": {"legendary": ["globe_tomato", "gardener_babbo"],
                            "rare": ["snowman", "trail_snow", "companion_globe"]}},
}


def season(today=None):
    month = (today or timezone.now().date()).month
    return next(name for name, months in SEASONS.items() if month in months)


def pool(tier, today=None):
    """The standard banner's things of a tier (seasonal skins in their season; no banner's own)."""
    now = season(today)
    return [p for p in PRIZES if p["tier"] == tier and p.get("season") in (None, now) and not p.get("banner")]


def banner_open(bid, today=None):
    b = BANNERS.get(bid)
    if not b:
        return False
    return b["months"] is None or (today or timezone.now().date()).month in b["months"]


def banner_ends(bid, today=None):
    """The last day a seasonal banner runs (this year's last month of it), or None."""
    import calendar
    from datetime import date
    b = BANNERS.get(bid) or {}
    if not b.get("months") or not banner_open(bid, today):
        return None
    d = today or timezone.now().date()
    last = max(b["months"])
    return date(d.year, last, calendar.monthrange(d.year, last)[1])


def _state(score):
    m = dict(score.machine or {})
    for k in ("used", "bonus", "golden", "compost", "pity_rare", "pity_legend", "earned"):
        m[k] = int(m.get(k) or 0)
    m["items"] = dict(m.get("items") or {})
    m["equipped"] = dict(m.get("equipped") or {})
    m["history"] = list(m.get("history") or [])
    m["promise"] = m.get("promise") if m.get("promise") in BY_ID else None
    m["promise_sure"] = bool(m.get("promise_sure"))
    banners = dict(m.get("banners") or {})  # each seasonal banner's own pity, guarantees and promise
    for bid in BANNERS:
        if bid == "standard":
            continue
        b = dict(banners.get(bid) or {})
        for k in ("pity_rare", "pity_legend"):
            b[k] = int(b.get(k) or 0)
        b["sure"], b["sure_rare"] = bool(b.get("sure")), bool(b.get("sure_rare"))
        b["promise"] = b.get("promise") if b.get("promise") in BANNERS[bid]["featured"]["legendary"] else None
        banners[bid] = b
    m["banners"] = banners
    return m


def spins_left(score, m=None):
    m = m or _state(score)
    return max(0, START_SPINS + (score.wild + m["earned"]) // SPIN_COST + m["bonus"] - m["used"])


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


def _featured_draw(b, banner, tier, rng, today):
    """On a seasonal banner: (prize, how) for a legendary or rare, with its rate-up and guarantee."""
    featured = [BY_ID[i] for i in banner["featured"].get(tier, [])]
    key = "sure" if tier == "legendary" else "sure_rare"
    if featured and (b[key] or rng.random() < .5):
        b[key] = False
        if tier == "legendary" and b["promise"]:
            return BY_ID[b["promise"]], "promise"
        return rng.choice(featured), "featured"
    b[key] = True  # missed the rate-up: the next one of this tier is featured
    return rng.choice(pool(tier, today)), "lost" if tier == "legendary" else ""


def _draw(m, rng, today, bid="standard"):
    if bid != "standard":  # a seasonal banner: its own pity and guarantees
        b, banner = m["banners"][bid], BANNERS[bid]
        tier = _tier(b, rng)
        if tier == "common":
            prize, how = rng.choice(pool("common", today)), ""
            b["pity_legend"] += 1
            b["pity_rare"] += 1
        else:
            prize, how = _featured_draw(b, banner, tier, rng, today)
            if tier == "legendary":
                b["pity_legend"], b["pity_rare"] = 0, 0
            else:
                b["pity_legend"] += 1
                b["pity_rare"] = 0
        return _keep(m, prize, tier, how, bid)
    tier = _tier(m, rng)
    how = ""
    if tier == "legendary":
        prize, how = _legendary(m, rng, today)
        m["pity_legend"], m["pity_rare"] = 0, 0
    else:
        prize = rng.choice(pool(tier, today))
        m["pity_legend"] += 1
        m["pity_rare"] = 0 if tier == "rare" else m["pity_rare"] + 1
    return _keep(m, prize, tier, how, bid)


def _keep(m, prize, tier, how, bid):
    had = m["items"].get(prize["id"], 0)
    dup = had > 0 and prize["kind"] not in STACKS
    compost = COMPOST_FOR[tier] if dup else 0
    if dup:
        m["compost"] += compost
    else:
        m["items"][prize["id"]] = had + 1
    return {"id": prize["id"], "tier": tier, "dup": dup, "compost": compost, "promise": how, "banner": bid}


def spin(user, n=1, rng=None, today=None, banner="standard"):
    """Spend `n` spins (1 or 10) on a banner. Returns (results, state) or raises ValueError with a message for
    the person."""
    from mainapp import tomatoes
    from mainapp.models import TomatoScore
    if n not in (1, 10):
        raise ValueError("One spin or ten.")
    if not banner_open(banner, today):
        raise ValueError("That banner isn't running right now.")
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
            results.append(_draw(m, rng, today, banner))
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


def promise(user, prize_id, banner="standard"):
    """Pick (or, with None, drop) the legendary Bulba promises (on a seasonal banner: one of its featured ones)."""
    if prize_id is not None and (BY_ID.get(prize_id) or {}).get("tier") != "legendary":
        raise ValueError("Bulba only promises legendaries.")
    if banner != "standard":
        if banner not in BANNERS:
            raise ValueError("No such banner.")
        if prize_id is not None and prize_id not in BANNERS[banner]["featured"]["legendary"]:
            raise ValueError("On this banner Bulba promises one of its featured legendaries.")

        def pick(m):
            m["banners"][banner]["promise"] = prize_id
        return _change(user, pick)
    if prize_id is not None and BY_ID[prize_id].get("banner"):
        raise ValueError("That one is only on its own banner.")

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
            out[slot] = pid if slot in ("trail", "companion") else p["emoji"]
    return out


def owned_skins(score):
    m = _state(score)
    return [pid for pid, n in m["items"].items() if n and (BY_ID.get(pid) or {}).get("kind") == "skin"]


def public(score, today=None):
    """What the Pit shows: spins, progress to the next one, pity, the promise, the collection, the odds."""
    m = _state(score)
    now = season(today)
    return {
        "spins": spins_left(score, m), "cost": SPIN_COST, "toward": (score.wild + m["earned"]) % SPIN_COST, "earned": m["earned"],
        "compost": m["compost"], "compost_spin": COMPOST_SPIN, "golden": m["golden"],
        "pity": {"rare": m["pity_rare"], "rare_at": RARE_PITY, "legend": m["pity_legend"], "legend_at": LEGEND_PITY},
        "promise": m["promise"], "promise_sure": m["promise_sure"],
        "items": m["items"], "equipped": m["equipped"], "history": m["history"][:20],
        "odds": ODDS, "season": now,
        "prizes": [{**p, "now": p.get("season") in (None, now) and (not p.get("banner") or banner_open(p["banner"], today))}
                   for p in PRIZES],
        "banners": [{"id": bid, "name": b["name"], "emoji": b["emoji"], "tagline": b["tagline"], "art": b.get("art", ""),
                     "featured": b.get("featured") or {}, "open": banner_open(bid, today),
                     "ends": (banner_ends(bid, today).isoformat() if banner_ends(bid, today) else None),
                     **({k: m["banners"][bid][k] for k in ("pity_rare", "pity_legend", "sure", "sure_rare", "promise")}
                        if bid != "standard" else {})}
                    for bid, b in sorted(BANNERS.items(), key=lambda kv: kv[0] == "standard")  # the seasonal one first
                    if bid == "standard" or banner_open(bid, today)],
    }
