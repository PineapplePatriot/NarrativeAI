"""
💐 Things made in the garden, not grown: bouquets arranged from what's on the shelf.

- A bouquet is STEMS_MIN to STEMS_MAX stems from the shelf (at least one flower: a sunflower or a monstrous flower;
  carrot tops count as greenery, a tomato sprig as an odd accent; a pumpkin is not a stem), a wrapping and a name the
  person writes. It goes into the vase (VASE_MAX at most) until it's given to a neighbour (mainapp/tomato_village.py).
- Charm (1 to 5 ★) comes from variety: more kinds of stem, a full bunch, a monstrous flower, a wrapping that suits.
  A neighbour who likes bouquets takes a charming one (4★ or more) as one more heart.
The garden postcard is made on the page itself (mainapp/static/mainapp/js/tomato_garden.js): nothing kept here.
Kept in TomatoScore.garden: "bouquets" [{"stems": {seed: n}, "wrap", "name", "charm", "at"}], oldest first.
"""
from mainapp import tomato_garden as G

STEMS_MIN, STEMS_MAX = 3, 6
VASE_MAX = 6
NAME_MAX = 40
STEMS = {  # what can go in, and as what
    "seed_sunflower": "flower",
    "seed_monster": "flower",
    "seed_carrot": "greens",
    "seed_tomato": "accent",
}
WRAPS = {
    "kraft": "brown paper and string",
    "newspaper": "yesterday's newspaper",
    "lace": "a lace doily",
    "ribbon": "just a red ribbon",
}
SUITS = {"kraft": "seed_sunflower", "lace": "seed_monster", "newspaper": "seed_carrot", "ribbon": "seed_tomato"}
CHARMING = 4


def charm(stems, wrap):
    """1 to 5 stars, from variety."""
    total = sum(stems.values())
    c = len(stems)  # 1 to 4 kinds
    c += 1 if total >= 5 else 0
    c += 1 if "seed_monster" in stems else 0
    c += 1 if SUITS.get(wrap) in stems else 0
    return max(1, min(5, c))


def _vase(g):
    out = []
    for b in g.get("bouquets") or []:
        if isinstance(b, dict) and isinstance(b.get("stems"), dict):
            out.append(b)
        elif b:  # an older plain entry
            out.append({"stems": {"seed_sunflower": 3}, "wrap": "kraft", "name": "A bouquet", "charm": 2, "at": 0})
    g["bouquets"] = out[:VASE_MAX]
    return g["bouquets"]


def arrange(g, m, stems, wrap, name):
    """A bouquet from the shelf into the vase. Raises ValueError for the person."""
    vase = _vase(g)
    if len(vase) >= VASE_MAX:
        raise ValueError(f"The vase holds {VASE_MAX} bouquets: give one to a neighbour first.")
    picked = {}
    for k, n in (stems or {}).items():
        n = int(n) if str(n).lstrip("-").isdigit() else 0
        if n <= 0:
            continue
        if k == "seed_pumpkin":
            raise ValueError("A pumpkin is not a stem. You tried, and that's what matters.")
        if k not in STEMS:
            raise ValueError("That doesn't go in a bouquet.")
        picked[k] = n
    total = sum(picked.values())
    if not STEMS_MIN <= total <= STEMS_MAX:
        raise ValueError(f"A bouquet takes {STEMS_MIN} to {STEMS_MAX} stems.")
    if not any(STEMS[k] == "flower" for k in picked):
        raise ValueError("A bouquet needs at least one flower: a sunflower or a monstrous flower.")
    short = {k: n for k, n in picked.items() if g["shelf"].get(k, 0) < n}
    if short:
        raise ValueError(f"Not enough on the shelf: {G.describe(short)}.")
    wrap = wrap if wrap in WRAPS else "kraft"
    name = " ".join(str(name or "").split())[:NAME_MAX] or "A bouquet"
    for k, n in picked.items():
        g["shelf"][k] -= n
    g["shelf"] = {k: v for k, v in g["shelf"].items() if v > 0}
    c = charm(picked, wrap)
    vase.append({"stems": picked, "wrap": wrap, "name": name, "charm": c, "at": int(G._now())})
    G._log(g, f"💐 You arranged “{name}”: {G.describe(picked)}, in {WRAPS[wrap]}. {'★' * c}")
    return c


def take(g):
    """The oldest bouquet out of the vase (for a gift). Raises ValueError."""
    vase = _vase(g)
    if not vase:
        raise ValueError("No bouquet ready: arrange one first.")
    return vase.pop(0)


def public(g):
    return {"vase": _vase(g), "max": VASE_MAX, "min_stems": STEMS_MIN, "max_stems": STEMS_MAX, "name_max": NAME_MAX,
            "stems": STEMS, "wraps": WRAPS, "charming": CHARMING}
