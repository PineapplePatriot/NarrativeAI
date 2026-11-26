"""
🏡 The cottage by the garden: a quest in five stages, built by Il Dattore (a scientist who over-engineers
everything) with Pantaleone's money (a banker who reads every receipt). A nod to two old commedia dell'arte
characters, the pompous Doctor and the miserly merchant.

How a stage goes
- It starts with Il Dattore buying the seeds it needs (with Pantaleone's money): they go into the basket.
- Its builder's order is pinned to the order board: crops are handed over from the shelf (🧺 Give).  
  The porch asks for something else: different mutations found (the almanac).
- When the order is complete they pay the compost (the "build" action) and Il Dattore builds for some hours.
- Done: the stage's unlock works from then on, the two have a word, and the next stage starts.
- Under budget (the crops in within BUDGET_DAYS of the stage starting): Pantaleone tips BONUS tomatoes toward spins.

Unlocks: mailbox (a 4th order slot), plot (a 6th row), barrel (thrown tomatoes water 25% more), kitchen (dish orders,
paid double), porch (the cottage dresses for the season; the gardeners sit out in the evening).
The second chapter (from CHAPTER_TWO) opens new places (mainapp/tomato_garden.py AREAS): field (a second plot),
greenhouse (everything grows 50% faster), mill (MILL_WHEAT wheat seeds a day, for bread, pizza, pasta), orchard (four
saplings; a grown tree fruits again and again).
Kept in TomatoScore.garden["house"]: stage (stages done), have {seed: n}, started, building_until, scene {key, at},
bonus (stages finished under budget).
"""
from mainapp import tomato_garden as G

ENABLED = True  # (tests about other things switch the quest off)
BUILDER, BANKER = "Il Dattore", "Pantaleone"
BUDGET_DAYS = 3
BONUS = 100
STAGES = (
    {"id": "foundation", "name": "Foundation", "emoji": "🧱", "needs": {"seed_tomato": 5}, "compost": 15, "hours": 6,
     "unlock": "mailbox", "about": "📮 A mailbox: the order board holds 4 orders."},
    {"id": "walls", "name": "Walls", "emoji": "🪵", "needs": {"seed_carrot": 6, "seed_sunflower": 4}, "compost": 30,
     "hours": 12, "unlock": "plot", "about": "🌱 A bigger plot: one more row of patches."},
    {"id": "roof", "name": "Roof", "emoji": "🏠", "needs": {"seed_sunflower": 6, "seed_tomato": 6}, "compost": 45,
     "hours": 24, "unlock": "barrel", "about": "🛢️ A rain barrel: every tomato you throw waters 25% more."},
    {"id": "kitchen", "name": "Chimney and kitchen", "emoji": "🍲", "needs": {"seed_tomato": 8, "seed_carrot": 6},
     "compost": 60, "hours": 24, "unlock": "kitchen", "about": "🍲 The kitchen: dish orders (several crops at once) pay double."},
    {"id": "porch", "name": "Porch", "emoji": "🪑", "needs": {}, "mutations": 3, "compost": 80, "hours": 36,
     "unlock": "porch", "about": "🪑 The porch: the cottage dresses up for the seasons, and the gardeners sit out in the evening."},
    # --- the second chapter: the garden grows (new places: mainapp/tomato_garden.py AREAS) ---
    {"id": "field", "name": "The far field", "emoji": "🌾", "needs": {"seed_peas": 6, "seed_beet": 6, "seed_carrot": 6},
     "compost": 100, "hours": 24, "unlock": "field", "about": "🌾 The far field: a second plot of 40 patches, through the gate."},
    {"id": "greenhouse", "name": "The greenhouse", "emoji": "🪟", "needs": {"seed_strawberry": 6, "seed_basil": 6, "seed_pepper": 3},
     "compost": 140, "hours": 36, "unlock": "greenhouse", "about": "🪟 The greenhouse: 18 patches under glass, where everything grows 50% faster."},
    {"id": "mill", "name": "The mill", "emoji": "⚙️", "needs": {"seed_sunflower": 10, "seed_pumpkin": 2, "seed_garlic": 4},
     "compost": 180, "hours": 48, "unlock": "mill", "about": "⚙️ The mill: wheat seeds every day, and bread, pizza and pancakes to discover in the kitchen."},
    {"id": "orchard", "name": "The orchard", "emoji": "🌳", "needs": {"seed_wheat": 8, "seed_blueberry": 4}, "mutations": 12,
     "compost": 240, "hours": 72, "unlock": "orchard", "about": "🌳 The orchard: four fruit trees that, once grown, give fruit again and again."},
)
CHAPTER_TWO = 5  # the stage the second chapter starts at
MILL_WHEAT = 2  # wheat seeds a day from the mill
ORCHARD_TREES = ("tree_apple", "tree_pear", "tree_cherry", "tree_plum")
D, P = BUILDER, BANKER
SCENES = {
    "intro": [(P, "Ah. So this is the “garden”. Charming. Small. Muddy."),
              (D, "Mud is a feature. Soil is merely a very slow laboratory."),
              (P, "Il Dattore is going to build you a cottage. I am paying for it. I will be reading the receipts."),
              (D, "I have taken the liberty of buying the seeds for the foundation. With his money."),
              (P, "…With my money.")],
    "foundation": [(D, "The foundation is laid. I reinforced it. Slightly."),
                   (P, "How slightly?"),
                   (D, "It would survive a small meteor."),
                   (P, "I did not budget for meteors. I did, however, budget for a mailbox. You may have it.")],
    "walls": [(D, "Walls! I added a window that only opens on Tuesdays."),
              (P, "Why."),
              (D, "Science does not answer to “why”. Science answers to funding."),
              (P, "Then science answers to me. The garden gets one more row. Nothing that opens on Tuesdays.")],
    "roof": [(P, "A roof. Red. Reasonable. Who approved the lightning rod?"),
             (D, "Nobody. That is what made it exciting."),
             (P, "Remove it."),
             (D, "It is load-bearing now. Also it fills the rain barrel. You're welcome.")],
    "kitchen": [(D, "The kitchen works. The stove has three settings: warm, hot, and “please step back”."),
                (P, "Can it make soup?"),
                (D, "It can make anything into soup."),
                (P, "Keep it away from the ledger. And tell the neighbours: dishes cost double.")],
    "porch": [(P, "Finished. I am almost moved. Almost."),
              (D, "I built you a rocking chair. It rocks by itself."),
              (P, "Of course it does."),
              (D, "Same time next year? I have plans for a mill."),
              (P, "I have plans for an audit.")],
    "bonus": [(P, "Under budget. Remarkable. Here: a hundred tomatoes. Don't tell him.")],
    "chapter2": [(D, "It's next year. Well. It's next week. Close enough. I have plans."),
                 (P, "You always have plans. I have a ledger."),
                 (D, "A field! A greenhouse! A mill! An orchard! The garden must grow."),
                 (P, "The garden may grow by one field. Then we talk."),
                 (D, "I bought the seeds already."),
                 (P, "…With my money.")],
    "field": [(D, "I moved the fence. Forty new patches, and a gate that only squeaks on purpose."),
              (P, "Why would a gate squeak on purpose?"),
              (D, "So you know someone's coming. Security."),
              (P, "It's a vegetable field.")],
    "greenhouse": [(P, "Glass. So much glass. Do you know what glass costs?"),
                   (D, "Everything grows half again as fast in there. I calculated it."),
                   (P, "And the windows?"),
                   (D, "Self-cleaning. Mostly by rain. Occasionally by Ribbit.")],
    "mill": [(D, "The mill turns! It grinds! It occasionally sings, which I didn't plan."),
             (P, "Does it make money?"),
             (D, "It makes wheat. Two seeds a day, every day. And flour, for pizza."),
             (P, "Pizza. Finally, something I understand.")],
    "orchard": [(P, "Four trees. I counted. Four."),
                (D, "Apple, pear, cherry, plum. Once they're grown they fruit again, and again, and again."),
                (P, "Forever?"),
                (D, "Longer than your audit, certainly."),
                (P, "…I'll allow it.")],
}


# the porch's scene runs on into the second chapter ("Same time next year? I have plans for a mill.")
SCENES["porch"] = SCENES["porch"] + SCENES.pop("chapter2")


def _house(g):
    """The quest's state, tidied in place (so every helper works on the same dict)."""
    if not isinstance(g.get("house"), dict):
        g["house"] = {}
    h = g["house"]
    h["stage"] = max(0, min(len(STAGES), int(h.get("stage") or 0)))
    h["have"] = {k: int(v) for k, v in (h.get("have") or {}).items()}
    for k in ("started", "building_until", "bonus"):
        h[k] = int(h.get(k) or 0)
    return h


def has(g, unlock):
    """Whether a stage with this unlock is built."""
    done = _house(g)["stage"]
    return any(s["unlock"] == unlock for s in STAGES[:done])


def current(g):
    h = _house(g)
    return STAGES[h["stage"]] if h["stage"] < len(STAGES) else None


def _scene(g, key):
    _house(g)["scene"] = {"key": key, "at": int(G._now())}


def _start(g, m):
    """A new stage: Il Dattore buys its seeds (Pantaleone pays) and pins its order to the board."""
    h, stage = _house(g), current(g)
    h["have"], h["started"], h["building_until"] = {k: 0 for k in stage["needs"]}, int(G._now()), 0
    for seed, n in stage["needs"].items():
        m["items"][seed] = m["items"].get(seed, 0) + n
    if stage["needs"]:
        G._log(g, f"🏡 {BUILDER} bought seeds for the {stage['name'].lower()} with {BANKER}'s money: "
                  f"{G.describe(stage['needs'])}. They're in the basket.")


def tick(g, m):
    """The quest moves on by itself: it begins on the first visit, and a stage being built finishes in time."""
    if not ENABLED:
        return
    h = _house(g)
    if "begun" not in h:
        h["begun"] = int(G._now())
        _scene(g, "intro")
        _start(g, m)
        return
    if h["building_until"] and G._now() >= h["building_until"]:
        stage = current(g)
        h["stage"] += 1
        h["building_until"] = 0
        _scene(g, stage["id"])
        G._log(g, f"🏡 The {stage['name'].lower()} is finished! {stage['about']}")
        if stage["id"] == "orchard":  # four saplings for the orchard
            for t in ORCHARD_TREES:
                m["items"][t] = m["items"].get(t, 0) + 1
            G._log(g, f"🌳 {BUILDER} left four saplings in the basket: apple, pear, cherry and plum. They go in the orchard.")
        if current(g):
            _start(g, m)
    if has(g, "mill") and h.get("mill_day") != G.timezone.localdate().isoformat():  # ⚙️ the mill's wheat, daily
        h["mill_day"] = G.timezone.localdate().isoformat()
        m["items"]["seed_wheat"] = m["items"].get("seed_wheat", 0) + MILL_WHEAT
        G._log(g, f"⚙️ The mill left {MILL_WHEAT} wheat seeds in the basket. It sang a little while doing it.")


def deliver(g, seed):
    """A harvest for the builder's order (before any other order). True if it went there."""
    h, stage = _house(g), current(g)
    if not ENABLED or not stage or "begun" not in h or h["building_until"] or h["have"].get(seed, 0) >= stage["needs"].get(seed, 0):
        return False
    h["have"][seed] = h["have"].get(seed, 0) + 1
    if all(h["have"].get(k, 0) >= n for k, n in stage["needs"].items()):
        G._log(g, f"🏡 Everything for the {stage['name'].lower()} is in. Pay the compost and {BUILDER} gets to work.")
    return True


def _found(g):
    return sum(1 for n in g.get("almanac", {}).values() if n)


def ready(g, m):
    """(ready to build, what's missing)."""
    h, stage = _house(g), current(g)
    if not stage:
        return False, "The cottage is finished."
    if h["building_until"]:
        return False, f"{BUILDER} is building."
    missing = {k: n - h["have"].get(k, 0) for k, n in stage["needs"].items() if h["have"].get(k, 0) < n}
    if missing:
        return False, f"Still to give from the shelf: {G.describe(missing)}."
    if _found(g) < stage.get("mutations", 0):
        return False, f"{BUILDER} needs {stage['mutations']} different mutations for it ({_found(g)} found so far)."
    if m["compost"] < stage["compost"]:
        return False, f"It costs ♻ {stage['compost']} compost; you have {m['compost']}."
    return True, ""


def build(g, m):
    ok, why = ready(g, m)
    if not ok:
        raise ValueError(why)
    h, stage = _house(g), current(g)
    m["compost"] -= stage["compost"]
    now = int(G._now())
    h["building_until"] = now + stage["hours"] * 3600
    if now - h["started"] <= BUDGET_DAYS * 86400:
        m["earned"] = int(m.get("earned") or 0) + BONUS
        h["bonus"] += 1
        _scene(g, "bonus")
        G._log(g, f"💰 {BANKER}: “Under budget. Remarkable.” 🍅 +{BONUS} tomatoes toward your next spin.")
    G._log(g, f"🏡 {BUILDER} started on the {stage['name'].lower()}. ♻ −{stage['compost']} compost. "
              f"Ready in about {stage['hours']} hours.")


def public(g, m):
    h, stage = _house(g), current(g)
    now = int(G._now())
    ok, why = ready(g, m)
    scene = h.get("scene") or {}
    out = {"stage": h["stage"], "stages": [{k: s[k] for k in ("id", "name", "emoji", "about")} for s in STAGES],
           "building": max(0, h["building_until"] - now) if h["building_until"] else 0, "ready": ok, "why": why,
           "builder": BUILDER, "banker": BANKER, "bonus": h["bonus"],
           "scene": {"key": scene.get("key"), "at": scene.get("at", 0),
                     "lines": [{"who": who, "text": text} for who, text in SCENES.get(scene.get("key"), [])]}}
    if stage:
        out["current"] = {**{k: stage[k] for k in ("id", "name", "emoji", "about", "compost", "hours")},
                          "needs": [{"seed": k, "name": G.CROPS[k]["name"], "n": n, "have": min(n, h["have"].get(k, 0))}
                                    for k, n in stage["needs"].items()],
                          "mutations": stage.get("mutations", 0), "found": _found(g),
                          "budget_left": max(0, h["started"] + BUDGET_DAYS * 86400 - now) if not h["building_until"] else 0}
    return out
