"""
🏘️ The neighbours: five people (and a crow) who live around the garden. Each day one of them drops by with a small
request; anyone can be given one thing a day (a crop from the shelf, a dish from the pantry, a bouquet). What they
like is learned by giving. Friendship is hearts from 0 to HEARTS_MAX; at 3, 6 and 10 hearts a letter comes, with a
present.

Kept in TomatoScore.garden["village"]: hearts {who: n}, learned {who: [likes/dislikes found]}, gifted {who: day},
visitor {who, wants {kind, id, n}, day, done}, letters [{who, at, title, text}], seen (letter count read).
"""
import random

from django.utils import timezone

from mainapp import tomato_garden as G

ENABLED = True  # (tests about other things switch the daily visitor off)
HEARTS_MAX = 10
LETTER_AT = (3, 6, 10)

NEIGHBOURS = {
    "rosa": {
        "name": "Signora Rosa", "emoji": "🎭", "about": "Retired opera singer next door. Waters her geraniums in a silk dressing gown.",
        "likes": ["bouquet", "seed_sunflower", "tomato_soup", "carrot_cake"], "dislikes": ["seed_monster", "monstrous_salad"],
        "hello": ["“Your tomatoes are singing, cara. Slightly flat, but singing.”", "“I sang Tosca in Milan. The garden reminds me. I don't know why.”",
                  "“A little something for an old woman's table?”"],
        "thanks": "“Bellissimo. I shall put it by the window, where the light is kind.”",
        "meh": "“Ah. How… practical. Thank you, cara.”",
        "no": "“Take it away, it is looking at me.”",
        "letters": [("A note on lilac paper", "Cara, the soup was the first thing I have eaten standing at the window since my husband died. "
                     "He sang to the tomatoes, did you know? Badly. I enclose seeds from his garden. — R.", {"seed_sunflower": 3}),
                    ("Programme from 1983", "I found this in a drawer: my name, second from the top. I was very good, you know, and very "
                     "difficult. Both things help. — Rosa", {"tomatoes": 150}),
                    ("An invitation", "On Sunday I shall sing on my balcony. One aria, no encore. You will come and stand in your "
                     "garden and pretend you are not listening. Bring nothing. Bring pumpkin seeds. — R.", {"seed_pumpkin": 2, "tomatoes": 200})],
    },
    "pepper": {
        "name": "Old Man Pepper", "emoji": "🐝", "about": "Keeps bees and opinions. Has not smiled since the last good harvest, in 1997.",
        "likes": ["seed_pumpkin", "sunflower_bread", "pumpkin_pie", "seed_sunflower"], "dislikes": ["ketchup", "bouquet"],
        "hello": ["“Hmph. Bees like your sunflowers. Don't let it go to your head.”", "“You're watering wrong. Everybody's watering wrong.”",
                  "“I'm not here to chat. I'm here because the bees made me.”"],
        "thanks": "“…That'll do. That'll do fine.” (He almost smiles.)",
        "meh": "“Hmph. I've had worse.”",
        "no": "“Flowers? Cut flowers? They were alive this morning.”",
        "letters": [("A jar with a label", "HONEY. FROM YOUR SUNFLOWERS. DON'T MAKE IT A THING. — P.", {"tomatoes": 100}),
                    ("Instructions, underlined", "Pumpkins: water at the root, not the leaf. Talk to them if you must. I don't. "
                     "(I do.) Seeds enclosed. — Pepper", {"seed_pumpkin": 2}),
                    ("A photograph", "Me and my wife, 1997, with a pumpkin bigger than both of us. Yours could get there. Don't tell "
                     "anyone I said so. — P.", {"seed_pumpkin": 1, "tomatoes": 250})],
    },
    "mirela": {
        "name": "Mirela the baker", "emoji": "🥖", "about": "Runs the bakery on the corner. Up at four, flour to the elbows, always humming.",
        "likes": ["seed_carrot", "seed_sunflower", "carrot_cake", "roasted_seeds"], "dislikes": ["ketchup", "monster_jam"],
        "hello": ["“I need carrots for a cake that is, honestly, mostly carrots.”", "“Smell that? Rye. I've been up since four. I'm fine.”",
                  "“Trade you a loaf for whatever's ripe?”"],
        "thanks": "“Oh, these are perfect. You'll get the first slice, I promise.”",
        "meh": "“Thanks! I'll think of something to do with it.”",
        "no": "“In my bakery? Absolutely not. With love.”",
        "letters": [("A recipe card, floury", "Your carrots made the best cake I've sold this year. Recipe on the back; don't tell my "
                     "mother. — M.", {"seed_carrot": 4}),
                    ("A paper bag", "Day-old bread for your compost, and something for you. I put your name on the board by the "
                     "till: 'Carrots by our neighbour'. People ask. — Mirela", {"tomatoes": 150}),
                    ("A small key", "It's for the bakery's back door. Come early on Saturdays; the first batch is the best one and it "
                     "should be yours. — M.", {"seed_sunflower": 3, "tomatoes": 200})],
    },
    "corvin": {
        "name": "Sir Corvin", "emoji": "🐦‍⬛", "about": "A crow of excellent manners. Collects shiny things and compliments, in that order.",
        "likes": ["mutation", "roasted_seeds", "seed_sunflower", "bouquet"], "dislikes": ["seed_carrot", "carrot_crisps"],
        "hello": ["“Good day. I have come about the shiny things. Have you any?”", "“I bow. (He bows.) I am here on business.”",
                  "“A crow remembers a kindness. And a slight. Mostly the kindness.”"],
        "thanks": "“Exquisite. I shall add it to the collection, between the bottle cap and the spoon.”",
        "meh": "“How generous. It is not shiny, but it is generous.”",
        "no": "“I regret I must decline. I have standards. They are high and arbitrary.”",
        "letters": [("A feather, folded into a note", "In gratitude, a feather. One of mine. Do not lose it. — Sir C.", {"tomatoes": 100}),
                    ("A bottle cap", "The finest in my collection. I give it to you because you will understand. — Corvin",
                     {"seed_monster": 1}),
                    ("A map, scratched in charcoal", "Where the shiny things are buried. I trust you. I have told no other "
                     "mammal. — Sir Corvin, crow", {"tomatoes": 300})],
    },
    "lyuba": {
        "name": "Nonna Lyuba", "emoji": "👵", "about": "Lives across the road. Has an opinion about your soup and a jar of something for everyone.",
        "likes": ["tomato_soup", "seed_tomato", "seed_pumpkin", "garden_stew"], "dislikes": ["roasted_seeds"],
        "hello": ["“You're thin. Did you eat? Eat.”", "“My mother grew tomatoes like this. Bigger. But like this.”",
                  "“I brought you a jar. Don't ask what's in it. Give me tomatoes.”"],
        "thanks": "“Good. Good! Now this is food.”",
        "meh": "“Mm. I'll make something out of it. I always do.”",
        "no": "“Sunflower seeds you buy at the station, not in a kitchen.”",
        "letters": [("A note tucked in a jar", "Pickles. Open in winter, not before. And listen: four tomatoes alone, cooked slow, "
                     "make a sauce your Bulba will cry over. — L.", {"hint": "ketchup", "tomatoes": 100}),
                    ("A folded tea towel", "My mother's. For your kitchen. And a secret: a pumpkin, a carrot, a sunflower, all in one "
                     "pot, and it tastes like October. — Lyuba", {"hint": "pumpkin_pie", "seed_tomato": 4}),
                    ("A recipe, written in two languages", "Everything the garden gives, one of each, into the big pot. That's "
                     "the whole secret. It always was. Come for dinner. — Nonna L.", {"hint": "garden_stew", "tomatoes": 250})],
    },
}


def _today():
    return timezone.localdate().isoformat()


def _village(g):
    v = g.get("village") if isinstance(g.get("village"), dict) else {}
    v["hearts"] = {k: max(0, min(HEARTS_MAX, int(n))) for k, n in (v.get("hearts") or {}).items() if k in NEIGHBOURS}
    v["learned"] = {k: list(x) for k, x in (v.get("learned") or {}).items() if k in NEIGHBOURS}
    v["gifted"] = {k: d for k, d in (v.get("gifted") or {}).items() if k in NEIGHBOURS}
    v["letters"] = list(v.get("letters") or [])
    v["seen"] = int(v.get("seen") or 0)
    g["village"] = v
    return v


def _label(kind, item):
    from mainapp import tomato_kitchen as K
    if kind == "dish":
        return K.RECIPES[item]["name"].lower()
    if kind == "bouquet":
        return "a bouquet"
    if kind == "mutation":
        return G.MUTANT[item]["name"].lower()
    return G.CROPS[item]["name"].lower()


def _tag(kind, item):
    """What the neighbour's likes are written in: a crop or dish id, "bouquet", or "mutation"."""
    return {"bouquet": "bouquet", "mutation": "mutation"}.get(kind, item)


def _heart(g, m, who, n):
    """Friendship changes; a letter (and its present) at 3, 6 and 10 hearts."""
    v = _village(g)
    before = v["hearts"].get(who, 0)
    after = max(0, min(HEARTS_MAX, before + n))
    v["hearts"][who] = after
    for i, at in enumerate(LETTER_AT):
        if before < at <= after:
            title, text, gift = NEIGHBOURS[who]["letters"][i]
            v["letters"].append({"who": who, "at": int(G._now()), "title": title, "text": text})
            got = []
            for k, val in gift.items():
                if k == "tomatoes":
                    m["earned"] = int(m.get("earned") or 0) + val
                    got.append(f"🍅 {val} tomatoes toward a spin")
                elif k == "hint":  # a secret recipe told in the letter: it goes into the book as known
                    g.setdefault("book", {}).setdefault(val, 0)
                    got.append("a secret recipe")
                else:
                    m["items"][k] = m["items"].get(k, 0) + val
                    got.append(f"{val} {G.CROPS[k]['name'].lower()} seeds")
            G._log(g, f"💌 A letter from {NEIGHBOURS[who]['name']}: “{title}”. With it: {', '.join(got)}.")


def _take(g, m, kind, item):
    """One thing out of the shelf, the pantry, the vase or the almanac's seeds, for a gift. Raises ValueError."""
    if kind == "crop":
        if g["shelf"].get(item, 0) < 1:
            raise ValueError("None of those on the shelf.")
        g["shelf"][item] -= 1
        g["shelf"] = {k: v for k, v in g["shelf"].items() if v > 0}
    elif kind == "dish":
        if (g.get("pantry") or {}).get(item, 0) < 1:
            raise ValueError("None of that in the pantry.")
        g["pantry"][item] -= 1
        g["pantry"] = {k: v for k, v in g["pantry"].items() if v > 0}
    elif kind == "bouquet":  # the oldest in the vase (mainapp/tomato_crafts.py)
        from mainapp import tomato_crafts as C
        return C.take(g)
    elif kind == "mutation":  # a mutation's seed, from the basket (the crow likes those)
        if m["items"].get(f"seed_{item}", 0) < 1:
            raise ValueError("You have no seed of that mutation.")
        m["items"][f"seed_{item}"] -= 1
    else:
        raise ValueError("You can give a crop, a dish, a bouquet or a mutation's seed.")


def gift(g, m, who, kind, item):
    """One present a day to a neighbour: liked +2 hearts, neither +1, disliked −1 (and they say so)."""
    v = _village(g)
    if who not in NEIGHBOURS:
        raise ValueError("No such neighbour.")
    if v["gifted"].get(who) == _today():
        raise ValueError(f"You've already given {NEIGHBOURS[who]['name']} something today.")
    took = _take(g, m, kind, item)
    n = NEIGHBOURS[who]
    tag = _tag(kind, item)
    verdict = "likes" if tag in n["likes"] else "dislikes" if tag in n["dislikes"] else ""
    if verdict and tag not in v["learned"].setdefault(who, []):
        v["learned"][who].append(tag)
    v["gifted"][who] = _today()
    line = n["thanks"] if verdict == "likes" else n["no"] if verdict == "dislikes" else n["meh"]
    from mainapp import tomato_crafts as C
    charming = kind == "bouquet" and verdict == "likes" and (took or {}).get("charm", 0) >= C.CHARMING
    what = f"“{took['name']}” ({'★' * took['charm']})" if kind == "bouquet" and took else _label(kind, item)
    G._log(g, f"{n['emoji']} You gave {n['name']} {what}. {line}" + (" They put it in water straight away." if charming else ""))
    _heart(g, m, who, {"likes": 2 + (1 if charming else 0), "dislikes": -1}.get(verdict, 1))


def _requests(who):
    """What a visiting neighbour might ask for: [(kind, id, n)]."""
    n = NEIGHBOURS[who]
    out = []
    for tag in n["likes"]:
        if tag in G.CROPS:
            out.append(("crop", tag, 2 if G.CROPS[tag]["hours"] <= 30 else 1))
        elif tag == "bouquet":
            out.append(("bouquet", "bouquet", 1))
        elif tag != "mutation":
            out.append(("dish", tag, 1))
    return out


def tick(g, m, rng=None):
    """Once a day a neighbour drops by (the least known first, now and then someone else) with a request."""
    v = _village(g)
    today = _today()
    if not ENABLED or (v.get("visitor") or {}).get("day") == today:
        return
    rng = rng or random.SystemRandom()
    who = sorted(NEIGHBOURS, key=lambda k: (v["hearts"].get(k, 0), rng.random()))[0] if rng.random() < .6 else rng.choice(list(NEIGHBOURS))
    from mainapp import tomato_kitchen as K
    asks = [a for a in _requests(who) if a[0] != "dish" or K.is_open(g)]
    kind, item, n = rng.choice(asks)
    v["visitor"] = {"who": who, "kind": kind, "id": item, "n": n, "day": today, "done": False,
                    "hello": rng.choice(NEIGHBOURS[who]["hello"])}
    G._log(g, f"{NEIGHBOURS[who]['emoji']} {NEIGHBOURS[who]['name']} dropped by. {v['visitor']['hello']}")


def help_visitor(g, m):
    """The visitor's request, given: +2 hearts (and what it was is now known to be liked), and a few tomatoes."""
    v = _village(g)
    vis = v.get("visitor") or {}
    if not vis or vis.get("done") or vis.get("day") != _today():
        raise ValueError("Nobody is waiting right now.")
    kind = "bouquet" if vis["kind"] == "bouquet" else vis["kind"]
    for _ in range(vis["n"]):
        _take(g, m, kind, vis["id"])
    vis["done"] = True
    who = vis["who"]
    if vis["id"] not in v["learned"].setdefault(who, []):
        v["learned"][who].append(_tag(kind, vis["id"]))
    m["earned"] = int(m.get("earned") or 0) + 50
    G._log(g, f"{NEIGHBOURS[who]['emoji']} {NEIGHBOURS[who]['name']}: {NEIGHBOURS[who]['thanks']} 🍅 +50 tomatoes toward your next spin.")
    _heart(g, m, who, 2)


def read_letters(g):
    v = _village(g)
    v["seen"] = len(v["letters"])


def public(g):
    from mainapp import tomato_kitchen as K
    v = _village(g)
    vis = v.get("visitor") or {}
    here = vis if vis.get("day") == _today() else None
    name_of = lambda tag: ("a bouquet" if tag == "bouquet" else "mutations' seeds" if tag == "mutation"
                           else K.RECIPES[tag]["name"] if tag in K.RECIPES else G.CROPS[tag]["name"])
    return {
        "people": [{"id": k, "name": n["name"], "emoji": n["emoji"], "about": n["about"], "hearts": v["hearts"].get(k, 0),
                    "max": HEARTS_MAX, "gifted_today": v["gifted"].get(k) == _today(),
                    "likes": [name_of(t) for t in v["learned"].get(k, []) if t in n["likes"]],
                    "dislikes": [name_of(t) for t in v["learned"].get(k, []) if t in n["dislikes"]],
                    "next_letter": next((a for a in LETTER_AT if a > v["hearts"].get(k, 0)), None)} for k, n in NEIGHBOURS.items()],
        "visitor": ({"who": here["who"], "name": NEIGHBOURS[here["who"]]["name"], "emoji": NEIGHBOURS[here["who"]]["emoji"],
                     "hello": here.get("hello", ""), "done": here.get("done", False),
                     "wants": f"{here['n']} × {_label(here['kind'], here['id'])}" if here["n"] > 1 else _label(here["kind"], here["id"]),
                     "kind": here["kind"], "id": here["id"], "n": here["n"]} if here else None),
        "letters": [{**x, "name": NEIGHBOURS[x["who"]]["name"], "emoji": NEIGHBOURS[x["who"]]["emoji"]} for x in v["letters"]][::-1],
        "unread": max(0, len(v["letters"]) - v["seen"]),
    }
