"""
🍲 The cottage kitchen (opens with the cottage's kitchen stage, mainapp/tomato_house.py): crops from the shelf go into
the pot, two to four of them, and after some real minutes a dish comes out.

- RECIPES: the five dishes the order board asks for, plus secret ones nobody tells you about: found by trying. Every
  dish cooked goes into the recipe book (a secret one shows as "???" with how many crops it takes until found).
- A pot that matches no recipe still cooks: "something brown", worth a little compost, and a line from the stove.
- A dish goes to the pantry. From there: a dish order takes it whole (🧺 Give fills it at once); a neighbour can be
  given it (mainapp/tomato_village.py); or it's eaten for a boost:
    grow     every plant in the ground grows that many hours at once (the dish's "growth")
    compost  +N compost on every harvest for some hours
    luck     mutations come 2× / 3× as often for some hours
    water    thrown tomatoes water more for some hours
Kept in TomatoScore.garden: "pot" {needs, recipe, ready}, "pantry" {dish: n}, "book" {dish: times cooked},
"boosts" {kind: {"until", "n"}}.
"""
from mainapp import tomato_garden as G

POT_MIN, POT_MAX = 2, 4
MINUTES_PER_CROP = 10
PANTRY_MAX = 12  # of each dish

RECIPES = {
    # --- the ones the order board asks for (names match tomato_garden.DISHES) ---
    "tomato_soup": {"name": "Tomato soup", "emoji": "🍲", "needs": {"seed_tomato": 3, "seed_carrot": 1},
                    "boost": ("grow", 2, "every plant grows 2 hours at once"),
                    "line": "The stove says “warm”. It means “hot”."},
    "sunflower_bread": {"name": "Sunflower bread", "emoji": "🍞", "needs": {"seed_sunflower": 2, "seed_tomato": 1},
                        "boost": ("compost", 1, "+1 compost on every harvest for 6 hours"),
                        "line": "The crust cracks when you press it. Correct."},
    "carrot_cake": {"name": "Carrot cake", "emoji": "🍰", "needs": {"seed_carrot": 3, "seed_sunflower": 1},
                    "boost": ("luck", 2, "mutations twice as likely for 6 hours"),
                    "line": "Ribbit has asked, formally, for a slice."},
    "pumpkin_risotto": {"name": "Pumpkin risotto", "emoji": "🍚", "needs": {"seed_pumpkin": 1, "seed_tomato": 2},
                        "boost": ("grow", 4, "every plant grows 4 hours at once"),
                        "line": "Stirred for exactly as long as it took. Not a second more."},
    "monstrous_salad": {"name": "Monstrous salad (it bites back)", "emoji": "🥗", "needs": {"seed_monster": 1, "seed_carrot": 2},
                        "boost": ("luck", 3, "mutations three times as likely for 4 hours"),
                        "line": "It is eating the croutons. Let it."},
    "ratatouille": {"name": "Ratatouille", "emoji": "🥘", "needs": {"seed_eggplant": 1, "seed_pepper": 1, "seed_tomato": 1},
                    "boost": ("grow", 4, "every plant grows 4 hours at once"),
                    "line": "Layered in a spiral, because you were raised right."},
    "strawberry_tart": {"name": "Strawberry tart", "emoji": "🍓", "needs": {"seed_strawberry": 3, "seed_sunflower": 1},
                        "boost": ("luck", 2, "mutations twice as likely for 6 hours"),
                        "line": "Mirela would call it “acceptable”. That's her highest praise."},
    # --- secret: found by trying ---
    "pesto": {"name": "Pesto", "emoji": "🌿", "needs": {"seed_basil": 2, "seed_garlic": 1}, "secret": True,
              "boost": ("compost", 1, "+1 compost on every harvest for 6 hours"),
              "line": "Signora Rosa can smell it from her balcony. She sings a little louder."},
    "borscht": {"name": "Borscht", "emoji": "🍲", "needs": {"seed_beet": 2, "seed_carrot": 1, "seed_garlic": 1}, "secret": True,
                "boost": ("grow", 5, "every plant grows 5 hours at once"),
                "line": "The colour of a good winter. Nonna Lyuba would nod once. That's enough."},
    "pea_soup": {"name": "Pea soup", "emoji": "🥣", "needs": {"seed_peas": 3}, "secret": True,
                 "boost": ("compost", 1, "+1 compost on every harvest for 6 hours"),
                 "line": "Thick enough to stand a spoon in. The spoon is fine with this."},
    "strawberry_jam": {"name": "Strawberry jam", "emoji": "🍯", "needs": {"seed_strawberry": 3}, "secret": True,
                       "boost": ("water", 2, "every tomato you throw waters twice as much for 6 hours"),
                       "line": "Six jars. Four by tomorrow. You know why."},
    "chili_sauce": {"name": "Chili sauce", "emoji": "🌶️", "needs": {"seed_chili": 2, "seed_tomato": 1}, "secret": True,
                    "boost": ("water", 3, "every tomato you throw waters three times as much for 4 hours"),
                    "line": "Bulba tasted it and has not spoken since. Respectfully."},
    "blueberry_pie": {"name": "Blueberry pie", "emoji": "🥧", "needs": {"seed_blueberry": 2, "seed_strawberry": 1}, "secret": True,
                      "boost": ("luck", 2, "mutations twice as likely for 6 hours"),
                      "line": "Your teeth are blue now. It was worth it."},
    "melon_salad": {"name": "Watermelon and basil", "emoji": "🍉", "needs": {"seed_watermelon": 1, "seed_basil": 1}, "secret": True,
                    "boost": ("grow", 3, "every plant grows 3 hours at once"),
                    "line": "Cold, sweet, green-smelling. Summer, in a bowl."},
    "stuffed_peppers": {"name": "Stuffed peppers", "emoji": "🫑", "needs": {"seed_pepper": 2, "seed_tomato": 1, "seed_garlic": 1}, "secret": True,
                        "boost": ("compost", 2, "+2 compost on every harvest for 6 hours"),
                        "line": "Each one a small, warm, generous house."},
    "mandrake_tonic": {"name": "Mandrake tonic", "emoji": "🧪", "needs": {"seed_mandrake": 1, "seed_garlic": 1}, "secret": True,
                       "boost": ("luck", 3, "mutations three times as likely for 4 hours"),
                       "line": "It screamed going in. It's quiet now. Drink it before it changes its mind."},
    "ketchup": {"name": "Homemade ketchup", "emoji": "🥫", "needs": {"seed_tomato": 4}, "secret": True,
                "boost": ("water", 2, "every tomato you throw waters twice as much for 6 hours"),
                "line": "Bulba looks at the jar for a long time. It says nothing. It is moved."},
    "roasted_seeds": {"name": "Roasted sunflower seeds", "emoji": "🌰", "needs": {"seed_sunflower": 2}, "secret": True,
                      "boost": ("compost", 1, "+1 compost on every harvest for 6 hours"),
                      "line": "Salted. The crow outside has noticed."},
    "carrot_crisps": {"name": "Carrot crisps", "emoji": "🥕", "needs": {"seed_carrot": 2}, "secret": True,
                      "boost": ("grow", 1, "every plant grows 1 hour at once"),
                      "line": "Crunchy. Suspiciously orange."},
    "tomato_salad": {"name": "Tomato salad", "emoji": "🍅", "needs": {"seed_tomato": 2, "seed_sunflower": 1}, "secret": True,
                     "boost": ("grow", 2, "every plant grows 2 hours at once"),
                     "line": "Olive oil, salt, a sunflower petal for no reason."},
    "pumpkin_pie": {"name": "Pumpkin pie", "emoji": "🥧", "needs": {"seed_pumpkin": 1, "seed_carrot": 1, "seed_sunflower": 1},
                    "secret": True, "boost": ("luck", 2, "mutations twice as likely for 6 hours"),
                    "line": "The kitchen smells like an autumn that hasn't happened yet."},
    "monster_jam": {"name": "Monstrous jam", "emoji": "🫙", "needs": {"seed_monster": 1, "seed_pumpkin": 1}, "secret": True,
                    "boost": ("compost", 2, "+2 compost on every harvest for 6 hours"),
                    "line": "It glows a little in the jar. That's fine. That's probably fine."},
    "garden_stew": {"name": "Whole-garden stew", "emoji": "🫕", "needs": {"seed_tomato": 1, "seed_carrot": 1,
                    "seed_sunflower": 1, "seed_pumpkin": 1}, "secret": True,
                    "boost": ("grow", 6, "every plant grows 6 hours at once"),
                    "line": "Everyone in the garden stops working to smell it. Even Hoe-Bot."},
    "sunflower_tea": {"name": "Moon tea", "emoji": "🍵", "needs": {"seed_sunflower": 1, "seed_monster": 1}, "secret": True,
                      "boost": ("luck", 3, "mutations three times as likely for 4 hours"),
                      "line": "You drink it and, for a moment, the flowers seem to be looking at you."},
}
FAILED = {"name": "Something brown", "emoji": "🟤", "line": "The stove made a noise you'll be thinking about tonight."}
HOURS = {"compost": 6, "luck": 6, "water": 6}
for _r in RECIPES.values():
    if _r["boost"][0] != "grow" and "4 hours" in _r["boost"][2]:
        _r["hours"] = 4


def _match(needs):
    """The recipe these crops make, or None."""
    return next((rid for rid, r in RECIPES.items() if r["needs"] == needs), None)


def _tidy(g):
    g["pantry"] = {k: int(v) for k, v in (g.get("pantry") or {}).items() if k in RECIPES and int(v) > 0}
    g["book"] = {k: int(v) for k, v in (g.get("book") or {}).items() if k in RECIPES}
    g["boosts"] = {k: v for k, v in (g.get("boosts") or {}).items() if isinstance(v, dict) and v.get("until", 0) > G._now()}
    if g.get("pot") is not None and not isinstance(g.get("pot"), dict):
        g["pot"] = None


def is_open(g):
    from mainapp import tomato_house as H
    return H.has(g, "kitchen") or not H.ENABLED


def cook(g, m, needs):
    """The pot gets these crops from the shelf and starts cooking. Raises ValueError for the person."""
    _tidy(g)
    if not is_open(g):
        raise ValueError("The kitchen isn't built yet: it's the cottage's fourth stage.")
    if g.get("pot"):
        raise ValueError("Something is already cooking.")
    needs = {G.base(k): int(n) for k, n in (needs or {}).items() if k in G.CROPS and int(n) > 0}
    total = sum(needs.values())
    if not POT_MIN <= total <= POT_MAX:
        raise ValueError(f"The pot takes {POT_MIN} to {POT_MAX} crops.")
    short = {k: n for k, n in needs.items() if g["shelf"].get(k, 0) < n}
    if short:
        raise ValueError(f"Not enough on the shelf: {G.describe(short)}.")
    for k, n in needs.items():
        g["shelf"][k] -= n
    g["shelf"] = {k: v for k, v in g["shelf"].items() if v > 0}
    g["pot"] = {"needs": needs, "recipe": _match(needs), "ready": int(G._now() + total * MINUTES_PER_CROP * 60)}
    G._log(g, f"🍲 Into the pot: {G.describe(needs)}. Ready in {total * MINUTES_PER_CROP} minutes.")


def collect(g, m):
    """The dish out of the pot, into the pantry (or, a failure, into the compost). Returns its name."""
    _tidy(g)
    pot = g.get("pot")
    if not pot:
        raise ValueError("The pot is empty.")
    if pot["ready"] > G._now():
        raise ValueError("Not ready yet.")
    g["pot"] = None
    rid = pot.get("recipe")
    if not rid:
        back = sum(pot["needs"].values())
        m["compost"] += back
        G._log(g, f"{FAILED['emoji']} {FAILED['name']}. {FAILED['line']} (♻ +{back} compost: it went on the heap.)")
        return FAILED["name"]
    r = RECIPES[rid]
    new = rid not in g["book"]
    g["book"][rid] = g["book"].get(rid, 0) + 1
    if g["pantry"].get(rid, 0) < PANTRY_MAX:
        g["pantry"][rid] = g["pantry"].get(rid, 0) + 1
    G._log(g, f"{r['emoji']} {r['name']} is ready. {r['line']}"
              + (" 📖 A new recipe for the book!" if new and r.get("secret") else ""))
    return r["name"]


def eat(g, m, rid):
    """A dish from the pantry, eaten for its boost."""
    _tidy(g)
    if g["pantry"].get(rid, 0) < 1:
        raise ValueError("There's none of that in the pantry.")
    g["pantry"][rid] -= 1
    g["pantry"] = {k: v for k, v in g["pantry"].items() if v > 0}
    r = RECIPES[rid]
    kind, n, about = r["boost"]
    if kind == "grow":  # every plant in the ground grows n hours at once
        for t in g["tiles"].values():
            if t.get("kind") == "plant":
                t["boost"] = t.get("boost", 0) + n * 3600
    else:
        hours = r.get("hours", HOURS[kind])
        g["boosts"][kind] = {"n": n, "until": int(G._now() + hours * 3600)}
    G._log(g, f"{r['emoji']} You ate the {r['name'].lower()}: {about}.")


def boost(g, kind):
    """The active boost of this kind (its n), or 0."""
    b = (g.get("boosts") or {}).get(kind)
    return b["n"] if isinstance(b, dict) and b.get("until", 0) > G._now() else 0


def for_order(g, order):
    """The recipe id of a dish order (by its name), if it's in the pantry."""
    rid = next((k for k, r in RECIPES.items() if r["name"] == order.get("dish")), None)
    return rid if rid and (g.get("pantry") or {}).get(rid, 0) > 0 else None


def public(g):
    _tidy(g)
    now = int(G._now())
    pot = g.get("pot")
    return {
        "open": is_open(g), "min": POT_MIN, "max": POT_MAX, "minutes": MINUTES_PER_CROP,
        "pot": ({"needs": pot["needs"], "what": G.describe(pot["needs"]), "left": max(0, pot["ready"] - now)} if pot else None),
        "pantry": [{"id": k, "n": n, "name": RECIPES[k]["name"], "emoji": RECIPES[k]["emoji"], "boost": RECIPES[k]["boost"][2]}
                   for k, n in g["pantry"].items()],
        "book": [{"id": k, "known": k in g["book"] or not r.get("secret"), "cooked": g["book"].get(k, 0),
                  "name": r["name"] if (k in g["book"] or not r.get("secret")) else "???",
                  "emoji": r["emoji"] if (k in g["book"] or not r.get("secret")) else "❔",
                  "needs": G.describe(r["needs"]) if (k in g["book"] or not r.get("secret")) else f"{sum(r['needs'].values())} crops",
                  "boost": r["boost"][2] if (k in g["book"] or not r.get("secret")) else ""} for k, r in RECIPES.items()],
        "boosts": [{"kind": k, "n": v["n"], "left": max(0, v["until"] - now)} for k, v in g["boosts"].items()],
    }
