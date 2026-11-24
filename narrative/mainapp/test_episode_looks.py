import io
import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from mainapp import episode_looks, messenger, vn_scenes
from mainapp.models import Character, EpisodeLook


def png(alpha=True):
    out = io.BytesIO()
    Image.new("RGBA" if alpha else "RGB", (4, 6)).save(out, format="PNG")
    return out.getvalue()


class LooksSetup(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.user = get_user_model().objects.create_user(username="looks", persona_name="Rowan")
        self.char = Character.objects.create(author=self.user, name="Mira", slug="looks-mira",
                                             description="Silver hair, green eyes.")
        self.thread = messenger.create_thread(self.user, [self.char])
        self.client.force_login(self.user)

    def make(self, moods=("happy",), outfit="black wool coat; grey scarf"):
        with patch.object(episode_looks, "references", return_value=[(b"ref", "image/png")]), \
             patch.object(messenger, "make_picture", side_effect=lambda *a, **k: (b"img-" + str(len(a[1])).encode(), 0.01)) as image:
            look, cost, errors = episode_looks.create(self.user, self.char, "canon", "Day", outfit, moods=list(moods))
        return look, image, errors

    def post(self, action, **extra):
        return self.client.post(reverse("vn_scenes_api"), data=json.dumps({"action": action, **extra}),
                                content_type="application/json")


class EpisodeLookTests(LooksSetup):
    def test_every_mood_is_an_edit_of_the_one_neutral_picture(self):
        look, image, errors = self.make(moods=("happy", "sad"))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(look.moods), ["happy", "neutral", "sad"])
        base_call, *mood_calls = image.call_args_list
        self.assertEqual(base_call.kwargs["references"], [(b"ref", "image/png")])
        self.assertIn("black wool coat; grey scarf", base_call.args[1])
        with default_storage.open(look.moods["neutral"]["raw"], "rb") as handle:
            base = handle.read()
        for call in mood_calls:
            self.assertEqual(call.kwargs["references"], [(base, "image/png")])
            self.assertIn("Edit this exact picture", call.args[1])

    def test_key_colour_avoids_the_characters_own_colours(self):
        self.assertNotEqual(episode_looks.pick_key("green eyes, emerald dress"), "green")
        self.assertNotEqual(episode_looks.pick_key("pink hair, violet ribbon"), "magenta")
        look, _, _ = self.make(outfit="lime jacket")
        self.assertNotEqual(look.key_colour, "green")

    def test_a_mood_it_doesnt_have_shows_the_closest_one(self):
        look, _, _ = self.make(moods=("happy", "flustered"))
        self.assertEqual(episode_looks.nearest(look, "blushing"), "flustered")
        self.assertEqual(episode_looks.nearest(look, "laughing"), "happy")
        self.assertEqual(episode_looks.nearest(look, "drenched"), "neutral")
        self.assertEqual(episode_looks.nearest(look, "sad"), "neutral")

    def test_modern_looks_start_from_the_phone_portrait_and_canon_from_the_sprite(self):
        self.char.photo_neutral.name = "photos/canon.png"
        self.char.save()
        messenger.save_char_profile(self.char, {"neutral_url": "/media/messenger/phone.png"})
        with patch.object(messenger, "_read_storage_image", side_effect=lambda pick: (str(pick).encode(), "image/png")):
            modern = episode_looks.references(self.user, self.char, "modern")
            canon = episode_looks.references(self.user, self.char, "canon")
        self.assertIn(b"phone.png", modern[0][0])
        self.assertIn(b"canon.png", canon[0][0])

    def test_the_browser_cut_must_be_a_transparent_png(self):
        look, _, _ = self.make()
        with self.assertRaises(ValueError):
            episode_looks.save_cut(look, "happy", png(alpha=False))
        with self.assertRaises(ValueError):
            episode_looks.save_cut(look, "happy", b"not a picture")
        response = self.client.post(reverse("vn_scenes_api"), data={
            "kind": "episode_cut", "look_id": look.pk, "mood": "happy",
            "file": SimpleUploadedFile("happy.png", png(), content_type="image/png")})
        self.assertEqual(response.status_code, 200)
        packed = response.json()["look"]
        self.assertTrue(packed["moods"]["happy"]["cut"])
        self.assertEqual(packed["needs_cut"], ["neutral"])
        look.refresh_from_db()
        self.assertIn("-cut-", episode_looks.url(look, "happy")[0])

    def test_someone_elses_look_cant_be_used_or_changed(self):
        look, _, _ = self.make()
        stranger = get_user_model().objects.create_user(username="stranger")
        self.client.force_login(stranger)
        self.assertEqual(self.post("episode_look_delete", look_id=look.pk).status_code, 400)
        self.assertTrue(EpisodeLook.objects.filter(pk=look.pk).exists())
        self.assertEqual(vn_scenes.pick_looks(stranger, [self.char], {self.char.slug: look.pk}), {})

    def test_the_launch_lists_the_cast_and_the_user_in_their_setting(self):
        look, _, _ = self.make()
        data = self.post("episode_looks", thread_id=self.thread.pk).json()
        mira, me = data["cast"]
        self.assertEqual((mira["key"], mira["setting"], mira["chosen"]), (self.char.slug, "canon", look.pk))
        self.assertEqual(me["key"], "user")
        self.assertEqual(data["core_moods"], episode_looks.CORE_MOODS)

    def test_storyteller_sees_only_the_looks_moods_and_outfit_and_never_draws(self):
        look, _, _ = self.make(moods=("happy",))
        reply = {"title": "Rain", "handoff": "user_turn",
                 "beats": [{"speaker_slug": self.char.slug, "emotion": "lovestruck", "text": "Oh. It's you."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply) as model, \
             patch.object(messenger, "make_picture") as image:
            scene = vn_scenes.start_scene(self.user, self.thread)
        prompt = model.call_args.args[1]
        self.assertIn("Moods: happy, neutral", prompt)
        self.assertIn("Outfit (Day): black wool coat; grey scarf", prompt)
        image.assert_not_called()
        beat = scene["beats"][0]
        self.assertEqual((beat["asked_emotion"], beat["emotion"], beat["look_id"]), ("lovestruck", "neutral", look.pk))
        self.assertIn(look.moods["neutral"]["raw"].rsplit("/", 1)[-1], beat["sprite_url"])

    def test_without_a_look_the_stage_shows_only_the_name(self):
        reply = {"title": "Rain", "handoff": "user_turn",
                 "beats": [{"speaker_slug": self.char.slug, "emotion": "happy", "text": "Hi."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply):
            scene = vn_scenes.start_scene(self.user, self.thread)
        self.assertEqual(scene["beats"][0]["sprite_url"], "")
        self.assertEqual(scene["looks"], {})

    def test_deleting_a_mood_keeps_the_base_and_deleting_the_look_removes_files(self):
        look, _, _ = self.make()
        with self.assertRaises(ValueError):
            episode_looks.remove_mood(look, "neutral")
        happy = look.moods["happy"]["raw"]
        episode_looks.remove_mood(look, "happy")
        self.assertFalse(default_storage.exists(happy))
        base = look.moods["neutral"]["raw"]
        episode_looks.delete(look)
        self.assertFalse(default_storage.exists(base))


class OutfitChangeTests(LooksSetup):
    def scene_with_change(self):
        self.look, _, _ = self.make(moods=("happy",))
        reply = {"title": "Rain", "handoff": "user_turn", "beats": [
            {"speaker_slug": self.char.slug, "emotion": "happy", "text": "Finally, you're here."},
            {"speaker_slug": "narrator", "text": "The downpour soaks them both before they reach the porch.",
             "stage": {"outfit_change": {self.char.slug: "black wool coat, soaked through; grey scarf, dripping",
                                         "stranger": "a cape"}}},
            {"speaker_slug": self.char.slug, "emotion": "happy", "text": "Well. That happened."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply), \
             patch.object(messenger, "make_picture") as image:
            scene = vn_scenes.start_scene(self.user, self.thread)
        image.assert_not_called()  # the story changing clothes never draws by itself
        return scene

    def test_the_story_notes_the_change_and_keeps_it_as_a_fact(self):
        scene = self.scene_with_change()
        first, change, after = scene["beats"]
        self.assertNotIn("outfit_change", first)
        self.assertEqual(change["outfit_change"], [{"slug": self.char.slug, "name": "Mira",
                                                    "outfit": "black wool coat, soaked through; grey scarf, dripping"}])
        self.assertIn("soaked", after["stage"]["continuity"]["outfits"][self.char.slug])
        self.assertNotIn("soaked", json.dumps(first["stage"]))
        roster = vn_scenes._build_char_roster([self.char], self.user, None, {self.char.slug: self.look},
                                              scene["continuity"]["outfits"])
        self.assertIn("Outfit now: black wool coat, soaked through", roster)

    def test_drawing_the_new_look_dresses_them_from_that_passage_on(self):
        scene = self.scene_with_change()
        first, change, after = scene["beats"]
        with patch.object(messenger, "make_picture", side_effect=[(b"wet", 0), (b"wet-happy", 0)]) as image:
            scene, _, errors = vn_scenes.change_look(self.user, change["id"], self.char.slug,
                                                     outfit=change["outfit_change"][0]["outfit"], name="Soaked")
        self.assertEqual(errors, [])
        self.assertIn("Change only the clothes", image.call_args_list[0].args[1])
        wet = EpisodeLook.objects.get(name="Soaked")
        self.assertEqual(wet.parent_id, self.look.pk)
        first, change, after = scene["beats"]
        self.assertEqual(first["look_id"], self.look.pk)
        self.assertEqual(after["look_id"], wet.pk)
        self.assertEqual(change["stage_before"]["looks"][self.char.slug], self.look.pk)  # reading back stays true
        self.assertEqual(scene["current_stage"]["looks"][self.char.slug], wet.pk)
        self.assertEqual(change["outfit_change"], [])
        self.assertEqual(vn_scenes.scene_looks(self.user, scene)[self.char.slug], wet)

    def test_keeping_the_picture_only_closes_the_note(self):
        scene = self.scene_with_change()
        change = scene["beats"][1]
        with patch.object(messenger, "make_picture") as image:
            scene, cost, _ = vn_scenes.change_look(self.user, change["id"], self.char.slug, keep=True)
        image.assert_not_called()
        self.assertEqual(scene["beats"][1]["outfit_change"], [])
        self.assertEqual(scene["beats"][2]["look_id"], self.look.pk)

    def test_switching_to_someone_elses_look_is_refused(self):
        scene = self.scene_with_change()
        other = Character.objects.create(author=self.user, name="Ivo", slug="looks-ivo")
        theirs = EpisodeLook.objects.create(author=self.user, character=other, setting="canon", name="Ivo's",
                                            moods={"neutral": {"raw": "x.png", "cut": ""}})
        with self.assertRaises(Exception):
            vn_scenes.change_look(self.user, scene["beats"][0]["id"], self.char.slug, look_id=theirs.pk)
        spare = EpisodeLook.objects.create(author=self.user, character=self.char, setting="canon", name="Evening",
                                           moods={"neutral": {"raw": "e.png", "cut": ""}})
        scene, _, _ = vn_scenes.change_look(self.user, scene["beats"][2]["id"], self.char.slug, look_id=spare.pk)
        self.assertEqual(scene["beats"][0]["look_id"], self.look.pk)
        self.assertEqual(scene["beats"][2]["look_id"], spare.pk)


class FaceTests(LooksSetup):
    def test_narration_keeps_the_last_face_instead_of_flipping_to_neutral(self):
        self.make(moods=("happy", "sad"))
        reply = {"title": "Steps", "handoff": "user_turn", "beats": [
            {"speaker_slug": self.char.slug, "emotion": "happy", "text": "You came."},
            {"speaker_slug": "narrator", "emotion": "neutral", "text": "Rain starts."},
            {"speaker_slug": self.char.slug, "emotion": "sad", "text": "My coat."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply):
            scene = vn_scenes.start_scene(self.user, self.thread)
        self.assertEqual([b["emotion"] for b in scene["beats"]], ["happy", "happy", "sad"])
        follow = {"handoff": "user_turn", "beats": [{"speaker_slug": "narrator", "text": "She wrings out her scarf."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=follow):
            scene, new = vn_scenes.step_scene(self.user, "I hand her a towel.")
        self.assertEqual(new[0]["emotion"], "sad")  # carried over from the last turn's stage


class LookCheckTests(LooksSetup):
    SEEN = '{"hair": "silver, shoulder length, straight fringe", "eyes": "green", "skin": "pale", "face": "narrow", ' \
           '"build": "slim", "marks": "", "art_style": "anime cel shading"}'

    def test_bulba_describes_the_picture_and_the_card_prose_is_left_out(self):
        self.char.description = "A brooding archivist haunted by her past, with eyes like storm clouds."
        self.char.save()
        with patch.object(episode_looks, "references", return_value=[(b"ref", "image/png")]), \
             patch("mainapp.bulba.vision.prepare", return_value=("data:x", None)), \
             patch("mainapp.bulba.vision.describe", return_value=(self.SEEN, "test")), \
             patch.object(episode_looks, "review", return_value={"ok": True, "issues": []}), \
             patch.object(messenger, "make_picture", return_value=(b"img", 0)) as image:
            look, _, _ = episode_looks.create(self.user, self.char, "canon", "Day", "black coat", moods=["happy"])
        base, mood = image.call_args_list[0].args[1], image.call_args_list[1].args[1]
        self.assertIn("hair: silver, shoulder length", base)
        self.assertIn("the pictures win", base)
        self.assertIn("Exactly two arms and two hands", base)
        self.assertNotIn("storm clouds", base)
        self.assertIn("Change only the face", mood)
        self.assertIn("Do not move, add, remove or redraw arms, hands", mood)
        self.assertEqual(look.identity["eyes"], "green")
        self.assertIn("green", episode_looks.pack(look)["identity"])

    def test_bulbas_review_turns_counts_into_plain_issues(self):
        look, _, _ = self.make()
        answer = json.dumps({"arms": 3, "hands": 2, "extra_or_merged_limbs": True, "fingers_ok": True, "same_person": True,
                             "outfit_missing": ["grey scarf"], "background_plain": True, "notes": "The third arm is behind her."})
        with patch("mainapp.bulba.vision.looker", return_value=("vision/model", "x")), \
             patch("mainapp.bulba.vision.prepare", return_value=("data:x", None)), \
             patch("mainapp.ai_client.complete", return_value=answer) as call:
            result = episode_looks.review(self.user, look, [(b"ref", "image/png")], (b"drawn", "image/png"))
        self.assertFalse(result["ok"])
        self.assertIn("3 arms.", result["issues"])
        self.assertIn("Missing from the outfit: grey scarf.", result["issues"])
        self.assertEqual(len([c for c in call.call_args.args[2][0]["content"] if c["type"] == "image_url"]), 2)
        good = json.dumps({"arms": 2, "hands": 2, "extra_or_merged_limbs": False, "fingers_ok": True, "same_person": True,
                           "outfit_missing": [], "background_plain": True, "notes": ""})
        with patch("mainapp.bulba.vision.looker", return_value=("vision/model", "x")), \
             patch("mainapp.bulba.vision.prepare", return_value=("data:x", None)), \
             patch("mainapp.ai_client.complete", return_value=good):
            self.assertEqual(episode_looks.review(self.user, look, [], (b"drawn", "image/png")), {"ok": True, "issues": []})

    def test_a_mood_whose_outline_changed_is_flagged_and_can_be_redrawn(self):
        look, _, _ = self.make()
        episode_looks.save_cut(look, "happy", png(), body_changed=0.02)
        self.assertNotIn("flag", look.moods["happy"])
        episode_looks.save_cut(look, "happy", png(), body_changed=0.19)
        self.assertIn("19%", look.moods["happy"]["flag"])
        self.assertIn("arm", episode_looks.pack(look)["moods"]["happy"]["flag"])
        old = look.moods["happy"]["raw"]
        with patch.object(messenger, "make_picture", return_value=(b"again", 0.01)) as image:
            cost = episode_looks.redraw_mood(self.user, look, "happy")
        self.assertIn("Change only the face", image.call_args.args[1])
        self.assertEqual(cost, 0.01)
        self.assertNotEqual(look.moods["happy"]["raw"], old)
        self.assertEqual(look.moods["happy"]["cut"], "")
        self.assertNotIn("flag", look.moods["happy"])
        with self.assertRaises(ValueError):
            episode_looks.redraw_mood(self.user, look, "neutral")

    def test_redrawing_the_whole_look_redraws_every_mood_from_the_new_neutral(self):
        look, _, _ = self.make(moods=("happy", "sad"))
        with patch.object(episode_looks, "references", return_value=[(b"ref", "image/png")]), \
             patch.object(episode_looks, "review", return_value={"ok": True, "issues": []}), \
             patch.object(messenger, "make_picture", side_effect=[(b"n2", 0), (b"h2", 0), (b"s2", 0)]) as image:
            cost, errors = episode_looks.redraw_look(self.user, look)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(look.moods), ["happy", "neutral", "sad"])
        self.assertEqual(image.call_args_list[1].kwargs["references"], [(b"n2", "image/png")])
        self.assertEqual(look.review, {"ok": True, "issues": []})

    def test_the_browser_sends_the_outline_change_with_the_cut(self):
        look, _, _ = self.make()
        response = self.client.post(reverse("vn_scenes_api"), data={
            "kind": "episode_cut", "look_id": look.pk, "mood": "happy", "body_changed": "0.0562",
            "file": SimpleUploadedFile("happy.png", png(), content_type="image/png")})
        self.assertIn("6%", response.json()["look"]["moods"]["happy"]["flag"])
        response = self.client.post(reverse("vn_scenes_api"), data={
            "kind": "episode_cut", "look_id": look.pk, "mood": "happy", "body_changed": "0.0004",
            "file": SimpleUploadedFile("happy.png", png(), content_type="image/png")})
        self.assertEqual(response.json()["look"]["moods"]["happy"]["flag"], "")

    def test_a_flagged_mood_stays_off_the_stage_until_redrawn(self):
        look, _, _ = self.make(moods=("happy",))
        episode_looks.save_cut(look, "happy", png(), body_changed=0.2)
        self.assertEqual(episode_looks.url(look, "happy")[1], "neutral")
        episode_looks.save_cut(look, "happy", png(), body_changed=0.001)
        self.assertEqual(episode_looks.url(look, "happy")[1], "happy")
