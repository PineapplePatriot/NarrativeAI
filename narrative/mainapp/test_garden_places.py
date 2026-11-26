"""🗺️ The cottage quest's second chapter: new places (field, greenhouse, orchard), the mill's wheat, fruit trees."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from mainapp import tomato_garden as G, tomato_house as H
from mainapp.models import TomatoScore
from mainapp.tests import quiet_garden


class PlacesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="farmer2", password="pw12345!")
        self.client.force_login(self.user)
        self.score = TomatoScore.objects.create(
            user=self.user, machine={"items": {"seed_tomato": 3, "tree_apple": 1}},
            garden={"house": {"stage": 5, "begun": 1, "have": {}}, "log": []})
        quiet_garden(self)
        p = mock.patch.object(H, "ENABLED", True)
        p.start(); self.addCleanup(p.stop)

    def do(self, **body):
        return self.client.post(reverse("tomato_garden_state"), json.dumps(body), content_type="application/json")

    def set_stage(self, n):
        self.score.refresh_from_db()
        g = self.score.garden
        g["house"]["stage"] = n
        self.score.garden = g
        self.score.save()

    def test_places_open_with_the_quest(self):
        state = self.client.get(reverse("tomato_garden_state")).json()
        self.assertEqual([a["id"] for a in state["areas"]], ["home"])
        self.assertEqual(self.do(action="plant", area="field", x=0, y=0, id="seed_tomato").status_code, 400)
        self.set_stage(7)  # field and greenhouse built
        state = self.do(action="plant", area="field", x=7, y=4, id="seed_tomato").json()
        self.assertEqual([a["id"] for a in state["areas"]], ["home", "field", "greenhouse"])
        t = next(t for t in state["tiles"] if t["area"] == "field")
        self.assertEqual((t["x"], t["y"]), (7, 4))
        self.assertEqual(self.do(action="plant", area="greenhouse", x=6, y=0, id="seed_tomato").status_code, 400)  # 6 wide
        state = self.do(action="plant", area="greenhouse", x=0, y=0, id="seed_tomato").json()
        gh = next(t for t in state["tiles"] if t["area"] == "greenhouse")
        self.assertGreater(gh["rate"], next(t for t in state["tiles"] if t["area"] == "field")["rate"] * 1.4)

    def test_trees_only_in_the_orchard_and_they_fruit_again(self):
        self.set_stage(9)
        self.assertEqual(self.do(action="plant", area="home", x=0, y=0, id="tree_apple").status_code, 400)
        self.assertEqual(self.do(action="plant", area="orchard", x=0, y=0, id="seed_tomato").status_code, 400)
        self.do(action="plant", area="orchard", x=0, y=0, id="tree_apple")
        self.score.refresh_from_db()
        g = self.score.garden
        g["tiles"]["orchard:0,0"]["at"] -= 100 * 3600
        self.score.garden = g
        self.score.save()
        state = self.do(action="harvest", area="orchard", x=0, y=0).json()
        self.assertEqual(state["shelf"]["tree_apple"], 1)
        tree = next(t for t in state["tiles"] if t["area"] == "orchard")
        self.assertAlmostEqual(tree["progress"], 1 - 24 / 96, places=2)  # still there, fruiting again in a day

    def test_the_mill_and_the_saplings(self):
        g, m = {"house": {"stage": 7, "begun": 1, "have": {}}, "log": [], "tiles": {}}, {"items": {}, "compost": 0}
        H.tick(g, m)
        self.assertNotIn("seed_wheat", m["items"])
        g["house"]["stage"] = 8
        H.tick(g, m); H.tick(g, m)  # once a day
        self.assertEqual(m["items"]["seed_wheat"], H.MILL_WHEAT)
        g["house"].update(stage=8, building_until=1)  # the orchard finishes building
        H.tick(g, m)
        self.assertTrue(all(m["items"].get(t) == 1 for t in H.ORCHARD_TREES))
        self.assertIsNone(H.current(g))

    def test_chapter_two_follows_the_porch(self):
        self.assertEqual(H.STAGES[H.CHAPTER_TWO]["id"], "field")
        self.assertIn("I have plans", " ".join(t for _, t in H.SCENES["porch"]))
        self.assertTrue(all(a.get("unlock") in {s["unlock"] for s in H.STAGES} for a in G.AREAS.values() if a.get("unlock")))
