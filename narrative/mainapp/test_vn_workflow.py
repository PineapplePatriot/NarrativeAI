import copy
import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from mainapp import ai_client, messenger, presets, vn_history, vn_scenes, vn_story, vn_support
from mainapp.models import Character, Preset
from users.models import ConnectionProfile


class EpisodeWorkflowTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory(); self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name); settings.enable(); self.addCleanup(settings.disable)
        self.user = get_user_model().objects.create_user(username="workflow", persona_name="Rowan")
        ConnectionProfile.objects.create(user=self.user, name="test", provider="openrouter", api_key="test", model="xiaomi/mimo-v2.6-pro")
        self.char = Character.objects.create(author=self.user, name="Mira", slug="workflow-mira", description="Keeps the brass key.")
        self.thread = messenger.create_thread(self.user, [self.char])
        self.client.force_login(self.user)

    def response(self, **extra):
        return {"title": "Archive", "beats": [{"speaker_slug": self.char.slug, "emotion": "neutral", "text": "You brought the key."}],
                "handoff": "user_turn", "choices": ["I did.", "Not yet."], **extra}

    def start(self, response=None, **settings):
        with patch.object(vn_scenes, "_call_vn_json", return_value=response or self.response()):
            return vn_scenes.start_scene(self.user, self.thread, **settings)

    def post(self, action, **extra):
        return self.client.post(reverse("vn_scenes_api"), data=json.dumps({"action": action, **extra}), content_type="application/json")

    def test_real_preset_assembly_honours_enabled_blocks_macros_and_lore(self):
        data = presets.normalize({"blocks": [
            {"name": "My style", "content": "VOICE FOR {{char}} AND {{user}}"},
            {"name": "Disabled", "enabled": False, "content": "DO NOT SEND THIS"},
            {"name": "Card", "kind": "marker", "marker": "char_description"},
            {"name": "Lore", "kind": "marker", "marker": "lore_before"},
            {"name": "History", "kind": "marker", "marker": "chat_history"}]})
        obj = Preset.objects.create(user=self.user, name="Private style", data=data, is_active=True)
        presets.activate(obj)
        raw = messenger.thread_data(self.thread)
        raw.update(lore_mode="local", lorebook={"entries": [{"keys": ["brass"], "content": "The brass key opens Gate Nine."}]})
        raw["messages"] = [{"role": "user", "text": "I found the brass key."}]
        messenger.save_thread_data(self.thread, raw)
        with patch.object(ai_client, "complete", return_value=json.dumps(self.response())) as model:
            scene = vn_scenes.start_scene(self.user, self.thread)
        messages = json.dumps(model.call_args.args[2])
        prompt = "\n".join(message["content"] for message in model.call_args.args[2])
        self.assertIn("SCENE CAST", prompt)
        self.assertIn(f'"slug": "{self.char.slug}"', prompt)
        self.assertIn("VOICE FOR Mira AND Rowan", messages)
        self.assertIn("Keeps the brass key", messages)
        self.assertIn("opens Gate Nine", messages)
        self.assertNotIn("DO NOT SEND THIS", messages)
        self.assertEqual(scene["last_request"]["preset_id"], obj.pk)
        self.assertTrue(scene["last_request"]["lore"])

    def test_free_writing_suppresses_model_choices_and_preferences_persist(self):
        scene = self.start(interaction_mode="write")
        self.assertEqual(scene["choices"], [])
        result = self.post("episode_preferences", interaction_mode="choices", direction="Long descriptive narration.")
        self.assertEqual(result.status_code, 200)
        scene = result.json()["scene"]
        self.assertEqual(scene["interaction_mode"], "choices")
        with patch.object(vn_scenes, "_call_vn_json", return_value=self.response()) as generate:
            vn_scenes.step_scene(self.user)
        self.assertIn("Long descriptive narration", generate.call_args.args[1])

    def test_directing_can_write_user_character_with_their_own_sprite(self):
        self.user.persona_photo_happy.name = "personas/rowan-happy.png"
        self.user.save(update_fields=["persona_photo_happy"])
        response = self.response(beats=[{"speaker_slug": "user", "character_slug": "user", "emotion": "happy", "text": "I kept my promise."}])
        scene = self.start(response, authoring_mode="director")
        self.assertEqual(scene["beats"][0]["speaker_name"], "Rowan")
        self.assertIn("rowan-happy.png", scene["beats"][0]["sprite_url"])
        self.assertFalse(scene["beats"][0]["needs_sprite_gen"])

    def test_visual_change_occurs_on_its_passage_not_at_turn_opening(self):
        response = self.response(beats=[
            {"speaker_slug": "narrator", "text": "They wait outside.", "stage": {"location": "Street", "continuity": {"outfits": {self.char.slug: "green coat"}}}},
            {"speaker_slug": self.char.slug, "text": "Come inside.", "stage": {"location": "Archive", "continuity": {"outfits": {self.char.slug: "shirt sleeves"}}}}],
            continuity={"summary": "They entered the archive.", "outfits": {self.char.slug: "shirt sleeves"}})
        scene = self.start(response)
        first, second = scene["beats"]
        self.assertEqual(first["stage"]["location"], "Street")
        self.assertEqual(first["stage"]["continuity"]["outfits"][self.char.slug], "green coat")
        self.assertNotIn("They entered", json.dumps(first["stage"]))
        self.assertEqual(second["stage"]["location"], "Archive")
        self.assertEqual(scene["current_stage"]["continuity"]["summary"], "They entered the archive.")

    def test_edit_discards_future_and_saves_a_recoverable_version(self):
        scene = self.start(self.response(beats=[
            {"speaker_slug": self.char.slug, "text": "I have the key.", "stage": {"location": "Street"}},
            {"speaker_slug": self.char.slug, "text": "FUTURE SECRET IS A DRAGON.", "stage": {"location": "Vault", "continuity": {"summary": "FUTURE SECRET IS A DRAGON."}}}]))
        with patch.object(messenger, "ask_json", return_value={"stage": {"location": "Street", "continuity": {"summary": "Mira lost the key."}}}) as repair:
            edited = vn_history.edit(self.user, scene["beats"][0]["id"], "I lost the key.")
        self.assertEqual(len(edited["beats"]), 1)
        self.assertEqual(edited["beats"][0]["text"], "I lost the key.")
        self.assertNotIn("FUTURE SECRET", repair.call_args.args[1])
        self.assertNotIn("FUTURE SECRET", json.dumps(edited["continuity"]))
        saved = vn_scenes.get_vn_state(self.user)["drafts"]
        self.assertIn("FUTURE SECRET", json.dumps(saved[0]["scene"]))

    def test_regeneration_restores_checkpoint_and_uses_regenerate_trigger(self):
        scene = self.start(self.response(beats=[
            {"speaker_slug": self.char.slug, "text": "A beginning.", "stage": {"location": "Street"}},
            {"speaker_slug": self.char.slug, "text": "FUTURE_SECRET", "stage": {"location": "Vault", "continuity": {"summary": "FUTURE_SECRET"}}}]))
        with patch.object(vn_scenes, "_call_vn_json", return_value=self.response()) as generate:
            updated = vn_history.regenerate(self.user, scene["beats"][1]["id"], "Keep her reserved.")
        self.assertEqual(generate.call_args.args[3], "regenerate")
        self.assertNotIn("FUTURE_SECRET", generate.call_args.args[1])
        self.assertEqual(updated["beats"][0]["text"], "A beginning.")
        self.assertEqual(len(vn_scenes.get_vn_state(self.user)["drafts"]), 1)

    def test_failed_regeneration_keeps_original_scene(self):
        scene = self.start()
        with patch.object(vn_scenes, "_call_vn_json", side_effect=ai_client.AIError("blocked")), self.assertRaises(ai_client.AIError):
            vn_history.regenerate(self.user, scene["beats"][0]["id"])
        current = vn_scenes.get_vn_state(self.user)
        self.assertEqual(current["active_scene"], scene)
        self.assertEqual(current["drafts"], [])

    def test_branch_has_its_own_phone_context_and_lore_copy(self):
        data = messenger.thread_data(self.thread)
        data.update(lore_mode="local", lorebook={"title": "Original lore", "entries": []})
        messenger.save_thread_data(self.thread, data)
        scene = self.start()
        fork = vn_history.branch(self.user, scene["beats"][0]["id"])
        self.assertNotEqual(fork["thread_id"], self.thread.pk)
        branch_thread = vn_support.linked_thread(self.user, fork)
        self.assertEqual(branch_thread.data["lorebook"]["title"], "Original lore")
        branch_thread.data["lorebook"]["title"] = "Branch lore"; branch_thread.save(update_fields=["data"])
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data["lorebook"]["title"], "Original lore")
        self.assertEqual(vn_scenes.get_vn_state(self.user)["drafts"][0]["scene"]["id"], scene["id"])

    def test_branch_keeps_lore_updated_after_the_episode_started(self):
        scene = self.start()
        raw = messenger.thread_data(self.thread)
        raw.update(lore_mode="local", lorebook={"title": "Updated during the episode", "entries": []})
        messenger.save_thread_data(self.thread, raw)
        fork = vn_history.branch(self.user, scene["beats"][0]["id"])
        self.assertEqual(vn_support.linked_thread(self.user, fork).data["lorebook"]["title"], "Updated during the episode")

    def test_old_tab_cannot_edit_different_active_episode(self):
        scene = self.start()
        fork = vn_history.branch(self.user, scene["beats"][0]["id"])
        response = self.post("episode_preferences", scene_id=scene["id"], revision=scene["revision"], direction="Wrong tab")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(vn_scenes.get_vn_state(self.user)["active_scene"]["id"], fork["id"])

    def test_gallery_no_longer_silently_drops_older_episodes(self):
        entries = [{"id": str(i)} for i in range(65)]
        vn_scenes.save_vn_state(self.user, {"gallery": entries})
        self.assertEqual(len(vn_scenes.get_vn_state(self.user)["gallery"]), 65)

    def test_completed_episode_can_reopen_as_separate_branch(self):
        original = self.start()
        with patch.object(vn_scenes, "_call_vn_json", return_value={"summary": "They met."}):
            vn_scenes.finish_scene_with_cg(self.user, capture_image=False)
        reopened = vn_history.reopen_completed(self.user, original["id"])
        self.assertNotEqual(reopened["thread_id"], self.thread.pk)
        self.assertEqual(reopened["beats"], original["beats"])

    def test_request_inspection_contains_no_connection_credentials(self):
        with patch.object(ai_client, "complete", return_value=json.dumps(self.response())):
            scene = vn_scenes.start_scene(self.user, self.thread)
        response = self.post("inspect_request")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request"]["model"], "xiaomi/mimo-v2.6-pro")
        self.assertNotIn("api_key", json.dumps(scene["last_request"]))

    def test_regeneration_really_uses_generation_specific_preset_blocks(self):
        cfg = presets.normalize({"blocks": [
            {"name": "Normal", "content": "NORMAL_ONLY_SENTINEL", "triggers": ["normal"]},
            {"name": "Another take", "content": "REGENERATE_ONLY_SENTINEL", "triggers": ["regenerate"]},
            {"name": "History", "kind": "marker", "marker": "chat_history"}]})
        obj = Preset.objects.create(user=self.user, name="Triggers", data=cfg, is_active=True); presets.activate(obj)
        with patch.object(ai_client, "complete", return_value=json.dumps(self.response())) as model:
            scene = vn_scenes.start_scene(self.user, self.thread)
            vn_history.regenerate(self.user, scene["beats"][0]["id"])
        first = json.dumps(model.call_args_list[0].args[2]); second = json.dumps(model.call_args_list[1].args[2])
        self.assertIn("NORMAL_ONLY_SENTINEL", first); self.assertNotIn("REGENERATE_ONLY_SENTINEL", first)
        self.assertIn("REGENERATE_ONLY_SENTINEL", second); self.assertNotIn("NORMAL_ONLY_SENTINEL", second)

    def test_invalid_edit_state_does_not_destroy_original(self):
        scene = self.start()
        with patch.object(messenger, "ask_json", return_value={"stage": "invalid"}), self.assertRaises(ai_client.AIError):
            vn_history.edit(self.user, scene["beats"][0]["id"], "A correction.")
        self.assertEqual(vn_scenes.get_vn_state(self.user)["active_scene"], scene)

    def test_custom_expression_updates_the_selected_passage(self):
        scene = self.start()
        selected = scene["beats"][0]
        with patch.object(messenger, "make_picture", return_value=(b"image", 0)):
            updated, url, emotion, _ = vn_scenes.generate_beat_sprite(self.user, beat_id=selected["id"],
                char_slug=self.char.slug, emotion="curious")
        self.assertEqual(emotion, "curious")
        self.assertEqual(updated["beats"][0]["sprite_url"], url)
        self.assertEqual(updated["beats"][0]["emotion"], "curious")

    def test_unrecognized_assets_do_not_replace_the_setting_with_an_arbitrary_picture(self):
        self.assertEqual(vn_scenes._match_bg([{"id": "unrelated", "name": "Desert", "url": "/desert.png"}], "Archive")["url"], "")
        self.assertEqual(vn_scenes._match_track([{"id": "unrelated", "name": "Dance", "url": "/dance.mp3"}], "Quiet")["url"], "")

    def test_legacy_passage_without_checkpoint_is_not_unsafely_rewritten(self):
        scene = self.start()
        scene["beats"][0].pop("stage_before")
        vn_scenes.save_vn_state(self.user, {"active_scene": scene})
        with patch.object(vn_scenes, "_call_vn_json") as model, self.assertRaises(ai_client.AIError):
            vn_history.regenerate(self.user, scene["beats"][0]["id"])
        model.assert_not_called()

    def test_vn_character_slot_does_not_truncate_the_card_to_the_phone_limit(self):
        self.char.description = "Archive notes. " * 350 + " CRITICAL_LATE_CHARACTER_TRAIT"
        self.char.save(update_fields=["description"])
        with patch.object(ai_client, "complete", return_value=json.dumps(self.response())) as model:
            vn_scenes.start_scene(self.user, self.thread)
        self.assertIn("CRITICAL_LATE_CHARACTER_TRAIT", json.dumps(model.call_args.args[2]))

    def test_selected_preset_does_not_receive_a_second_hidden_writing_baseline(self):
        cfg = presets.normalize({"blocks": [{"name": "My style", "content": "My chosen writing instructions."},
            {"kind": "marker", "marker": "chat_history"}]})
        obj = Preset.objects.create(user=self.user, name="Only my instructions", data=cfg, is_active=True)
        presets.activate(obj)
        with patch.object(ai_client, "complete", return_value=json.dumps(self.response())) as model:
            vn_scenes.start_scene(self.user, self.thread)
        outgoing = json.dumps(model.call_args.args[2])
        self.assertIn("My chosen writing instructions", outgoing)
        self.assertNotIn("stock reactions (jaw clenching", outgoing)

    def test_switching_to_writing_and_back_keeps_existing_options(self):
        scene = self.start()
        self.assertEqual(self.post("episode_preferences", interaction_mode="write").json()["scene"]["choices"], [])
        restored = self.post("episode_preferences", interaction_mode="choices").json()["scene"]
        self.assertEqual(restored["choices"], scene["choices"])

    def test_options_can_be_requested_without_advancing_the_scene_or_drawing(self):
        original = self.start(interaction_mode="write")
        self.post("episode_preferences", interaction_mode="choices")
        with patch.object(vn_scenes, "_call_vn_json", return_value={"choices": ["Wait here.", "Ask about the key."]}), \
             patch.object(messenger, "make_picture") as picture:
            response = self.post("suggest_choices")
        self.assertEqual(response.status_code, 200)
        updated = response.json()["scene"]
        self.assertEqual(updated["beats"], original["beats"])
        self.assertEqual(updated["continuity"], original["continuity"])
        self.assertEqual(updated["choices"], ["Wait here.", "Ask about the key."])
        picture.assert_not_called()

    def test_step_without_image_flag_preserves_the_saved_preference(self):
        self.start()
        self.post("episode_preferences", auto_generate_sprites=True)
        with patch.object(vn_scenes, "_call_vn_json", return_value=self.response()), \
             patch.object(messenger, "make_picture", return_value=(b"image", 0)):
            response = self.post("step_scene", user_input="I bring the key.")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["scene"]["auto_generate_sprites"])

    def test_unfinished_episode_can_be_parked_and_resumed_without_model_calls(self):
        original = self.start()
        self.post("episode_preferences", auto_generate_sprites=True)
        with patch.object(vn_scenes, "_call_vn_json") as model:
            parked = self.post("park_scene")
            self.assertIsNone(parked.json()["scene"])
            draft = parked.json()["vn_scenes"]["drafts"][-1]
            resumed = self.post("resume_draft", draft_id=draft["id"])
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["scene"]["resumed_from"], original["id"])
        self.assertEqual(resumed.json()["scene"]["beats"], original["beats"])
        self.assertTrue(resumed.json()["scene"]["auto_generate_sprites"])
        model.assert_not_called()

    def test_malformed_requests_do_not_start_a_generation(self):
        bodies = [[], None, {"action": "start_scene", "thread_id": "not-a-chat"},
                  {"action": "start_scene", "thread_id": 0}, {"action": "start_scene", "thread_id": 10**30},
                  {"action": "start_scene", "thread_id": self.thread.pk, "auto_generate_sprites": "false"},
                  {"action": "start_scene", "thread_id": self.thread.pk, "character_slugs": "mira"}]
        with patch.object(vn_scenes, "_call_vn_json") as model:
            for body in bodies:
                response = self.client.post(reverse("vn_scenes_api"), data=json.dumps(body), content_type="application/json")
                self.assertEqual(response.status_code, 400, body)
        model.assert_not_called()

    def test_missing_or_empty_chat_does_not_silently_choose_another_character(self):
        with patch.object(vn_scenes, "_call_vn_json") as model:
            self.assertEqual(self.post("start_scene", thread_id=999999).status_code, 404)
            self.thread.characters.clear()
            self.assertEqual(self.post("start_scene", thread_id=self.thread.pk).status_code, 400)
        model.assert_not_called()

    def test_director_input_is_an_instruction_not_character_dialogue(self):
        self.start(authoring_mode="director")
        with patch.object(vn_scenes, "_call_vn_json", return_value=self.response()) as model:
            scene, _ = vn_scenes.step_scene(self.user, "DIRECTOR_COMMAND Make Mira leave the room.")
        command = next(b for b in scene["beats"] if b.get("kind") == "direction")
        self.assertEqual(command["speaker_slug"], "director")
        self.assertIn("not spoken dialogue", model.call_args.args[1])
        with patch.object(messenger, "ask_json") as repair:
            updated = vn_history.edit(self.user, command["id"], "Have Mira stay instead.")
        repair.assert_not_called()
        self.assertEqual(updated["beats"][-1]["kind"], "direction")
        with patch.object(vn_scenes, "_call_vn_json", return_value={"summary": "They met."}) as summary:
            vn_scenes.finish_scene_with_cg(self.user, capture_image=False)
        self.assertNotIn("Have Mira stay instead", summary.call_args.args[1])
