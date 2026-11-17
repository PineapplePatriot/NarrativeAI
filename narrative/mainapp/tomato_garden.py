"""
🌻 The garden: where the Sauce-o-Matic's seeds, decorations and gardeners go (a live page, tomato_garden.js).

- A plot of COLS × ROWS tiles. A tile holds a plant or a decoration.
- Plants grow over real time (CROPS: hours to ripe), through seed → sprout → leafy → bloom → ripe.
- Tomatoes thrown at chats and Bulba water the garden: each one adds WATER seconds of growth to every plant
  (mainapp/tomatoes.add_wild calls water()).
- A ripe plant is harvested for compost (the machine's: 10 compost = a spin). Planting uses up the seed.
- Decorations are placed from the basket and can go back into it (owned stays owned; placed ones are counted).
- Gardeners live in the garden once won, three at a time (CREW: they pick which; the rest rest in the shed), and
  each one at work helps:
    Grandpa Pomodoro  plants grow 25% faster
    Ribbit            +1 compost on every harvest (he carries the basket)
    Hoe-Bot 3000      harvests ripe plants by himself
    Basil             every second harvest gives the seed back
    Mr. Death         every third harvest brings 3 extra compost (Lantern Night banner)
    Babbo Natale      once a day leaves a present in the shed: a packet of seeds (First Snow banner)
- The order board: neighbours post orders for crops ("3 carrots"). A new one each day, at most ORDERS_OPEN open, each
  open for ORDER_DAYS days. Harvests count toward the oldest open order for that crop (and still give compost);
  a filled order pays 100-300 tomatoes, which count toward spins (not the leaderboard: TomatoScore.machine "earned").
- Mutations: 1 in MUTATION_ODDS harvests is a strange variant (MUTATIONS), kept in the almanac. The common ones
  give triple compost; the rare one of each crop gives a free spin. A mutation also gives one of its seeds
  (VARIANT_SEEDS): planted, it grows like its crop and comes out as the variant again KEEP of the time (with
  its seed back, so a line can go on); otherwise it's an ordinary harvest of that crop.
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
    "seed_monster": {"name": "Monstrous flower", "hours": 40, "compost": 8},
}
STAGES = ((0.15, "seed"), (0.4, "sprout"), (0.7, "leafy"), (1.0, "bloom"))
DECOR = ("gnome", "bench", "scarecrow", "pond", "lantern", "snowman")
GARDENERS = {
    "gardener_farmer": "Plants grow 25% faster: he waters everything, including things that aren't plants.",
    "gardener_frog": "+1 compost on every harvest: he carries the basket.",
    "gardener_robot": "Harvests ripe plants by himself, on schedule.",
    "gardener_witch": "Every second harvest gives the seed back. Nobody knows the song.",
    "gardener_death": "Every third harvest brings three extra compost: he collects his dues, very politely.",
    "gardener_babbo": "Once a day he leaves a present in the shed: a packet of seeds, wrapped badly, with love.",
}
ORDERS_OPEN = 3
ORDER_DAYS = 3
NEIGHBOURS = ("Signora Rosa", "the bakery", "Old Man Pepper", "the pizzeria", "Bulba (suspicious)", "the soup kitchen",
              "a very polite crow", "the village fair")
MUTATION_ODDS = 20
# crop → its strange variants: (id, emoji, name, rare). A rare one gives a spin; the others triple the compost.
MUTATIONS = {
    "seed_tomato": [("heart_tomato", "❤️", "Heart-shaped tomato", False), ("stripy_tomato", "🦓", "Stripy tomato", False),
                    ("golden_tomato", "🌟", "Golden tomato", True)],
    "seed_carrot": [("twin_carrot", "🥕", "Twin carrots, holding hands", False), ("purple_carrot", "🟣", "Purple carrot", False),
                    ("legs_carrot", "🦵", "A carrot with legs", True)],
    "seed_sunflower": [("giant_sunflower", "🌻", "Giant sunflower", False), ("night_sunflower", "🌙", "Moonflower (it faces the moon)", False),
                       ("winking_sunflower", "😉", "A sunflower that winks", True)],
    "seed_pumpkin": [("giant_pumpkin", "🎃", "Giant pumpkin", False), ("smiling_pumpkin", "😊", "A pumpkin that smiles back", False),
                     ("glass_pumpkin", "🔮", "Glass pumpkin", True)],
    "seed_monster": [("glowing_monster", "✨", "Glowing monstrous flower", False), ("sleepy_monster", "😴", "Sleepy monstrous flower", False),
                     ("polite_monster", "🎩", "A very polite monstrous flower", True)],
}
MUTANT = {mid: {"id": mid, "crop": crop, "emoji": e, "name": n, "rare": r} for crop, ms in MUTATIONS.items() for mid, e, n, r in ms}
# Seeds of the variants: they grow like their crop (seed id "seed_<mutation id>")
KEEP = {False: .5, True: .25}  # how often a planted variant comes out as itself (common / rare)
VARIANT_SEEDS = {f"seed_{mid}": mid for mid in MUTANT}
for _sid, _mid in VARIANT_SEEDS.items():
    _base = CROPS[MUTANT[_mid]["crop"]]
    CROPS[_sid] = {"name": MUTANT[_mid]["name"], "hours": _base["hours"], "compost": _base["compost"],
                   "base": MUTANT[_mid]["crop"], "variant": _mid}


def base(seed):
    """The ordinary crop a seed belongs to (a variant's crop, or itself)."""
    return CROPS.get(seed, {}).get("base") or seed


# Babbo Natale's presents: mostly everyday seeds, now and then a pumpkin
GIFTS = (("seed_tomato", 3), ("seed_carrot", 3), ("seed_sunflower", 2), ("seed_pumpkin", 1))


def _now():
    return timezone.now().timestamp()


def _state(score):
    g = dict(score.garden or {})
    g["tiles"] = {k: dict(v) for k, v in (g.get("tiles") or {}).items() if isinstance(v, dict)}
    g["log"] = list(g.get("log") or [])
    for k in ("harvests", "watered", "filled", "order_seq"):
        g[k] = int(g.get(k) or 0)
    g["orders"] = [dict(o) for o in (g.get("orders") or []) if isinstance(o, dict) and o.get("seed") in CROPS]
    g["almanac"] = {k: int(v) for k, v in (g.get("almanac") or {}).items() if k in MUTANT}
    return g


def _key(x, y):
    if not (isinstance(x, int) and isinstance(y, int) and 0 <= x < COLS and 0 <= y < ROWS):
        raise ValueError("That's outside the garden.")
    return f"{x},{y}"


CREW = 3  # gardeners working at once: they pick which, the others rest in the shed (no stacking every bonus)


def crew(m):
    """The gardeners at work: the ones they picked (still owned), else the first CREW they own."""
    owned = [pid for pid in GARDENERS if m["items"].get(pid)]
    picked = m.get("crew")
    if isinstance(picked, list):
        return [pid for pid in picked if pid in owned][:CREW]
    return owned[:CREW]


def _has(m, pid):
    if pid in GARDENERS:  # a gardener helps only while at work
        return pid in crew(m)
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


def _mutate(g, m, seed, rng=None):
    """1 in MUTATION_ODDS harvests: a strange variant (a rare one a quarter of the time); a planted variant comes
    out as itself KEEP of the time. Each one gives a seed of itself. Returns it or None."""
    import random
    rng = rng or random.SystemRandom()
    planted = CROPS.get(seed, {}).get("variant")
    if planted and rng.random() < KEEP[MUTANT[planted]["rare"]]:
        mid = planted
    else:
        variants = MUTATIONS.get(base(seed))
        if not variants or rng.random() >= 1 / MUTATION_ODDS:
            return None
        common = [v for v in variants if not v[3]]
        rare = [v for v in variants if v[3]]
        mid = (rng.choice(rare) if rare and rng.random() < .25 else rng.choice(common or rare))[0]
    g["almanac"][mid] = g["almanac"].get(mid, 0) + 1
    m["items"][f"seed_{mid}"] = m["items"].get(f"seed_{mid}", 0) + 1
    g["mutation"] = {"id": mid, "at": int(_now())}  # the page shows it once
    if MUTANT[mid]["rare"]:
        m["bonus"] += 1
    return MUTANT[mid]


def _deliver(g, m, seed, by=""):
    """A harvest counts toward the oldest open order for that crop; a filled one pays its tomatoes."""
    order = next((o for o in g["orders"] if o["seed"] == seed and o["got"] < o["n"]), None)
    if not order:
        return None
    order["got"] += 1
    if order["got"] >= order["n"]:
        g["orders"].remove(order)
        m["earned"] = int(m.get("earned") or 0) + order["reward"]
        g["filled"] += 1
        _log(g, f"📋 Order filled for {order['from']}: {order['n']} {CROPS[seed]['name'].lower()}"
                f"{'s' if order['n'] > 1 else ''}. 🍅 +{order['reward']} tomatoes toward your next spin.")
    return order


def _harvest(g, m, key, by="", rng=None):
    tile = g["tiles"].pop(key)
    crop = CROPS[tile["seed"]]
    got = crop["compost"] + (1 if _has(m, "gardener_frog") else 0)
    odd = _mutate(g, m, tile["seed"], rng)
    if odd and not odd["rare"]:
        got *= 3
    g["harvests"] += 1
    dues = _has(m, "gardener_death") and g["harvests"] % 3 == 0
    if dues:
        got += 3
    m["compost"] += got
    back = _has(m, "gardener_witch") and g["harvests"] % 2 == 0
    if back:  # (an ordinary seed: a variant's own seed only comes back when it comes out as itself)
        m["items"][base(tile["seed"])] = m["items"].get(base(tile["seed"]), 0) + 1
    _log(g, f"{by or 'You'} harvested a {crop['name'].lower()}: ♻ +{got} compost" + (" and Basil hummed the seed back" if back else "")
         + (" (Mr. Death collected his dues: +3)" if dues else "") + ".")
    if odd:
        _log(g, f"🧬 A mutation! {odd['emoji']} {odd['name']}: " + ("a free spin at the Sauce-o-Matic." if odd["rare"]
                                                                     else "triple compost.") + " Into the almanac, and its seed into the basket.")
    _deliver(g, m, base(tile["seed"]))
    return got


def _robot(g, m, now=None):
    """Hoe-Bot 3000 harvests whatever is ripe."""
    if not _has(m, "gardener_robot"):
        return 0
    ripe = [k for k, t in g["tiles"].items() if t.get("kind") == "plant" and progress(t, m, now) >= 1]
    return sum(_harvest(g, m, k, by="Hoe-Bot 3000") for k in ripe)


def _babbo(g, m, rng=None, today=None):
    """Babbo Natale's present: one a day while he's at work (the server's date)."""
    if not _has(m, "gardener_babbo"):
        return None
    day = (today or timezone.localdate()).isoformat()
    if g.get("gift_day") == day:
        return None
    import random
    rng = rng or random.SystemRandom()
    seed = rng.choices([k for k, _ in GIFTS], weights=[w for _, w in GIFTS])[0]
    g["gift_day"] = day
    m["items"][seed] = m["items"].get(seed, 0) + 1
    _log(g, f"Babbo Natale left a present in the shed: 🎁 {CROPS[seed]['name'].lower()} seeds. The wrapping is a disaster.")
    return seed


def _orders(g, m, rng=None, today=None):
    """The order board: expired orders come down; a new one goes up once a day while there's room."""
    import random
    rng = rng or random.SystemRandom()
    now = _now()
    for o in [o for o in g["orders"] if o["due"] <= now]:
        g["orders"].remove(o)
        _log(g, f"📋 {o['from'].capitalize()} gave up waiting for {o['n']} {CROPS[o['seed']]['name'].lower()}"
                f"{'s' if o['n'] > 1 else ''}.")
    day = (today or timezone.localdate()).isoformat()
    if g.get("order_day") == day or len(g["orders"]) >= ORDERS_OPEN:
        return None
    # Crops they can grow: everyday ones always, the rarer ones once they've had their seeds
    crops = ["seed_tomato", "seed_carrot", "seed_sunflower"] + [c for c in ("seed_pumpkin", "seed_monster") if c in m["items"]]
    seed = rng.choice(crops)
    n = rng.choice((1, 2, 2, 3)) if CROPS[seed]["hours"] <= 30 else 1
    reward = max(100, min(300, int(round(CROPS[seed]["hours"] * n * 3.4 / 10)) * 10))
    g["order_seq"] += 1
    order = {"id": g["order_seq"], "seed": seed, "n": n, "got": 0, "reward": reward, "from": rng.choice(NEIGHBOURS),
             "posted": int(now), "due": int(now + ORDER_DAYS * 86400)}
    g["orders"].append(order)
    g["order_day"] = day
    _log(g, f"📋 New order from {order['from']}: {n} {CROPS[seed]['name'].lower()}{'s' if n > 1 else ''} for 🍅 {reward}.")
    return order


def _locked(user, fn):
    from mainapp import tomatoes
    from mainapp.models import TomatoScore
    with transaction.atomic():
        tomatoes.score_of(user)
        score = TomatoScore.objects.select_for_update().get(user=user)
        m, g = M._state(score), _state(score)
        fn(g, m)
        _orders(g, m)
        _babbo(g, m)
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
    pid = body.get("id")
    if action == "crew":  # a gardener to work, or to the shed
        def shift(g, m):
            if pid not in GARDENERS or not m["items"].get(pid):
                raise ValueError("You don't have that gardener.")
            now = crew(m)
            if body.get("on"):
                if pid in now:
                    return
                if len(now) >= CREW:
                    raise ValueError(f"{CREW} gardeners at a time: send one to the shed first.")
                m["crew"] = now + [pid]
                _log(g, f"{M.BY_ID[pid]['name']} came out to work.")
            else:
                m["crew"] = [x for x in now if x != pid]
                _log(g, f"{M.BY_ID[pid]['name']} went to rest in the shed.")
        return _locked(user, shift)
    key = _key(body.get("x"), body.get("y"))

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
            item.update(seed=t["seed"], look=base(t["seed"]), variant=crop.get("variant", ""), name=crop["name"], progress=round(p, 4), stage=stage(p),
                        left=int(max(0, (1 - p) * crop["hours"] * 3600 / speed)), rate=speed / (crop["hours"] * 3600))
        else:
            item["id"] = t.get("id")
        tiles.append(item)
    basket = {pid: n for pid, n in m["items"].items() if pid in CROPS and n > 0}
    basket.update({pid: m["items"][pid] - placed(g, pid) for pid in DECOR if m["items"].get(pid, 0) - placed(g, pid) > 0})
    return {"cols": COLS, "rows": ROWS, "tiles": tiles, "basket": basket, "compost": m["compost"],
            "gardeners": [{"id": pid, "about": about} for pid, about in GARDENERS.items() if _has(m, pid)],
            "shed": [{"id": pid, "about": about} for pid, about in GARDENERS.items()
                     if m["items"].get(pid) and not _has(m, pid)], "crew_max": CREW,
            "hat": M.worn(score).get("hat", ""), "log": g["log"][:12], "harvests": g["harvests"],
            "water": WATER, "crops": CROPS, "now": int(now),
            "orders": [{**o, "name": CROPS[o["seed"]]["name"], "left": max(0, o["due"] - int(now))} for o in g["orders"]],
            "orders_max": ORDERS_OPEN, "filled": g["filled"], "mutation": g.get("mutation"), "mutation_odds": MUTATION_ODDS,
            "almanac": [{**v, "got": g["almanac"].get(mid, 0)} for mid, v in MUTANT.items()],
            "prizes": {**{p["id"]: {"name": p["name"], "emoji": p["emoji"]} for p in M.PRIZES
                          if p["kind"] in ("seed", "decor", "gardener")},
                       **{sid: {"name": f"{MUTANT[mid]['name']} seeds", "emoji": MUTANT[mid]["emoji"]} for sid, mid in VARIANT_SEEDS.items()}},
            "keep": {"common": KEEP[False], "rare": KEEP[True]}}
