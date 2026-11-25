import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from mainapp import messenger, vn_casting, vn_scenes
from mainapp.models import Character, EpisodeLook, EpisodePlace


class CastingTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.user = get_user_model().objects.create_user(username="casting", persona_name="Rowan")
        self.mira = Character.objects.create(author=self.user, name="Mira", slug="cast-mira", description="Archivist.")
        self.ivo = Character.objects.create(author=self.user, name="Ivo", slug="cast-ivo", description="Courier.")
        self.thread = messenger.create_thread(self.user, [self.mira, self.ivo])
        data = messenger.thread_data(self.thread)
        data.update(memory="Mira promised to show Rowan the sealed map room.",
                    scene={"Mira": {"where": "archive", "doing": "closing up", "around": "", "wearing": "grey cardigan, black jeans"}},
                    places={"the archive": "tall oak shelves, green reading lamps, a brass map cabinet"})
        messenger.save_thread_data(self.thread, data)
        self.look = EpisodeLook.objects.create(author=self.user, character=self.mira, setting="canon", name="Work",
                                               outfit="grey cardigan, black jeans", moods={"neutral": {"raw": "a.png", "cut": ""}})
        stranger = get_user_model().objects.create_user(username="stranger")
        self.foreign = EpisodeLook.objects.create(author=stranger, character=self.mira, setting="canon", name="Theirs",
                                                  moods={"neutral": {"raw": "b.png", "cut": ""}})
        self.client.force_login(self.user)

    def answer(self, **extra):
        return {"cast": [self.mira.slug, "nobody"],
                "place": {"name": "The archive map room", "background_id": "not-a-backdrop", "time": "Friday, 21:10",
                          "light": "green reading lamps", "weather": "", "details": ["brass map cabinet", "oak table"]},
                "outfits": [{"key": self.mira.slug, "look_id": self.look.pk, "name": "Work", "items": "", "why": "Still at work."},
                            {"key": self.ivo.slug, "look_id": self.foreign.pk, "name": "Courier gear",
                             "items": "navy rain jacket; black cargo trousers; grey trainers", "why": "Came from a delivery."},
                            {"key": "ghost", "look_id": None, "name": "x", "items": "y"}],
                "facts": ["Mira promised Rowan the map room.", "Ivo doesn't know about the promise."],
                "opening": "Mira unlocks the map room while Rowan waits.", "nudge": "The cabinet's lowest drawer sticks.",
                **extra}

    def test_bulba_reads_the_chat_and_the_sheet_keeps_only_what_exists(self):
        with patch.object(messenger, "ask_json", return_value=self.answer()) as bulba:
            sheet = vn_casting.propose(self.user, self.thread, [self.mira, self.ivo], wish="Somewhere quiet")
        prompt = bulba.call_args.args[1]
        for seen in ("sealed map room", "grey cardigan, black jeans", "brass map cabinet", '"name": "Work"', "Somewhere quiet"):
            self.assertIn(seen, prompt)
        self.assertNotIn("Theirs", prompt)
        self.assertEqual(sheet["cast"], [self.mira.slug])
        self.assertEqual(sheet["place"]["background_id"], "")
        self.assertEqual(sheet["outfits"][0]["look_id"], self.look.pk)
        self.assertIsNone(sheet["outfits"][1]["look_id"])  # someone else's look is never offered
        self.assertEqual(sheet["outfits"][1]["items"], "navy rain jacket; black cargo trousers; grey trainers")
        self.assertEqual(len(sheet["outfits"]), 2)

    def test_a_plans_cast_is_the_plans(self):
        with patch.object(messenger, "ask_json", return_value=self.answer(cast=[self.mira.slug])):
            sheet = vn_casting.propose(self.user, self.thread, [self.mira, self.ivo],
                                       pulse_event={"title": "Map room", "participants": [self.ivo.slug]})
        self.assertEqual(sheet["cast"], [self.ivo.slug])

    def test_the_applied_sheet_is_fixed_for_the_episode(self):
        bg = vn_scenes.available_backgrounds([self.mira], self.user)[1]
        casting = {"cast": [self.mira.slug], "facts": ["Ivo doesn't know about the promise."],
                   "place": {"name": "The archive map room", "time": "Friday, 21:10", "light": "green reading lamps",
                             "details": ["brass map cabinet"], "background_id": bg["id"]},
                   "opening": "Mira unlocks the map room.", "nudge": "The lowest drawer sticks."}
        reply = {"title": "Map room", "handoff": "user_turn", "background": "something else",
                 "beats": [{"speaker_slug": self.mira.slug, "text": "It's this way."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply) as model, \
             patch.object(messenger, "make_picture") as image:
            scene = vn_scenes.start_scene(self.user, self.thread, casting=casting, generate_background=True)
        prompt = model.call_args.args[1]
        for fixed in ("CASTING", "brass map cabinet", "Ivo doesn't know", "Mira unlocks the map room", "lowest drawer sticks"):
            self.assertIn(fixed, prompt)
        image.assert_not_called()  # the casting chose a backdrop: nothing is drawn at start
        self.assertEqual(scene["character_slugs"], [self.mira.slug])
        self.assertEqual(scene["beats"][0]["stage"]["background"]["id"], bg["id"])
        self.assertEqual(scene["location"], "The archive map room")
        self.assertEqual(scene["continuity"]["time"], "Friday, 21:10")
        self.assertIn("green reading lamps", scene["continuity"]["location"])
        self.assertEqual(scene["casting"]["facts"], ["Ivo doesn't know about the promise."])

    def test_a_drawn_place_is_kept_and_offered_next_time(self):
        response_body = {"action": "place_draw", "setting": "canon",
                         "place": {"name": "The archive map room", "light": "green lamps", "details": ["brass cabinet"]}}
        with patch.object(messenger, "make_picture", return_value=(b"png", 0.04)) as image:
            response = self.client.post(reverse("vn_scenes_api"), data=json.dumps(response_body), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("brass cabinet", image.call_args.args[1])
        self.assertIn("no people", image.call_args.args[1])
        kept = EpisodePlace.objects.get()
        offered = vn_scenes.available_backgrounds([self.mira], self.user)
        self.assertEqual(offered[0]["id"], f"place_{kept.pk}")
        self.assertTrue(offered[0]["kept"])
        self.client.post(reverse("vn_scenes_api"), data=json.dumps({"action": "place_delete", "place_id": f"place_{kept.pk}"}),
                         content_type="application/json")
        self.assertFalse(EpisodePlace.objects.exists())

    def test_casting_needs_the_chat_and_reports_bulba_failures(self):
        url = reverse("vn_scenes_api")
        self.assertEqual(self.client.post(url, data=json.dumps({"action": "casting_propose"}),
                                          content_type="application/json").status_code, 400)
        from mainapp import ai_client
        with patch.object(messenger, "ask_json", side_effect=ai_client.AIError("Bulba is busy.")):
            response = self.client.post(url, data=json.dumps({"action": "casting_propose", "thread_id": self.thread.pk}),
                                        content_type="application/json")
        self.assertEqual(response.json()["error"], "Bulba is busy.")
        with patch.object(messenger, "ask_json", return_value=self.answer()):
            response = self.client.post(url, data=json.dumps({"action": "casting_propose", "thread_id": self.thread.pk}),
                                        content_type="application/json")
        self.assertEqual(response.json()["casting"]["opening"], "Mira unlocks the map room while Rowan waits.")

    def test_a_place_without_a_backdrop_is_drawn_from_its_card_at_start_and_kept(self):
        casting = {"cast": [self.mira.slug], "place": {"name": "The archive map room", "light": "green lamps",
                                                       "details": ["brass map cabinet"]}}
        reply = {"title": "Map room", "handoff": "user_turn", "beats": [{"speaker_slug": self.mira.slug, "text": "Here."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply), \
             patch.object(messenger, "make_picture", return_value=(b"png", 0.04)) as image:
            scene = vn_scenes.start_scene(self.user, self.thread, casting=casting, generate_background=True)
        self.assertIn("brass map cabinet", image.call_args.args[1])
        kept = EpisodePlace.objects.get()
        self.assertEqual(scene["beats"][0]["stage"]["background"]["id"], f"place_{kept.pk}")

    def test_bulba_says_which_moods_the_episode_needs_and_how_each_person_shows_them(self):
        answer = self.answer()
        answer["outfits"][0].update(moods=["smug", "Guarded", "neutral", "smug", "x" * 3],
                                    mood_notes={"smug": "a thin one-sided smile", "ghost": "nope"})
        with patch.object(messenger, "ask_json", return_value=answer) as bulba:
            sheet = vn_casting.propose(self.user, self.thread, [self.mira, self.ivo])
        self.assertIn("Moods fit the person and this episode", bulba.call_args.args[1])
        mira = sheet["outfits"][0]
        self.assertEqual(mira["moods"], ["smug", "guarded", "xxx"])
        self.assertEqual(mira["mood_notes"], {"smug": "a thin one-sided smile"})

    def test_casting_notes_reach_the_look_and_bulba_writes_only_the_rest(self):
        from mainapp import episode_looks
        with patch.object(episode_looks, "references", return_value=[(b"ref", "image/png")]), \
             patch.object(messenger, "ask_json", return_value={"notes": {"tired": "heavy eyelids"}}) as bulba, \
             patch.object(messenger, "make_picture", return_value=(b"img", 0)) as image:
            look, _, _ = episode_looks.create(self.user, self.mira, "canon", "Night", "coat", moods=["neutral", "smug", "tired"],
                                              mood_notes={"smug": "a thin one-sided smile"})
        self.assertEqual(sorted(look.moods), ["neutral", "smug", "tired"])
        self.assertIn("Moods: tired", bulba.call_args.args[1])  # smug was already described
        self.assertIn("a thin one-sided smile", image.call_args_list[1].args[1])
        with patch.object(messenger, "make_picture", return_value=(b"img", 0)), \
             patch.object(messenger, "ask_json", return_value={"notes": {}}):
            r = self.client.post(reverse("vn_scenes_api"), data=json.dumps({
                "action": "episode_look_moods", "look_id": look.pk, "moods": ["guarded"],
                "mood_notes": {"guarded": "chin up, eyes steady"}}), content_type="application/json")
        self.assertEqual(r.json()["look"]["mood_notes"]["guarded"], "chin up, eyes steady")
        self.assertIn("guarded", r.json()["look"]["moods"])
