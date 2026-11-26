"""🌱 The newer crops: each one can be won, drawn, mutated, cooked and asked for."""
import re
from pathlib import Path

from django.test import SimpleTestCase

from mainapp import tomato_garden as G, tomato_kitchen as K, tomato_machine as M, tomato_village as V, tomato_crafts as C

JS = (Path(__file__).parent / "static/mainapp/js/tomato_garden.js").read_text(encoding="utf-8")
BASE = [c for c in G.CROPS if not G.CROPS[c].get("base")]


class CropTests(SimpleTestCase):
    def test_every_crop_is_a_prize_with_a_sprite_a_flower_and_three_mutations(self):
        prizes = {p["id"] for p in M.PRIZES}
        for c in BASE:
            with self.subTest(c):
                self.assertIn(c, prizes)
                self.assertIn(f"ripe_{c}:", JS)
                self.assertRegex(JS, rf"\b{c}: '[a-zA-Z]'")  # its flower colour
                self.assertEqual(len(G.MUTATIONS[c]), 3)

    def test_every_mutation_has_a_look_that_differs_while_growing(self):
        for mid in G.MUTANT:
            with self.subTest(mid):
                m = re.search(rf"\n\s+{mid}: \{{ leaf: \{{([^}}]*)\}}", JS)
                self.assertTrue(m, "no look in VARIANT")
                self.assertTrue(m.group(1).strip(), "its leaves look just like the ordinary plant's")

    def test_names_and_plurals(self):
        self.assertEqual(G.describe({"seed_basil": 1, "seed_strawberry": 2, "seed_chili": 3}),
                         "1 bunch of basil, 2 strawberries and 3 chillies")
        self.assertEqual(G.describe({"seed_peas": 2}), "2 pea pods")

    def test_recipes_are_cookable_and_distinct(self):
        seen = set()
        for rid, r in K.RECIPES.items():
            self.assertTrue(all(k in BASE for k in r["needs"]), rid)
            self.assertTrue(K.POT_MIN <= sum(r["needs"].values()) <= K.POT_MAX, rid)
            key = tuple(sorted(r["needs"].items()))
            self.assertNotIn(key, seen, rid)
            seen.add(key)
        for d in G.DISHES:  # every order-board dish is a known recipe
            self.assertTrue(any(r["name"] == d["name"] and not r.get("secret") for r in K.RECIPES.values()), d["name"])

    def test_neighbours_tastes_are_real_things(self):
        for who, n in V.NEIGHBOURS.items():
            for tag in n["likes"] + n["dislikes"]:
                self.assertTrue(tag in G.CROPS or tag in K.RECIPES or tag in ("bouquet", "mutation"), f"{who}: {tag}")

    def test_bouquet_stems_are_crops_and_drawn(self):
        for k in C.STEMS:
            self.assertIn(k, G.CROPS)
            self.assertIn(f"'{k}'", JS)

    def test_a_visitor_never_asks_for_a_crop_never_seen(self):
        import random
        g = {"shelf": {}, "log": [], "tiles": {}}
        with self.settings():
            for i in range(40):
                g.pop("village", None)
                V.tick(g, {"items": {}}, rng=random.Random(i))
                vis = g["village"]["visitor"]
                if vis["kind"] == "crop":
                    self.assertIn(vis["id"], G.EVERYDAY)


class DecorationTests(SimpleTestCase):
    def test_every_decoration_is_a_prize_drawn_twice(self):
        root = Path(__file__).resolve().parents[1]
        by_id = {p["id"]: p for p in M.PRIZES}
        for d in G.DECOR:
            with self.subTest(d):
                self.assertEqual(by_id[d]["kind"], "decor")
                self.assertRegex(JS, rf"\n\s+{d}: \[")  # the pixel sprite on the canvas
        for d in G.DECOR:
            img = by_id[d]["img"]
            self.assertTrue((root / img.lstrip("/")).is_file(), img)  # the picture in the machine
