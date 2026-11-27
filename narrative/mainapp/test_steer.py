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
        self.assertNotIn("paragraph", hint)  # never a different length: that's the preset's call
        four = ['*A.*\n\n"B."\n\n*C.*\n\n"D."'.replace("\\n", "\n")] * 3
        self.assertNotIn("one or two", polish.shape_hint(four))
        data = {"notices": [{"label": "same_shape", "kind": "pattern", "status": "new", "at": 10}]}
        with mock.patch.object(polish, "approved", return_value=[]), mock.patch.object(watch, "chat_data", return_value=data):
            self.assertIn("Build this reply differently", polish.avoid_line(self.user, object(), alike, 12))


class NegatedActionTests(TestCase):
    """"She doesn't step back. She tips her chin up instead.": what didn't happen, before what did."""
    def test_spotted_for_free(self):
        hit = polish.DETECTORS["negated_action"].search
        for text in ("She doesn't step back. She tips her chin up instead — the better to look him over.",
                     "Mira doesn't answer. Mira just looks at the door.",
                     "Вона не відступає. Вона піднімає підборіддя.", "Він не відповідає. Натомість дивиться у вікно."):
            self.assertTrue(hit(text), text)
        for text in ('"I don\'t know. I think so," she says.', "He doesn't know the way, so she leads.",
                     "She opens the door and steps out into the rain."):
            self.assertFalse(hit(text), text)

    def test_known_slop_steered_in_every_reply_and_write_for_me(self):
        user = get_user_model().objects.create_user(username="negated", password="pw12345!")
        self.assertIn("negated_action", watch.KNOWN_FIX)
        self.assertIn("negated_action", watch.LABELS)
        with mock.patch.object(polish, "approved", return_value=[]):
            self.assertIn("start each beat on the action itself", polish.avoid_line(user))


class WriteMineAndModelSteerTests(TestCase):
    def test_write_for_me_keeps_their_usual_length(self):
        from mainapp.views import write_mine_length
        self.assertIn("about 150 words", write_mine_length(["word " * 150, "word " * 140, "word " * 160]))
        self.assertIn("about 40 words", write_mine_length(["hi", "ok then"]))  # never a line
        self.assertIn("a paragraph or two", write_mine_length([]))

    def test_mimo_is_kept_with_their_character(self):
        user = get_user_model().objects.create_user(username="mimo", password="pw12345!")
        with mock.patch.object(polish, "approved", return_value=[]), \
             mock.patch("mainapp.ai_client.resolve", return_value=(None, "xiaomi/mimo-v2.6-pro")):
            self.assertIn("Keep the story where the person's character is", polish.avoid_line(user))
        with mock.patch.object(polish, "approved", return_value=[]), \
             mock.patch("mainapp.ai_client.resolve", return_value=(None, "anthropic/claude-opus-5-5")):
            self.assertNotIn("Keep the story where", polish.avoid_line(user))
        self.assertIn("apart_scene", watch.LABELS)
