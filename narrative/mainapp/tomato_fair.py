"""
🎪 The village fair: every week, three contests; entries all week, judging on Sunday.

- CONTESTS: the biggest harvest (a crop from the shelf, or a mutation's seed: a giant one counts extra), the best dish
  (from the pantry), the prettiest bouquet (from the vase). One entry per contest per week; what's entered is given up.
- Three neighbours judge each week (mainapp/tomato_village.py). An entry's score is its quality, plus each judge's
  taste: something a judge likes +2, dislikes −1, and a little of their mood (0 to 2). Three made-up rivals from the
  village compete too, so a place is never guaranteed.
- Prizes (tomatoes toward a spin, and a ribbon for the trophy wall): 1st 300, 2nd 150, 3rd 60, 4th 20. First in all
  three in one week is Best in show: a rare seed besides.
- Judging happens on Sunday (or on the first visit after it), and the results stay up until the next ones.
Kept in TomatoScore.garden["fair"]: {"week", "entries" {contest: entry}, "results" {week, contests}, "trophies" [...],
"seen"}.
"""
import random

from django.utils import timezone

from mainapp import tomato_garden as G

ENABLED = True
PRIZE = {1: 300, 2: 150, 3: 60, 4: 20}
RIBBON = {1: "Blue ribbon", 2: "Red ribbon", 3: "Yellow ribbon", 4: "A pat on the back"}
JUDGES = 3
TROPHIES_MAX = 60
CONTESTS = {
    "harvest": {"name": "Biggest harvest", "emoji": "🎃", "ask": "a crop from the shelf, or a mutation's seed",
                "rivals": ["the Bellini twins' pumpkin", "a suspiciously large turnip from the next village",
                           "Father Ignazio's cabbage", "Mrs. Kovač's prize marrow", "a watermelon nobody admits to growing"]},
    "dish": {"name": "Best dish", "emoji": "🍲", "ask": "a dish from the pantry",
             "rivals": ["the pizzeria's lasagne", "Mrs. Kovač's apple strudel", "the Bellini twins' minestrone",
                        "a stew of uncertain origin", "Father Ignazio's honey cake"]},
    "bouquet": {"name": "Prettiest bouquet", "emoji": "💐", "ask": "a bouquet from the vase",
                "rivals": ["the florist's roses (professional, frankly unfair)", "a child's fistful of dandelions",
                           "Mrs. Kovač's peonies", "the Bellini twins' wild poppies", "a dried arrangement, very serious"]},
}
# how big a crop is, for the biggest harvest (0 to 10)
SIZE = {"seed_watermelon": 9, "seed_pumpkin": 9, "seed_mandrake": 6, "seed_eggplant": 5, "seed_sunflower": 6, "seed_pepper": 4,
        "seed_beet": 4, "seed_monster": 5, "seed_tomato": 3, "seed_carrot": 3, "seed_garlic": 3, "seed_strawberry": 2,
        "seed_chili": 2, "seed_blueberry": 2, "seed_peas": 2, "seed_basil": 2,
        "seed_wheat": 3, "tree_apple": 4, "tree_pear": 4, "tree_cherry": 2, "tree_plum": 3}


def _week(day=None):
    y, w, _ = (day or timezone.localdate()).isocalendar()
    return f"{y}-W{w:02d}"


def _fair(g):
    f = g.get("fair") if isinstance(g.get("fair"), dict) else {}
    f.setdefault("week", _week())
    f["entries"] = {k: v for k, v in (f.get("entries") or {}).items() if k in CONTESTS and isinstance(v, dict)}
    f["trophies"] = list(f.get("trophies") or [])[-TROPHIES_MAX:]
    f.setdefault("results", None)
    f["seen"] = f.get("seen") or ""
    g["fair"] = f
    return f


def judges(week):
    """This week's three judges (the same all week)."""
    from mainapp import tomato_village as V
    return random.Random(f"judges {week}").sample(sorted(V.NEIGHBOURS), JUDGES)


def _quality(contest, entry):
    """0 to 10: how good the entry itself is."""
    from mainapp import tomato_kitchen as K
    if contest == "harvest":
        if entry["kind"] == "mutation":
            mut = G.MUTANT[entry["item"]]
            return min(10, SIZE.get(mut["crop"], 3) * (1.6 if mut["id"].startswith("giant_") else 1.2) + (1 if mut["rare"] else 0))
        return SIZE.get(entry["item"], 3)
    if contest == "dish":
        r = K.RECIPES[entry["item"]]
        return min(10, 2 + sum(r["needs"].values()) * 1.5 + (2 if r.get("secret") else 0))
    b = entry.get("bouquet") or {}
    return min(10, b.get("charm", 1) * 1.6 + sum((b.get("stems") or {}).values()) * .4)


def _tag(contest, entry):
    """What a judge's likes are written in."""
    if contest == "bouquet":
        return "bouquet"
    if contest == "harvest" and entry["kind"] == "mutation":
        return "mutation"
    return entry["item"]


def _judge(week, contest, entry, who):
    """(points, verdict) from one judge."""
    from mainapp import tomato_village as V
    n = V.NEIGHBOURS[who]
    tag = _tag(contest, entry)
    mood = random.Random(f"{week} {contest} {who} {entry.get('item')}").uniform(0, 2)
    if tag in n["likes"]:
        return 2 + mood, "likes"
    if tag in n["dislikes"]:
        return -1 + mood * .5, "dislikes"
    return mood, ""


LINES = {"likes": "lingers over it, and writes something long.", "dislikes": "takes one look and moves on, briskly.",
         "": "nods, and writes something short."}


def judge(g, m, week, rng=None):
    """The week's entries, judged: places, prizes, ribbons, and the results kept for the page."""
    f = _fair(g)
    from mainapp import tomato_village as V
    panel = judges(week)
    out = {}
    firsts = 0
    for contest, entry in f["entries"].items():
        c = CONTESTS[contest]
        r = random.Random(f"rivals {week} {contest}")
        q = _quality(contest, entry)
        notes, pts = [], q
        for who in panel:
            p, verdict = _judge(week, contest, entry, who)
            pts += p
            notes.append(f"{V.NEIGHBOURS[who]['emoji']} {V.NEIGHBOURS[who]['name']} {LINES[verdict]}")
        rivals = [{"who": name, "score": round(r.uniform(5, 10.5) + sum(r.uniform(0, 2) for _ in panel), 1)}
                  for name in r.sample(c["rivals"], 3)]
        board = sorted(rivals + [{"who": "You", "what": entry["what"], "score": round(pts, 1), "you": True}],
                       key=lambda x: -x["score"])
        place = next(i for i, x in enumerate(board, 1) if x.get("you"))
        firsts += place == 1
        m["earned"] = int(m.get("earned") or 0) + PRIZE[place]
        if place <= 3:
            f["trophies"].append({"week": week, "contest": contest, "place": place, "what": entry["what"]})
        out[contest] = {"name": c["name"], "emoji": c["emoji"], "place": place, "board": board, "notes": notes,
                        "prize": PRIZE[place], "ribbon": RIBBON[place], "what": entry["what"]}
        G._log(g, f"🎪 The fair, {c['name'].lower()}: {RIBBON[place].lower()} for {entry['what']}. "
                  f"🍅 +{PRIZE[place]} tomatoes toward your next spin.")
    best = None
    if out and firsts == len(CONTESTS):  # first in all three: Best in show, and a rare seed
        from mainapp import tomato_machine as M
        seeds = [p["id"] for p in M.PRIZES if p["kind"] == "seed" and p["tier"] == "rare" and not p.get("banner")]
        best = (rng or random.SystemRandom()).choice(seeds)
        m["items"][best] = m["items"].get(best, 0) + 1
        f["trophies"].append({"week": week, "contest": "best", "place": 0, "what": "Best in show"})
        G._log(g, f"🏆 Best in show at the fair! The judges give you {M.BY_ID[best]['name'].lower()}.")
    f["results"] = {"week": week, "contests": out, "judges": panel, "best": best} if out else f["results"]
    f["entries"] = {}
    f["judged"] = week
    f["trophies"] = f["trophies"][-TROPHIES_MAX:]


def tick(g, m, today=None):
    """A new week opens the fair again; Sunday (or the first visit after it) judges the entries."""
    if not ENABLED:
        return
    f = _fair(g)
    day = today or timezone.localdate()
    week = _week(day)
    if f["week"] != week:
        if f["entries"]:  # judged late: nobody came by on Sunday
            judge(g, m, f["week"])
        f["week"] = week
        f["entries"] = {}
    elif day.weekday() == 6 and f["entries"] and f.get("judged") != week:
        judge(g, m, week)


def enter(g, m, contest, kind, item, today=None):
    """One entry into this week's contest (what's entered is given up). Raises ValueError for the person."""
    f = _fair(g)
    day = today or timezone.localdate()
    if contest not in CONTESTS:
        raise ValueError("No such contest.")
    if f.get("judged") == _week(day):
        raise ValueError("This week's fair has been judged: the next one opens on Monday.")
    if contest in f["entries"]:
        raise ValueError("You've already entered that one this week.")
    entry = {"kind": kind, "item": item}
    if contest == "harvest":
        if kind == "crop":
            if g["shelf"].get(item, 0) < 1:
                raise ValueError("None of those on the shelf.")
            g["shelf"][item] -= 1
            g["shelf"] = {k: v for k, v in g["shelf"].items() if v > 0}
            entry["what"] = f"your {G.CROPS[item]['name'].lower()}"
        elif kind == "mutation":
            if item not in G.MUTANT or m["items"].get(f"seed_{item}", 0) < 1:
                raise ValueError("You have no seed of that mutation.")
            m["items"][f"seed_{item}"] -= 1
            entry["what"] = f"your {G.MUTANT[item]['name'][0].lower() + G.MUTANT[item]['name'][1:]}"
        else:
            raise ValueError("The biggest harvest takes a crop or a mutation.")
    elif contest == "dish":
        from mainapp import tomato_kitchen as K
        if (g.get("pantry") or {}).get(item, 0) < 1:
            raise ValueError("None of that in the pantry.")
        g["pantry"][item] -= 1
        g["pantry"] = {k: v for k, v in g["pantry"].items() if v > 0}
        entry.update(kind="dish", what=f"your {K.RECIPES[item]['name'].lower()}")
    else:
        from mainapp import tomato_crafts as C
        vase = C._vase(g)
        i = int(item) if str(item).isdigit() else 0
        if not 0 <= i < len(vase):
            raise ValueError("No such bouquet in the vase.")
        b = vase.pop(i)
        entry.update(kind="bouquet", bouquet=b, what=f"“{b['name']}”")
    f["entries"][contest] = entry
    G._log(g, f"🎪 Entered in the fair ({CONTESTS[contest]['name'].lower()}): {entry['what']}. Judging on Sunday.")


def read(g):
    f = _fair(g)
    f["seen"] = (f.get("results") or {}).get("week", "")


def public(g, today=None):
    from mainapp import tomato_village as V
    f = _fair(g)
    day = today or timezone.localdate()
    week = _week(day)
    res = f.get("results")
    return {
        "open": ENABLED and f.get("judged") != week, "days_left": (6 - day.weekday()),
        "judges": [{"id": w, "name": V.NEIGHBOURS[w]["name"], "emoji": V.NEIGHBOURS[w]["emoji"]} for w in judges(week)],
        "contests": [{"id": k, "name": c["name"], "emoji": c["emoji"], "ask": c["ask"],
                      "entry": (f["entries"].get(k) or {}).get("what")} for k, c in CONTESTS.items()],
        "results": res, "unread": bool(res and res.get("week") != f["seen"]),
        "trophies": f["trophies"],
    }
