"""🎪 The village fair (mainapp/tomato_fair.py): entries all week, judging on Sunday, prizes and ribbons."""
import datetime as dt
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from mainapp import tomato_fair as F
from mainapp.models import TomatoScore
from mainapp.tests import quiet_garden

WED, SUN, NEXT_TUE = dt.date(2026, 11, 25), dt.date(2026, 11, 29), dt.date(2026, 12, 1)


class FairTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="fairgoer", password="pw12345!")
        self.client.force_login(self.user)
        self.score = TomatoScore.objects.create(
            user=self.user, machine={"items": {"seed_giant_pumpkin": 1}},
            garden={"shelf": {"seed_pumpkin": 2, "seed_tomato": 3}, "pantry": {"tomato_soup": 1}, "log": [],
                    "bouquets": [{"stems": {"seed_sunflower": 3, "seed_carrot": 2}, "wrap": "kraft", "name": "Sunny", "charm": 4, "at": 0}]})
        quiet_garden(self)
        p = mock.patch("mainapp.tomato_fair.timezone.localdate", return_value=WED)
        p.start(); self.addCleanup(p.stop)

    def do(self, **body):
        return self.client.post(reverse("tomato_garden_state"), json.dumps(body), content_type="application/json")

    def g_m(self):
        self.score.refresh_from_db()
        return self.score.garden, self.score.machine

    def test_entering_gives_the_thing_up_once_a_week(self):
        state = self.do(action="fair_enter", contest="harvest", kind="mutation", item="giant_pumpkin").json()
        self.assertEqual({c["id"]: c["entry"] for c in state["fair"]["contests"]}["harvest"], "your giant pumpkin")
        self.assertEqual(self.do(action="fair_enter", contest="harvest", kind="crop", item="seed_pumpkin").status_code, 400)
        state = self.do(action="fair_enter", contest="dish", kind="dish", item="tomato_soup").json()
        self.assertEqual(state["kitchen"]["pantry"], [])
        state = self.do(action="fair_enter", contest="bouquet", kind="bouquet", item="0").json()
        self.assertEqual(state["crafts"]["vase"], [])
        self.assertEqual(len(state["fair"]["judges"]), 3)
        self.assertEqual(state["fair"]["days_left"], 4)

    def test_sunday_judges_and_pays(self):
        self.do(action="fair_enter", contest="harvest", kind="crop", item="seed_pumpkin")
        g, m = self.g_m()
        F.tick(g, m, today=WED)
        self.assertIsNone(g["fair"]["results"])  # not yet
        F.tick(g, m, today=SUN)
        r = g["fair"]["results"]["contests"]["harvest"]
        self.assertIn(r["place"], (1, 2, 3, 4))
        self.assertEqual(len(r["board"]), 4)
        self.assertEqual(m["earned"], F.PRIZE[r["place"]])
        self.assertEqual(len(g["fair"]["trophies"]), 1 if r["place"] <= 3 else 0)
        with self.assertRaises(ValueError):  # judged: closed until Monday
            F.enter(g, m, "dish", "dish", "tomato_soup", today=SUN)

    def test_judged_late_when_nobody_came_on_sunday(self):
        self.do(action="fair_enter", contest="harvest", kind="crop", item="seed_pumpkin")
        g, m = self.g_m()
        F.tick(g, m, today=NEXT_TUE)
        self.assertEqual(g["fair"]["results"]["week"], "2026-W48")
        self.assertEqual(g["fair"]["week"], "2026-W49")
        F.enter(g, m, "harvest", "crop", "seed_pumpkin", today=NEXT_TUE)  # a new week, open again

    def test_best_in_show(self):
        for c, k, i in (("harvest", "crop", "seed_pumpkin"), ("dish", "dish", "tomato_soup"), ("bouquet", "bouquet", "0")):
            self.do(action="fair_enter", contest=c, kind=k, item=i)
        g, m = self.g_m()
        with mock.patch.object(F, "_judge", return_value=(9, "likes")):
            F.tick(g, m, today=SUN)
        self.assertTrue(g["fair"]["results"]["best"])
        self.assertEqual(m["items"][g["fair"]["results"]["best"]], 1)
        self.assertEqual([t["place"] for t in g["fair"]["trophies"]], [1, 1, 1, 0])
        self.assertEqual(m["earned"], 3 * F.PRIZE[1])
