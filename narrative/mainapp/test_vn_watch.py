import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from mainapp import messenger, vn_history, vn_scenes, vn_watch
from mainapp.models import Character, EpisodeLook


class EpisodeWatchTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.user = get_user_model().objects.create_user(username="watcher", persona_name="Rowan")
        self.mira = Character.objects.create(author=self.user, name="Mira", slug="watch-mira")
        self.ivo = Character.objects.create(author=self.user, name="Ivo", slug="watch-ivo")
        self.thread = messenger.create_thread(self.user, [self.mira, self.ivo])
        EpisodeLook.objects.create(author=self.user, character=self.mira, setting="canon", name="Work",
                                   outfit="grey cardigan, black jeans", moods={"neutral": {"raw": "a.png", "cut": ""}})
        self.casting = {"cast": [self.mira.slug, self.ivo.slug], "facts": ["Ivo does not know about the promise."],
                        "place": {"name": "The map room", "details": ["brass cabinet"]}}
        reply = {"title": "Map room", "handoff": "user_turn",
                 "beats": [{"speaker_slug": self.mira.slug, "text": "It's this way."}],
                 "continuity": {"summary": "They went to the map room."}}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply):
            vn_scenes.start_scene(self.user, self.thread, casting=self.casting)
        self.client.force_login(self.user)

    def step(self):
        turn = {"handoff": "user_turn", "continuity": {"summary": "Ivo knows about the promise now."},
                "beats": [{"speaker_slug": self.mira.slug, "text": "The cabinet sticks."},
                          {"speaker_slug": self.ivo.slug, "text": "Is this the room you promised Rowan? Mira told me everything."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=turn):
            return vn_scenes.step_scene(self.user, "I open the cabinet.")

    def test_every_turn_carries_the_casting_sheet_not_only_the_opening(self):
        turn = {"handoff": "user_turn", "beats": [{"speaker_slug": self.mira.slug, "text": "Here."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=turn) as model:
            vn_scenes.step_scene(self.user, "I follow.")
        prompt = model.call_args.args[1]
        self.assertIn("Ivo does not know about the promise.", prompt)
        self.assertIn("The map room", prompt)

    def test_bulba_checks_the_turn_against_what_was_established_before_it(self):
        scene, new = self.step()
        answer = {"slips": [{"passage": "p2", "what": "Ivo knows about the promise.", "fact": "Ivo does not know.",
                             "fix": "Is this the room? Mira wouldn't say why we're here."},
                            {"passage": "p9", "what": "Not a passage."}]}
        with patch.object(messenger, "ask_json", return_value=answer) as bulba:
            scene, slips = vn_watch.run(self.user)
        prompt = bulba.call_args.args[1]
        self.assertIn("Ivo does not know about the promise.", prompt)
        self.assertIn("grey cardigan, black jeans", prompt)
        self.assertIn("They went to the map room.", prompt)
        self.assertNotIn("Ivo knows about the promise now.", prompt)  # the turn's own record isn't the standard
        self.assertIn("[p2] Ivo:", prompt)
        self.assertEqual(len(slips), 1)
        self.assertEqual(slips[0]["beat_id"], new[1]["id"])
        self.assertEqual(scene["watch"]["slips"][0]["fix"], "Is this the room? Mira wouldn't say why we're here.")

    def test_bulbas_fix_is_a_passage_edit_and_regenerating_names_the_slip(self):
        scene, new = self.step()
        with patch.object(messenger, "ask_json", return_value={"stage": {}}):
            edited = vn_history.edit(self.user, new[1]["id"], "Is this the room? Mira wouldn't say why we're here.")
        self.assertEqual(edited["beats"][-1]["text"], "Is this the room? Mira wouldn't say why we're here.")
        scene, new = self.step()
        with patch.object(vn_scenes, "_call_vn_json", return_value={"handoff": "user_turn", "beats": [
                {"speaker_slug": self.ivo.slug, "text": "Why are we here?"}]}) as model:
            response = self.client.post(reverse("vn_scenes_api"), data=json.dumps({
                "action": "regenerate_passage", "beat_id": new[1]["id"],
                "direction": "Fix this continuity slip: Ivo knows about the promise."}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Fix this continuity slip", model.call_args.args[1])

    def test_ignoring_a_slip_removes_it_and_a_new_turn_clears_old_ones(self):
        self.step()
        with patch.object(messenger, "ask_json", return_value={"slips": [{"passage": "p2", "what": "Ivo knows."}]}):
            response = self.client.post(reverse("vn_scenes_api"), data=json.dumps({"action": "episode_watch"}),
                                        content_type="application/json")
        slip = response.json()["vn_scenes"]["active_scene"]["watch"]["slips"][0]
        response = self.client.post(reverse("vn_scenes_api"), data=json.dumps({"action": "watch_dismiss", "beat_id": slip["beat_id"]}),
                                    content_type="application/json")
        self.assertEqual(response.json()["vn_scenes"]["active_scene"]["watch"]["slips"], [])
        with patch.object(messenger, "ask_json", return_value={"slips": [{"passage": "p1", "what": "x"}]}):
            vn_watch.run(self.user)
        scene, _ = self.step()
        self.assertNotIn("watch", scene)

    def test_a_clean_turn_has_no_slips(self):
        self.step()
        with patch.object(messenger, "ask_json", return_value={"slips": []}):
            _, slips = vn_watch.run(self.user)
        self.assertEqual(slips, [])


class PresenceTests(EpisodeWatchTests):
    def test_leaving_and_arriving_change_who_is_on_stage_from_that_passage(self):
        turn = {"handoff": "user_turn", "beats": [
            {"speaker_slug": self.ivo.slug, "text": "I'll leave you two to it.", "stage": {"leave": [self.ivo.slug, "ghost"]}},
            {"speaker_slug": "narrator", "text": "The door closes behind him."},
            {"speaker_slug": "narrator", "text": "Ivo comes back with tea.", "stage": {"enter": [self.ivo.slug]}}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=turn):
            scene, new = vn_scenes.step_scene(self.user, "I wave him off.")
        goodbye, door, back = new
        self.assertIn(self.ivo.slug, goodbye["stage"]["present"])  # he says it, then goes
        self.assertEqual(goodbye["left"], [self.ivo.slug])
        self.assertNotIn(self.ivo.slug, door["stage"]["present"])
        self.assertIn(self.ivo.slug, back["stage"]["present"])
        with patch.object(vn_scenes, "_call_vn_json", return_value={"handoff": "user_turn", "beats": [
                {"speaker_slug": self.mira.slug, "text": "Thanks.", "stage": {"leave": [self.ivo.slug]}}]}):
            scene, _ = vn_scenes.step_scene(self.user, "I take a cup.")
        with patch.object(vn_scenes, "_call_vn_json", return_value={"handoff": "user_turn", "beats": [
                {"speaker_slug": self.ivo.slug, "text": "Me again."}]}) as model:
            scene, new = vn_scenes.step_scene(self.user, "I wait.")
        self.assertIn("GONE (not here until an \"enter\"): Ivo", model.call_args.args[1])
        self.assertTrue(new[0]["auto_entered"])  # he spoke without arriving: on stage, and the Watch is told
        with patch.object(messenger, "ask_json", return_value={"slips": []}) as bulba:
            vn_watch.run(self.user)
        self.assertIn("Gone when the turn began", bulba.call_args.args[1])
        self.assertIn("speaks in this turn without an arrival", bulba.call_args.args[1])


class PhoneHandoffTests(EpisodeWatchTests):
    def test_a_finished_episode_leaves_a_card_and_updates_right_now(self):
        with patch.object(vn_scenes, "_call_vn_json", return_value={"handoff": "user_turn", "beats": [
                {"speaker_slug": "narrator", "text": "Rain soaks Mira's cardigan.",
                 "stage": {"outfit_change": {self.mira.slug: "grey cardigan, soaked"}}},
                {"speaker_slug": self.ivo.slug, "text": "I'm off.", "stage": {"leave": [self.ivo.slug]}}]}):
            vn_scenes.step_scene(self.user, "Bye, Ivo.")
        with patch.object(vn_scenes, "_call_vn_json", return_value={"chat_summary": "They found the map.", "visual_prompt": "x"}):
            vn_scenes.finish_scene_with_cg(self.user, capture_image=False)
        self.thread.refresh_from_db()
        data = messenger.thread_data(self.thread)
        card = [m for m in data["messages"] if m.get("episode")][-1]
        self.assertEqual(card["episode"]["title"], "Map room")
        self.assertEqual(card["episode"]["summary"], "They found the map.")
        self.assertEqual(data["scene"]["Mira"]["where"], "The map room")
        self.assertEqual(data["scene"]["Mira"]["wearing"], "grey cardigan, soaked")
        self.assertNotEqual(data["scene"]["Ivo"]["where"], "The map room")  # he had left


class CostTests(EpisodeWatchTests):
    def test_the_episode_counts_its_cost_from_casting_on(self):
        from users.models import UsageRecord
        vn_scenes.save_vn_state(self.user, {"active_scene": None})
        UsageRecord.objects.create(user=self.user, task="chat", cost=5.0)  # before casting: not this episode's
        import time
        vn_scenes.mark_prep(self.user)
        since = vn_scenes.get_vn_state(self.user)["prep_since"]
        UsageRecord.objects.create(user=self.user, task="sprites", cost=0.04)
        UsageRecord.objects.create(user=self.user, task="bulba", cost=0.01)
        reply = {"title": "T", "handoff": "user_turn", "beats": [{"speaker_slug": self.mira.slug, "text": "Hi."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply):
            scene = vn_scenes.start_scene(self.user, self.thread)
        self.assertEqual(scene["cost_since"], since)
        self.assertIsNone(vn_scenes.get_vn_state(self.user)["prep_since"])
        UsageRecord.objects.create(user=self.user, task="chat", cost=0.02)
        cost = vn_scenes.episode_cost(self.user, scene["cost_since"])
        self.assertEqual(cost, {"total": 0.07, "pictures": 1, "picture_cost": 0.04, "text_cost": 0.03})
        payload = self.client.get(reverse("vn_scenes_api")).json()["vn_scenes"]
        self.assertEqual(payload["cost"]["total"], 0.07)
