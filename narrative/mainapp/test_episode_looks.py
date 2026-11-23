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


class EpisodeLookTests(TestCase):
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
