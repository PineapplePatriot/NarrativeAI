"""🪴 Decorations help the 8 patches around them (mainapp/tomato_garden.py: DECOR_EFFECT, aura)."""
import random
from unittest import mock

from django.test import SimpleTestCase

from mainapp import tomato_garden as G, tomato_machine as M


def garden(tiles):
    return {"tiles": tiles, "shelf": {}, "log": [], "almanac": {}, "harvests": 0}


class DecorTests(SimpleTestCase):
    def test_every_decoration_does_something(self):
        self.assertEqual(set(G.DECOR), set(G.DECOR_EFFECT))

    def test_only_the_eight_around_and_no_double_counting(self):
        g = garden({"1,1": {"kind": "decor", "id": "beehive"}, "3,1": {"kind": "decor", "id": "beehive"},
                    "2,2": {"kind": "decor", "id": "pond"}, "0,1": {"kind": "decor", "id": "gnome"},
                    "1,2": {"kind": "decor", "id": "fairy_arch"}})
        self.assertAlmostEqual(G.aura(g, "2,1")["grow"], .25)  # one beehive counted (two next to it) + the pond
        self.assertEqual(G.aura(g, "5,5")["by"], [])
        self.assertEqual(G.aura(g, "0,2")["mutation"], 3.0)  # gnome 1.5 × arch 2, capped at 3
        self.assertEqual(G.aura(g, "1,1")["by"], ["fairy_arch", "gnome", "pond"])  # not itself

    def test_growth_is_added_as_it_goes_never_backdated(self):
        now = 1_000_000
        g = garden({"0,0": {"kind": "plant", "seed": "seed_tomato", "at": now - 10_000, "boost": 0}})
        m = {"items": {}}
        with mock.patch.object(G, "_now", return_value=now):
            G._aura_tick(g, m)
        g["tiles"]["1,0"] = {"kind": "decor", "id": "beehive"}  # placed now: nothing backdated
        with mock.patch.object(G, "_now", return_value=now):
            G._aura_tick(g, m)
        self.assertEqual(g["tiles"]["0,0"]["boost"], 0)
        with mock.patch.object(G, "_now", return_value=now + 1000):
            G._aura_tick(g, m)
        self.assertAlmostEqual(g["tiles"]["0,0"]["boost"], 150)  # 15% of the 1000 seconds since

    def test_harvest_compost_and_a_second_crop(self):
        g = garden({"0,0": {"kind": "plant", "seed": "seed_tomato", "at": 0, "boost": 0},
                    "1,0": {"kind": "decor", "id": "wheelbarrow"}, "0,1": {"kind": "decor", "id": "scarecrow"}})
        m = {"items": {}, "compost": 0, "crew": [], "bonus": 0}
        rng = mock.Mock(random=mock.Mock(return_value=.2), choice=random.choice)  # no mutation (.2 ≥ 1/20), a second crop (.2 < .25)
        with mock.patch.object(M, "_state", return_value=m):
            got = G._harvest(g, m, "0,0", rng=rng)
        self.assertEqual(got, G.CROPS["seed_tomato"]["compost"] + 1)
        self.assertEqual(g["shelf"]["seed_tomato"], 2)
