import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from mainapp import messenger, picture_checks, vn_casting, vn_scenes
from mainapp.models import Character, EpisodeLook


def verdict(*problems):
    return {"ok": not problems, "issues": list(problems)}


@override_settings(PICTURE_CHECKS=True)
class DrawCheckedTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.user = get_user_model().objects.create_user(username="checks")

    def test_a_right_picture_is_drawn_once(self):
        with patch.object(messenger, "make_picture", return_value=(b"one", 0.04)) as image, \
             patch.object(picture_checks, "check", return_value=verdict()):
            data, cost, review = picture_checks.draw_checked(self.user, "p", [], kind="place", what="a room")
        self.assertEqual((data, cost, review["redrawn"]), (b"one", 0.04, False))
        image.assert_called_once()

    def test_a_wrong_picture_is_drawn_once_more_and_the_better_one_kept(self):
        with patch.object(messenger, "make_picture", side_effect=[(b"three-arms", 0.04), (b"fine", 0.04)]) as image, \
             patch.object(picture_checks, "check", side_effect=[verdict("Mira has three arms."), verdict()]):
            data, cost, review = picture_checks.draw_checked(self.user, "p", [(b"ref", "image/png")], kind="scene")
        self.assertEqual(data, b"fine")
        self.assertEqual(cost, 0.08)
        self.assertTrue(review["ok"] and review["redrawn"])
        self.assertEqual(image.call_count, 2)  # never a third time

    def test_when_the_second_try_is_worse_the_first_stays(self):
        with patch.object(messenger, "make_picture", side_effect=[(b"first", 0), (b"second", 0)]), \
             patch.object(picture_checks, "check", side_effect=[verdict("Six fingers."),
                                                                 verdict("Three arms.", "Wrong face.")]):
            data, _, review = picture_checks.draw_checked(self.user, "p", [])
        self.assertEqual(data, b"first")
        self.assertEqual(review["issues"], ["Six fingers."])

    def test_a_check_that_couldnt_look_never_costs_a_redraw(self):
        with patch.object(messenger, "make_picture", return_value=(b"one", 0)) as image, \
             patch.object(picture_checks, "check", return_value={"ok": None, "issues": ["Bulba couldn't look."]}):
            picture_checks.draw_checked(self.user, "p", [])
        image.assert_called_once()

    def test_the_check_sends_the_references_and_the_drawing_and_reads_problems(self):
        answer = json.dumps({"problems": ["Ivo has a third hand on Mira's shoulder."]})
        with patch("mainapp.bulba.vision.looker", return_value=("vision/model", "x")), \
             patch("mainapp.bulba.vision.prepare", return_value=("data:x", None)), \
             patch("mainapp.ai_client.complete", return_value=answer) as call:
            result = picture_checks.check(self.user, "scene", (b"drawn", "image/png"), [(b"a", "image/png"), (b"b", "image/png")],
                                          people="Mira, Ivo", what="They read the map.")
        content = call.call_args.args[2][0]["content"]
        self.assertEqual(sum(1 for c in content if c["type"] == "image_url"), 3)
        self.assertIn("Mira, Ivo", content[0]["text"])
        self.assertEqual(result, verdict("Ivo has a third hand on Mira's shoulder."))

    def test_places_are_checked_for_people_and_drawn_from_their_layout(self):
        place = {"name": "Map room", "layout": "shelves left, oak table middle, cabinet back", "details": ["brass cabinet"]}
        with patch.object(messenger, "make_picture", side_effect=[(b"with-a-man", 0), (b"empty", 0)]) as image, \
             patch.object(picture_checks, "check", side_effect=[verdict("A man stands by the table."), verdict()]) as looked:
            kept, _ = vn_casting.draw_place(self.user, place)
        self.assertIn("arranged exactly as the layout says", image.call_args.args[1])
        self.assertIn("shelves left, oak table middle", image.call_args.args[1])
        self.assertEqual(looked.call_args.args[1], "place")
        from django.core.files.storage import default_storage
        with default_storage.open(kept.image, "rb") as handle:
            self.assertEqual(handle.read(), b"empty")

    def test_phone_photos_are_checked_too(self):
        c = Character.objects.create(author=self.user, name="Mira", slug="checks-mira")
        with patch.object(messenger, "make_picture", side_effect=[(b"bad", 0), (b"good", 0)]), \
             patch.object(messenger, "load_character_references", return_value=[(b"ref", "image/png")]), \
             patch.object(picture_checks, "check", side_effect=[verdict("Two left hands."), verdict()]) as looked:
            messenger.generate_messenger_photo(self.user, c, "a selfie at the lab bench")
        self.assertEqual(looked.call_args.args[1], "photo")
        self.assertEqual(looked.call_count, 2)

    def test_the_illustration_describes_people_from_their_looks_and_is_checked(self):
        c = Character.objects.create(author=self.user, name="Mira", slug="checks-mira2",
                                     description="A brooding soul with eyes like storm clouds.")
        thread = messenger.create_thread(self.user, [c])
        EpisodeLook.objects.create(author=self.user, character=c, setting="canon", name="Day", outfit="black wool coat",
                                   identity={"hair": "silver bob", "eyes": "green"}, moods={"neutral": {"raw": "x.png", "cut": ""}})
        with patch.object(vn_scenes, "_call_vn_json", return_value={"title": "T", "handoff": "user_turn",
                                                                    "beats": [{"speaker_slug": c.slug, "text": "Hi."}]}):
            vn_scenes.start_scene(self.user, thread)
        with patch.object(vn_scenes, "_call_vn_json", return_value={"visual_prompt": "They share an umbrella.", "chat_summary": "Met."}), \
             patch.object(messenger, "make_picture", return_value=(b"cg", 0)) as image, \
             patch.object(picture_checks, "check", return_value=verdict()) as looked:
            vn_scenes.finish_scene_with_cg(self.user)
        prompt = image.call_args.args[1]
        self.assertIn("hair: silver bob", prompt)
        self.assertIn("wearing black wool coat", prompt)
        self.assertIn("exactly two arms", prompt)
        self.assertNotIn("storm clouds", prompt.split("Participant appearances:")[1].split("\n")[0])
        self.assertEqual(looked.call_args.args[1], "scene")


class ChecksOffInTestsTests(TestCase):
    def test_without_the_setting_a_picture_is_drawn_once_and_not_looked_at(self):
        user = get_user_model().objects.create_user(username="nochecks")
        with patch.object(messenger, "make_picture", return_value=(b"one", 0)) as image, \
             patch.object(picture_checks, "check") as looked:
            picture_checks.draw_checked(user, "p", [])
        image.assert_called_once()
        looked.assert_not_called()
