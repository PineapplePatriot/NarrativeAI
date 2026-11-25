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

from mainapp import ai_client, messenger, sprite_cuts, sprites
from mainapp.models import Character


def png(alpha=True):
    out = io.BytesIO()
    Image.new("RGBA" if alpha else "RGB", (4, 6)).save(out, format="PNG")
    return out.getvalue()


class SpriteCutTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.user = get_user_model().objects.create_user(username="cutter", persona_name="Rowan")
        self.char = Character.objects.create(author=self.user, name="Mira", slug="cut-mira", description="Silver hair, green coat.")
        self.char.photo_neutral.save("mira-neutral.png", ContentFile(png(alpha=False)))
        self.char.photo_happy.save("mira-happy.png", ContentFile(png(alpha=False)))
        self.client.force_login(self.user)

    def post_cut(self, name, data=None, target="character"):
        return self.client.post(reverse("sprite_cut"), data={
            "target": target, "slug": self.char.slug, "name": name,
            "file": SimpleUploadedFile("cut.png", data or png(), content_type="image/png")})

    def test_a_cut_replaces_the_sprite_and_can_be_undone(self):
        original = self.char.photo_happy.name
        r = self.post_cut("photo_happy")
        self.assertEqual(r.status_code, 200)
        self.char.refresh_from_db()
        self.assertTrue(self.char.photo_happy.name.startswith("cutouts/"))
        self.assertEqual(r.json()["cut"], ["photo_happy"])
        again = self.post_cut("photo_happy")  # cutting again keeps the first original
        self.assertEqual(again.status_code, 200)
        self.char.refresh_from_db()
        self.assertEqual(self.char.sprite_originals["photo_happy"], original)
        undo = self.client.post(reverse("sprite_cut"), data=json.dumps({"target": "character", "slug": self.char.slug,
                                                                        "name": "photo_happy", "undo": True}),
                                content_type="application/json")
        self.assertEqual(undo.status_code, 200)
        self.char.refresh_from_db()
        self.assertEqual(self.char.photo_happy.name, original)
        self.assertEqual(undo.json()["cut"], [])

    def test_only_a_transparent_png_of_your_own_sprite_is_kept(self):
        self.assertEqual(self.post_cut("photo_happy", png(alpha=False)).status_code, 400)
        self.assertEqual(self.post_cut("photo_sad").status_code, 400)  # nothing there to cut
        self.assertEqual(self.post_cut("persona_photo_happy").status_code, 400)  # not this character's
        stranger = get_user_model().objects.create_user(username="stranger")
        self.client.force_login(stranger)
        self.assertEqual(self.post_cut("photo_happy").status_code, 404)

    def test_extra_moods_and_persona_pictures_cut_too(self):
        sprites.save(self.char, "smug", png(alpha=False))
        self.assertEqual(self.post_cut("extra:smug").status_code, 200)
        self.char.refresh_from_db()
        self.assertTrue(self.char.extra_sprites["first"]["smug"].startswith("cutouts/"))
        self.user.persona_photo_neutral.save("me.png", ContentFile(png(alpha=False)))
        r = self.post_cut("persona_photo_neutral", target="persona")
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.persona_photo_neutral.name.startswith("cutouts/"))

    def test_an_upload_after_a_cut_makes_the_old_original_stale(self):
        self.post_cut("photo_happy")
        self.char.refresh_from_db()
        self.char.photo_happy.save("new-upload.png", ContentFile(png(alpha=False)))  # the form's own upload
        self.assertEqual(sprite_cuts.originals_list(self.char), [])
        self.assertEqual(sprite_cuts.uncut_bytes(self.char, "photo_happy")[0], png(alpha=False))

    def test_plain_drawing_uses_a_key_colour_and_moods_come_from_the_uncut_neutral(self):
        uncut = self.char.photo_neutral.name
        self.post_cut("photo_neutral")
        with default_storage.open(uncut, "rb") as handle:
            uncut_bytes = handle.read()
        with patch.object(ai_client, "generate_image", return_value=(png(alpha=False), 0.01)) as draw:
            r = self.client.post(reverse("character_sprite", args=[self.char.slug]),
                                 data=json.dumps({"emotion": "sad", "plain": True}), content_type="application/json")
        data = r.json()
        self.assertEqual((data["name"], data["cut"]), ("photo_sad", True))
        prompt, reference = draw.call_args.args[1], draw.call_args.args[2]
        self.assertIn("completely flat", prompt)
        self.assertNotIn("green", prompt.split("Background:")[1].split("(")[0])  # she wears green: another key
        self.assertEqual(reference, uncut_bytes)
        with patch.object(ai_client, "generate_image", return_value=(png(alpha=False), 0.01)) as draw:
            r = self.client.post(reverse("character_sprite", args=[self.char.slug]),
                                 data=json.dumps({"emotion": "angry"}), content_type="application/json")
        self.assertFalse(r.json()["cut"])
        self.assertNotIn("completely flat", draw.call_args.args[1])

    def test_a_sticker_you_own_gets_its_cut_out(self):
        messenger.save_char_profile(self.char, {"sticker_pack": [{"mood": "happy", "url": "/media/messenger/stickers/a.png"}]})
        messenger.save_user_profile(self.user, {"custom_stickers": [{"id": "custom_1", "pack": "My Stickers", "name": "x",
                                                                      "url": "/media/messenger/stickers/b.png"}]})
        new = sprite_cuts.replace_sticker(self.user, "/media/messenger/stickers/a.png", png())
        self.char.refresh_from_db()
        self.assertEqual(messenger.char_profile(self.char)["sticker_pack"][0]["url"], new)
        mine = sprite_cuts.replace_sticker(self.user, "/media/messenger/stickers/b.png", png())
        self.assertEqual(messenger.user_profile(self.user)["custom_stickers"][0]["url"], mine)
        with self.assertRaises(ValueError):
            sprite_cuts.replace_sticker(self.user, "/media/someone-elses.png", png())
        r = self.client.post(reverse("messenger_api"), data={
            "kind": "sticker_cut", "url": mine, "file": SimpleUploadedFile("s.png", png(), content_type="image/png")})
        self.assertEqual(r.status_code, 200)

    def test_stickers_are_drawn_on_a_key_colour_with_their_white_outline(self):
        with patch.object(messenger, "make_picture", return_value=(png(alpha=False), 0)) as draw, \
             patch.object(messenger, "load_character_references", return_value=[]):
            messenger.make_sticker(self.user, self.char, "happy")
        prompt = draw.call_args.args[1]
        self.assertIn("thick white outline", prompt)
        self.assertIn("completely flat", prompt)
