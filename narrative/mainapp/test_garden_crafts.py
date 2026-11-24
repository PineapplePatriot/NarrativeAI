"""💐 Bouquets (mainapp/tomato_crafts.py): arranged from the shelf, kept in the vase, given to neighbours."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from mainapp import tomato_crafts as C
from mainapp.models import TomatoScore
from mainapp.tests import quiet_garden


class BouquetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="florist", password="pw12345!")
        self.client.force_login(self.user)
        self.score = TomatoScore.objects.create(user=self.user, machine={"items": {}},
                                                garden={"shelf": {"seed_sunflower": 4, "seed_monster": 1, "seed_carrot": 3,
                                                                  "seed_pumpkin": 1, "seed_tomato": 2}, "log": []})
        quiet_garden(self)

    def do(self, **body):
        return self.client.post(reverse("tomato_garden_state"), json.dumps(body), content_type="application/json")

    def test_rules_of_a_bouquet(self):
        self.assertEqual(self.do(action="arrange", stems={"seed_sunflower": 2}).status_code, 400)  # too few
        self.assertEqual(self.do(action="arrange", stems={"seed_carrot": 3}).status_code, 400)  # no flower
        r = self.do(action="arrange", stems={"seed_sunflower": 2, "seed_pumpkin": 1})
        self.assertIn("pumpkin is not a stem", r.json()["error"] if r.status_code == 400 else "")
        self.assertEqual(self.do(action="arrange", stems={"seed_monster": 3}).status_code, 400)  # only one on the shelf
        state = self.do(action="arrange", stems={"seed_sunflower": 2, "seed_carrot": 2, "seed_monster": 1},
                        wrap="lace", name="  For   Rosa  ").json()
        b = state["crafts"]["vase"][0]
        self.assertEqual((b["name"], b["wrap"]), ("For Rosa", "lace"))
        self.assertEqual(b["charm"], 5)  # three kinds, a full bunch, a monstrous flower, lace suits it
        self.assertEqual(state["shelf"]["seed_sunflower"], 2)
        self.assertNotIn("seed_monster", state["shelf"])

    def test_charm(self):
        self.assertEqual(C.charm({"seed_sunflower": 3}, "ribbon"), 1)
        self.assertEqual(C.charm({"seed_sunflower": 3}, "kraft"), 2)

    def test_a_charming_bouquet_is_an_extra_heart(self):
        with mock.patch("mainapp.tomato_village.ENABLED", True):
            self.do(action="arrange", stems={"seed_sunflower": 2, "seed_carrot": 2, "seed_monster": 1}, wrap="lace", name="Big")
            state = self.do(action="gift", to="rosa", kind="bouquet", item="bouquet").json()  # Rosa likes bouquets
            rosa = next(p for p in state["village"]["people"] if p["id"] == "rosa")
            self.assertEqual(rosa["hearts"], 3)
            self.assertEqual(state["crafts"]["vase"], [])
            self.assertIn("“Big”", state["log"][0]["text"] + state["log"][1]["text"])
