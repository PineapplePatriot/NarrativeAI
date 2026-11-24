"""🍲 The garden's kitchen (mainapp/tomato_kitchen.py): cook from the shelf, discover recipes, eat for boosts."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from mainapp.models import TomatoScore
from mainapp.tests import quiet_garden


class KitchenTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cook", password="pw12345!")
        self.client.force_login(self.user)
        self.score = TomatoScore.objects.create(user=self.user, machine={"items": {"seed_tomato": 1}},
                                                garden={"shelf": {"seed_tomato": 6, "seed_carrot": 3, "seed_sunflower": 2}})
        quiet_garden(self)  # (the cottage quest is off in tests: the kitchen is open)

    def do(self, **body):
        return self.client.post(reverse("tomato_garden_state"), json.dumps(body), content_type="application/json")

    def later(self, minutes):
        self.score.refresh_from_db()
        g = self.score.garden
        if g.get("pot"):
            g["pot"]["ready"] -= minutes * 60
        self.score.garden = g
        self.score.save()

    def test_cook_a_known_dish_and_eat_it(self):
        self.assertEqual(self.do(action="cook", needs={"seed_tomato": 1}).status_code, 400)  # 2 to 4 crops
        state = self.do(action="cook", needs={"seed_tomato": 3, "seed_carrot": 1}).json()
        self.assertEqual(state["shelf"]["seed_tomato"], 3)
        self.assertEqual(state["kitchen"]["pot"]["left"], 40 * 60)
        self.assertEqual(self.do(action="collect").status_code, 400)  # not ready yet
        self.assertEqual(self.do(action="cook", needs={"seed_tomato": 2}).status_code, 400)  # already cooking
        self.later(41)
        state = self.do(action="collect").json()
        self.assertEqual([d["id"] for d in state["kitchen"]["pantry"]], ["tomato_soup"])
        self.do(action="plant", x=0, y=0, id="seed_tomato")
        state = self.do(action="eat", id="tomato_soup").json()
        plant = next(t for t in state["tiles"] if t["kind"] == "plant")
        self.assertGreater(plant["progress"], 0.08)  # two hours of growth at once
        self.assertEqual(state["kitchen"]["pantry"], [])

    def test_a_secret_recipe_is_found_and_a_failure_is_compost(self):
        book = lambda s: {r["id"]: r for r in s["kitchen"]["book"]}
        state = self.client.get(reverse("tomato_garden_state")).json()
        self.assertEqual(book(state)["ketchup"]["name"], "???")
        self.do(action="cook", needs={"seed_tomato": 4})
        self.later(60)
        state = self.do(action="collect").json()
        self.assertEqual(book(state)["ketchup"]["name"], "Homemade ketchup")
        state = self.do(action="eat", id="ketchup").json()
        self.assertEqual(state["kitchen"]["boosts"][0]["kind"], "water")
        before = state["compost"]
        self.do(action="cook", needs={"seed_carrot": 1, "seed_tomato": 1, "seed_sunflower": 1})  # no such recipe
        self.later(60)
        state = self.do(action="collect").json()
        self.assertEqual(state["compost"], before + 3)
        self.assertIn("Something brown", state["log"][0]["text"])

    def test_luck_and_compost_boosts_reach_the_harvest(self):
        from mainapp import tomato_garden as G, tomato_kitchen as K
        g = {"boosts": {"compost": {"n": 2, "until": G._now() + 60}, "luck": {"n": 3, "until": G._now() + 60}}}
        self.assertEqual((K.boost(g, "compost"), K.boost(g, "luck")), (2, 3))
        self.assertEqual(K.boost({"boosts": {"luck": {"n": 3, "until": G._now() - 1}}}, "luck"), 0)

    def test_a_dish_order_takes_the_cooked_dish(self):
        self.score.refresh_from_db()
        g = self.score.garden
        g["pantry"] = {"tomato_soup": 1}
        g["orders"] = [{"id": 7, "needs": {"seed_tomato": 3, "seed_carrot": 1}, "have": {"seed_tomato": 0, "seed_carrot": 0},
                        "reward": 300, "from": "Signora Rosa", "posted": 0, "due": 10 ** 12, "dish": "Tomato soup", "emoji": "🍲"}]
        self.score.garden = g
        self.score.save()
        state = self.do(action="give", to=7).json()
        self.assertEqual(state["orders"], [])
        self.assertEqual(state["kitchen"]["pantry"], [])
        self.assertEqual(state["shelf"]["seed_tomato"], 6)  # the shelf untouched


class NeighbourTests(KitchenTests):
    """🏘️ The neighbours (mainapp/tomato_village.py): a daily visitor, gifts, friendship, letters."""
    test_cook_a_known_dish_and_eat_it = test_a_secret_recipe_is_found_and_a_failure_is_compost = None
    test_luck_and_compost_boosts_reach_the_harvest = test_a_dish_order_takes_the_cooked_dish = None

    def setUp(self):
        super().setUp()
        from mainapp import tomato_village as V
        on = mock.patch.object(V, "ENABLED", True)
        on.start()
        self.addCleanup(on.stop)

    def test_gifts_teach_what_they_like_and_hearts_bring_letters(self):
        state = self.do(action="gift", to="rosa", kind="crop", item="seed_sunflower").json()
        rosa = next(p for p in state["village"]["people"] if p["id"] == "rosa")
        self.assertEqual((rosa["hearts"], rosa["likes"], rosa["gifted_today"]), (2, ["Sunflower"], True))
        self.assertEqual(self.do(action="gift", to="rosa", kind="crop", item="seed_tomato").status_code, 400)  # one a day
        state = self.do(action="gift", to="pepper", kind="crop", item="seed_carrot").json()  # neither liked nor not
        self.assertEqual(next(p for p in state["village"]["people"] if p["id"] == "pepper")["hearts"], 1)
        self.assertEqual(self.do(action="gift", to="nobody", kind="crop", item="seed_carrot").status_code, 400)
        # friendship to 3 hearts: a letter, with seeds
        self.score.refresh_from_db()
        g = self.score.garden
        g["village"]["gifted"] = {}
        self.score.garden = g
        self.score.save()
        state = self.do(action="gift", to="rosa", kind="crop", item="seed_sunflower").json()
        self.assertEqual(state["village"]["unread"], 1)
        self.assertEqual(state["village"]["letters"][0]["title"], "A note on lilac paper")
        self.assertEqual(state["basket"]["seed_sunflower"], 3)
        self.assertEqual(self.do(action="read_letters").json()["village"]["unread"], 0)

    def test_the_daily_visitor_and_helping(self):
        from mainapp import tomato_village as V
        state = self.client.get(reverse("tomato_garden_state")).json()
        vis = state["village"]["visitor"]
        self.assertIsNotNone(vis)
        self.assertEqual(self.client.get(reverse("tomato_garden_state")).json()["village"]["visitor"]["who"], vis["who"])  # one a day
        self.score.refresh_from_db()  # make it a request they can meet
        g = self.score.garden
        g["village"]["visitor"].update({"who": "mirela", "kind": "crop", "id": "seed_carrot", "n": 2})
        self.score.garden = g
        self.score.save()
        state = self.do(action="help_visitor").json()
        self.assertTrue(state["village"]["visitor"]["done"])
        self.assertEqual(next(p for p in state["village"]["people"] if p["id"] == "mirela")["hearts"], 2)
        self.assertEqual(state["shelf"]["seed_carrot"], 1)
        self.assertEqual(self.do(action="help_visitor").status_code, 400)  # already helped
        self.assertIn("lyuba", V.NEIGHBOURS)

    def test_a_letter_can_tell_a_secret_recipe(self):
        from mainapp import tomato_village as V
        g = {"shelf": {}, "log": [], "village": {"hearts": {"lyuba": 2}}}
        m = {"items": {}, "earned": 0}
        V._heart(g, m, "lyuba", 1)
        self.assertIn("ketchup", g["book"])  # in the book as known
        self.assertEqual(m["earned"], 100)
