import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from mainapp import ai_client, messenger, vn_scenes, vn_support
from mainapp.models import Character


class EpisodeTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.user = get_user_model().objects.create_user(username="director", password="test-password")
        self.char = Character.objects.create(author=self.user, name="Mira", slug="mira",
                                             description="Keeps a secret map of the old city.", personality="Dry and reserved.")
        self.thread = messenger.create_thread(self.user, [self.char])
        data = messenger.thread_data(self.thread)
        data.update(persona={"name": "Rowan", "description": "A visiting historian."},
                    memory="Mira promised to return the brass key.", clock_offset=-86400)
        messenger.save_thread_data(self.thread, data)
        self.client.force_login(self.user)

    def reply(self, text="You brought the map.", **extra):
        return {"title": "The map", "handoff": "user_turn",
                "beats": [{"speaker_slug": self.char.slug, "emotion": "neutral", "text": text}], **extra}

    def start(self, **kwargs):
        with patch.object(vn_scenes, "_call_vn_json", return_value=self.reply()):
            return vn_scenes.start_scene(self.user, thread=self.thread, **kwargs)

    def test_template_mounts_episode_and_audio_without_losing_phone_controls(self):
        response = self.client.get(reverse("screen_hub"))
        for expected in ('id="app-scenes"', 'id="vnScenesRoot"', 'id="vnAudioPlayer"', 'TG.openChats()'):
            self.assertContains(response, expected)

    def test_thread_identity_memory_clock_card_and_directions_reach_scene(self):
        with patch.object(vn_scenes, "_call_vn_json", return_value=self.reply()) as generate:
            scene = vn_scenes.start_scene(self.user, thread=self.thread, direction="Long descriptions with asides.")
        prompt = generate.call_args.args[1]
        for expected in ("Rowan", "visiting historian", "brass key", "secret map", "Long descriptions with asides"):
            self.assertIn(expected, prompt)
        self.assertNotIn("STRICT PHONE", prompt)
        self.assertNotIn("3 to 5", prompt)
        self.assertEqual(scene["context"]["clock"], vn_support.scene_context(self.user, self.thread)["clock"])

    def test_splitting_preserves_long_prose_and_more_than_six_blocks(self):
        prose = ("The map had changed since winter; she checked its streets carefully. " * 40) + "\n\nA new paragraph."
        blocks = [{"speaker_slug": "narrator", "text": prose}] * 7
        boxes = vn_scenes._enrich_beats(self.user, [self.char], blocks)
        self.assertEqual(" ".join(" ".join(b["text"] for b in boxes).split()), " ".join(" ".join([prose] * 7).split()))
        self.assertGreater(len(boxes), 7)
        self.assertTrue(all(len(b["text"]) <= 420 for b in boxes))

    def test_showing_a_listeners_reaction_does_not_change_who_speaks(self):
        other = Character.objects.create(author=self.user, name="Ivo", slug="ivo")
        blocks = [{"speaker_slug": self.char.slug, "character_slug": other.slug,
                   "emotion": "surprised", "text": "I found your map."}]
        boxes = vn_scenes._enrich_beats(self.user, [self.char, other], blocks)
        self.assertEqual(boxes[0]["speaker_slug"], self.char.slug)
        self.assertEqual(boxes[0]["character_slug"], other.slug)

    def test_generated_user_dialogue_is_rejected_instead_of_attributed_to_a_character(self):
        with self.assertRaises(ai_client.AIError):
            vn_scenes._enrich_beats(self.user, [self.char], [{"speaker_slug": "user", "text": "I agree."}])

    def test_long_history_is_preserved_and_continuity_reaches_next_turn(self):
        scene = self.start()
        seed = scene["beats"][0]
        scene["beats"] = [{**seed, "id": f"line-{i}", "text": f"Line {i}."} for i in range(90)]
        scene["continuity"] = {"summary": "They exchanged the brass key at the beginning.",
                               "outfits": {self.char.slug: "green coat"}}
        vn_scenes.save_vn_state(self.user, {"active_scene": scene})
        with patch.object(vn_scenes, "_call_vn_json", return_value=self.reply(continuity={"location": "The archive"})) as generate:
            updated, _ = vn_scenes.step_scene(self.user, "I unlock it.")
        self.assertEqual(len(updated["beats"]), 92)
        self.assertIn("exchanged the brass key", generate.call_args.args[1])
        self.assertEqual(updated["continuity"]["outfits"][self.char.slug], "green coat")
        with patch.object(vn_scenes, "_call_vn_json", side_effect=ai_client.AIError("unavailable")), \
             patch.object(messenger, "make_picture") as image:
            entry, cost = vn_scenes.finish_scene_with_cg(self.user, capture_image=False)
        image.assert_not_called()
        self.assertEqual(len(entry["transcript"]), 92)
        self.assertIn("exchanged the brass key", entry["summary"])
        self.assertEqual(cost, 0)
        self.thread.refresh_from_db()
        notice = messenger.thread_data(self.thread)["messages"][-1]
        self.assertEqual(notice["role"], "system")
        self.assertIn("brass key", notice["text"])

    def test_provider_failure_saves_episode_and_memory_without_broken_photo(self):
        self.start()
        with patch.object(vn_scenes, "_call_vn_json", return_value={"summary": "They opened the archive."}), \
             patch.object(messenger, "make_picture", side_effect=ai_client.AIError("Provider unavailable")):
            entry, _ = vn_scenes.finish_scene_with_cg(self.user)
        self.assertEqual(entry["image_error"], "Provider unavailable")
        self.assertIsNone(vn_scenes.get_vn_state(self.user)["active_scene"])
        self.thread.refresh_from_db()
        messages = messenger.thread_data(self.thread)["messages"]
        self.assertIn("opened the archive", messages[-1]["text"])
        self.assertFalse(any(m.get("photo") for m in messages))

    def test_stale_result_cannot_overwrite_newer_scene(self):
        scene = self.start()
        old = (scene["id"], scene["revision"])
        vn_scenes.save_vn_state(self.user, {"active_scene": {**scene, "location": "Updated"}})
        with self.assertRaises(ai_client.AIError):
            vn_scenes.save_vn_state(self.user, {"active_scene": scene}, expected=old)
        self.assertEqual(vn_scenes.get_vn_state(self.user)["active_scene"]["location"], "Updated")

    def test_new_episode_does_not_silently_replace_open_one(self):
        scene = self.start()
        with self.assertRaises(ai_client.AIError), patch.object(vn_scenes, "_call_vn_json") as generate:
            vn_scenes.start_scene(self.user, thread=self.thread)
        generate.assert_not_called()
        self.assertEqual(vn_scenes.get_vn_state(self.user)["active_scene"]["id"], scene["id"])

    def test_default_character_can_continue_and_is_not_modified_by_sprite_generation(self):
        other = get_user_model().objects.create_user(username="curator")
        self.char.author = other
        self.char.is_default = True
        self.char.save(update_fields=["author", "is_default"])
        self.start()
        with patch.object(vn_scenes, "_call_vn_json", return_value=self.reply()):
            scene, _ = vn_scenes.step_scene(self.user)
        with patch.object(messenger, "make_picture", return_value=(b"image", .02)):
            updated, _, _, _ = vn_scenes.generate_beat_sprite(self.user, char_slug=self.char.slug, emotion="curious")
        self.assertTrue(updated["sprite_cache"])
        self.char.refresh_from_db()
        self.assertFalse(self.char.extra_sprites)

    def test_finale_uses_each_participants_reference_and_scene_outfits(self):
        second = Character.objects.create(author=self.user, name="Ivo", slug="ivo")
        self.thread.characters.add(second)
        self.start()
        scene = vn_scenes.get_vn_state(self.user)["active_scene"]
        scene["continuity"] = {"outfits": {self.char.slug: "green coat", second.slug: "blue shirt"}}
        vn_scenes.save_vn_state(self.user, {"active_scene": scene})
        def references(c):
            return [(c.slug.encode(), "image/png"), (b"extra-" + c.slug.encode(), "image/png")]
        with patch.object(vn_scenes, "_call_vn_json", return_value={"summary": "They met."}), \
             patch.object(messenger, "load_character_references", side_effect=references), \
             patch.object(messenger, "make_picture", return_value=(b"image", 0)) as image:
            vn_scenes.finish_scene_with_cg(self.user)
        self.assertEqual(image.call_args.kwargs["references"][:2],
                         [(slug.encode(), "image/png") for slug in scene["character_slugs"]])
        for text in ("Mira", "Ivo", "green coat", "blue shirt"):
            self.assertIn(text, image.call_args.args[1])

    def test_empty_turn_retains_saved_history(self):
        scene = self.start()
        with patch.object(vn_scenes, "_call_vn_json", return_value={"beats": []}), self.assertRaises(ai_client.AIError):
            vn_scenes.step_scene(self.user, "I answer.")
        self.assertEqual(vn_scenes.get_vn_state(self.user)["active_scene"]["beats"], scene["beats"])

    def test_outfit_cache_does_not_reuse_or_overwrite_a_different_costume(self):
        cache = {}
        with patch.object(messenger, "make_picture", return_value=(b"image", .02)) as image:
            first = vn_scenes.resolve_or_generate_sprite(self.user, self.char, "happy", True, "green coat", cache)
            repeated = vn_scenes.resolve_or_generate_sprite(self.user, self.char, "happy", False, "green coat", cache)
            changed = vn_scenes.resolve_or_generate_sprite(self.user, self.char, "happy", False, "blue shirt", cache)
        image.assert_called_once()
        self.assertEqual(first["url"], repeated["url"])
        self.assertFalse(repeated["needs_gen"])
        self.assertTrue(changed["needs_gen"])
        self.char.refresh_from_db()
        self.assertFalse(self.char.photo_happy)

    def test_api_can_complete_without_requesting_a_picture(self):
        self.start()
        with patch.object(vn_scenes, "_call_vn_json", return_value={"summary": "They met."}), \
             patch.object(messenger, "make_picture") as image:
            response = self.client.post(reverse("vn_scenes_api"),
                data=json.dumps({"action": "finish_scene", "capture_image": False}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["vn_scenes"]["active_scene"])
        image.assert_not_called()

    def test_polish_preserves_metadata_and_original_before_splitting(self):
        blocks = self.reply("Her jaw clenches.")["beats"]
        with patch("mainapp.bulba.polish.approved", return_value=["pet_phrase"]), \
             patch.object(ai_client, "complete", return_value=json.dumps({"fixes": [
                 {"find": "Her jaw clenches.", "replace": "She sets the map down."}]})):
            updated, error = vn_support.polish_blocks(self.user, blocks, "They are in the archive.", True)
        self.assertFalse(error)
        self.assertEqual(updated[0]["text"], "She sets the map down.")
        self.assertEqual(updated[0]["original_text"], "Her jaw clenches.")
        self.assertEqual(updated[0]["speaker_slug"], self.char.slug)
