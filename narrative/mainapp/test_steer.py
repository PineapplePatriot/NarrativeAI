"""🧭 Habits a "don't" doesn't cure get what to do instead, before each reply (mainapp/bulba/polish.py avoid_line)."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from mainapp.bulba import polish, watch


class SteerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="steer", password="pw12345!")

    def test_a_habit_they_fix_is_steered_not_named(self):
        with mock.patch.object(polish, "approved", return_value=["detail_fixation", "recounting"]):
            line = polish.avoid_line(self.user)
        self.assertIn("Keep the scene moving", line)
        self.assertIn("Stay in the present", line)
        self.assertNotIn("lingering on small physical details", line)  # naming it primes it
        self.assertIn("Keep out of it", line)  # the witty-writing family, as before

    def test_what_watch_caught_in_this_chat_is_steered_for_a_while(self):
        chat = object()
        data = {"notices": [{"label": "detail_fixation", "kind": "pattern", "status": "opened", "at": 40},
                            {"label": "recounting", "kind": "pattern", "status": "muted", "at": 40}]}
        with mock.patch.object(polish, "approved", return_value=[]), mock.patch.object(watch, "chat_data", return_value=data):
            self.assertIn("Keep the scene moving", polish.avoid_line(self.user, chat, [], 50))
            self.assertNotIn("Stay in the present", polish.avoid_line(self.user, chat, [], 50))  # they don't mind it
            self.assertNotIn("Keep the scene moving", polish.avoid_line(self.user, chat, [], 80))  # long ago

    def test_same_build_gets_a_different_build(self):
        alike = ['*He walks in.*\\n\\n"Hi."\\n\\n*He sits.* "Well?"'.replace("\\n", "\n")] * 3
        hint = polish.shape_hint(alike)
        self.assertIn("open with a line of dialogue", hint)
        self.assertIn("not a question", hint)
        data = {"notices": [{"label": "same_shape", "kind": "pattern", "status": "new", "at": 10}]}
        with mock.patch.object(polish, "approved", return_value=[]), mock.patch.object(watch, "chat_data", return_value=data):
            self.assertIn("Build this reply differently", polish.avoid_line(self.user, object(), alike, 12))
