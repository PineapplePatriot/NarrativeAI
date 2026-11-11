"""
🌻 The garden: where the Sauce-o-Matic's seeds, decorations and gardeners go (a live page, tomato_garden.js).

- A plot of COLS × ROWS tiles. A tile holds a plant or a decoration.
- Plants grow over real time (CROPS: hours to ripe), through seed → sprout → leafy → bloom → ripe.
- Tomatoes thrown at chats and Bulba water the garden: each one adds WATER seconds of growth to every plant
  (mainapp/tomatoes.add_wild calls water()).
- A ripe plant is harvested for compost (the machine's: 10 compost = a spin). Planting uses up the seed.
- Decorations are placed from the basket and can go back into it (owned stays owned; placed ones are counted).
- Gardeners live in the garden once won, and each helps:
    Grandpa Pomodoro  plants grow 25% faster
    Ribbit            +1 compost on every harvest (he carries the basket)
    Hoe-Bot 3000      harvests ripe plants by himself
    Basil             every second harvest gives the seed back
Everything is kept in TomatoScore.garden (JSON); the time is always the server's.
"""
from django.db import transaction
from django.utils import timezone

from mainapp import tomato_machine as M

COLS, ROWS = 8, 5
WATER = 120          # seconds of growth per chat tomato
LOG = 30
CROPS = {  # seed id → what grows
    "seed_tomato": {"name": "Tomato", "hours": 24, "compost": 2},
    "seed_carrot": {"name": "Carrot", "hours": 18, "compost": 2},
    "seed_sunflower": {"name": "Sunflower", "hours": 30, "compost": 3},
    "seed_pumpkin": {"name": "Pumpkin", "hours": 48, "compost": 6},
}
STAGES = ((0.15, "seed"), (0.4, "sprout"), (0.7, "leafy"), (1.0, "bloom"))
DECOR = ("gnome", "bench", "scarecrow", "pond", "lantern")
GARDENERS = {
    "gardener_farmer": "Plants grow 25% faster: he waters everything, including things that aren't plants.",
    "gardener_frog": "+1 compost on every harvest: he carries the basket.",
    "gardener_robot": "Harvests ripe plants by himself, on schedule.",
    "gardener_witch": "Every second harvest gives the seed back. Nobody knows the song.",
}


def _now():
    return timezone.now().timestamp()


def _state(score):
    g = dict(score.garden or {})
    g["tiles"] = {k: dict(v) for k, v in (g.get("tiles") or {}).items() if isinstance(v, dict)}
    g["log"] = list(g.get("log") or [])
    for k in ("harvests", "watered"):
        g[k] = int(g.get(k) or 0)
    return g


def _key(x, y):
    if not (isinstance(x, int) and isinstance(y, int) and 0 <= x < COLS and 0 <= y < ROWS):
        raise ValueError("That's outside the garden.")
    return f"{x},{y}"


def _has(m, pid):
    return bool(m["items"].get(pid))


def progress(tile, m, now=None):
    """0..1: how grown a plant is (time since planting, faster with Grandpa Pomodoro, plus watering)."""
    crop = CROPS.get(tile.get("seed"))
    if not crop:
        return 0.0
    speed = 1.25 if _has(m, "gardener_farmer") else 1.0
    grown = max(0.0, ((now or _now()) - tile.get("at", 0)) * speed + tile.get("boost", 0))
    return min(1.0, grown / (crop["hours"] * 3600))


def stage(p):
    return next((name for limit, name in STAGES if p < limit), "ripe")


def _log(g, text):
    g["log"] = ([{"at": int(_now()), "text": text}] + g["log"])[:LOG]


def _harvest(g, m, key, by=""):
    tile = g["tiles"].pop(key)
    crop = CROPS[tile["seed"]]
    got = crop["compost"] + (1 if _has(m, "gardener_frog") else 0)
    m["compost"] += got
    g["harvests"] += 1
    back = _has(m, "gardener_witch") and g["harvests"] % 2 == 0
    if back:
        m["items"][tile["seed"]] = m["items"].get(tile["seed"], 0) + 1
    _log(g, f"{by or 'You'} harvested a {crop['name'].lower()}: ♻ +{got} compost" + (" and Basil hummed the seed back" if back else "") + ".")
    return got


def _robot(g, m, now=None):
    """Hoe-Bot 3000 harvests whatever is ripe."""
    if not _has(m, "gardener_robot"):
        return 0
    ripe = [k for k, t in g["tiles"].items() if t.get("kind") == "plant" and progress(t, m, now) >= 1]
    return sum(_harvest(g, m, k, by="Hoe-Bot 3000") for k in ripe)


def _locked(user, fn):
    from mainapp import tomatoes
    from mainapp.models import TomatoScore
    with transaction.atomic():
        tomatoes.score_of(user)
        score = TomatoScore.objects.select_for_update().get(user=user)
        m, g = M._state(score), _state(score)
        fn(g, m)
        _robot(g, m)
        score.machine, score.garden = m, g
        score.save(update_fields=["machine", "garden"])
    return public(score)


def water(score, n):
    """Chat tomatoes water every growing plant (called while add_wild holds the score; the caller saves)."""
    if n <= 0 or not score.garden:
        return
    g = _state(score)
    plants = [t for t in g["tiles"].values() if t.get("kind") == "plant"]
    if not plants:
        return
    for t in plants:
        t["boost"] = t.get("boost", 0) + n * WATER
    g["watered"] += n
    score.garden = g


def placed(g, pid):
    return sum(1 for t in g["tiles"].values() if t.get("kind") == "decor" and t.get("id") == pid)


def act(user, body):
    """One thing done in the garden: plant, place, harvest, dig, remove. Raises ValueError for the person."""
    action = body.get("action")
    key = _key(body.get("x"), body.get("y"))
    pid = body.get("id")

    def go(g, m):
        tile = g["tiles"].get(key)
        if action == "plant":
            if tile:
                raise ValueError("Something is already there.")
            if pid not in CROPS or not m["items"].get(pid):
                raise ValueError("You have no seeds of that kind. The Sauce-o-Matic does.")
            m["items"][pid] -= 1
            g["tiles"][key] = {"kind": "plant", "seed": pid, "at": int(_now()), "boost": 0}
            _log(g, f"You planted a {CROPS[pid]['name'].lower()}.")
        elif action == "place":
            if tile:
                raise ValueError("Something is already there.")
            if pid not in DECOR or m["items"].get(pid, 0) - placed(g, pid) < 1:
                raise ValueError("You don't have one of those to place.")
            g["tiles"][key] = {"kind": "decor", "id": pid}
            _log(g, f"You placed the {M.BY_ID[pid]['name'].lower()}.")
        elif action == "harvest":
            if not tile or tile.get("kind") != "plant" or progress(tile, m) < 1:
                raise ValueError("Nothing ripe there yet.")
            _harvest(g, m, key)
        elif action == "dig":
            if not tile or tile.get("kind") != "plant":
                raise ValueError("No plant there.")
            g["tiles"].pop(key)
            _log(g, f"You dug up a {CROPS[tile['seed']]['name'].lower()} before it was ready.")
        elif action == "remove":
            if not tile or tile.get("kind") != "decor":
                raise ValueError("No decoration there.")
            g["tiles"].pop(key)
            _log(g, f"The {M.BY_ID[tile['id']]['name'].lower()} went back into the basket.")
        else:
            raise ValueError("Unknown action.")
    return _locked(user, go)


def visit(user):
    """The garden as it is now (Hoe-Bot gets to work first)."""
    return _locked(user, lambda g, m: None)


def public(score):
    m, g = M._state(score), _state(score)
    now = _now()
    tiles = []
    for key, t in g["tiles"].items():
        x, y = (int(v) for v in key.split(","))
        item = {"x": x, "y": y, "kind": t.get("kind")}
        if t.get("kind") == "plant":
            p = progress(t, m, now)
            crop = CROPS[t["seed"]]
            speed = 1.25 if _has(m, "gardener_farmer") else 1.0
            item.update(seed=t["seed"], name=crop["name"], progress=round(p, 4), stage=stage(p),
                        left=int(max(0, (1 - p) * crop["hours"] * 3600 / speed)), rate=speed / (crop["hours"] * 3600))
        else:
            item["id"] = t.get("id")
        tiles.append(item)
    basket = {pid: n for pid, n in m["items"].items() if pid in CROPS and n > 0}
    basket.update({pid: m["items"][pid] - placed(g, pid) for pid in DECOR if m["items"].get(pid, 0) - placed(g, pid) > 0})
    return {"cols": COLS, "rows": ROWS, "tiles": tiles, "basket": basket, "compost": m["compost"],
            "gardeners": [{"id": pid, "about": about} for pid, about in GARDENERS.items() if _has(m, pid)],
            "hat": M.worn(score).get("hat", ""), "log": g["log"][:12], "harvests": g["harvests"],
            "water": WATER, "crops": CROPS, "now": int(now),
            "prizes": {p["id"]: {"name": p["name"], "emoji": p["emoji"]} for p in M.PRIZES
                       if p["kind"] in ("seed", "decor", "gardener")}}
