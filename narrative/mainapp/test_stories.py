import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from mainapp import messenger, stories, vn_casting, vn_scenes
from mainapp.models import Character, Story

SETUP = {
    "title": "The Salt Archive", "premise": "Rowan takes a job at a flooded archive.", "tone": "quiet mystery",
    "world": ["The archive floods at every spring tide.", "Lamps run on whale oil."],
    "side_characters": [{"name": "Oren Vale", "role": "the archive's keeper", "personality": "Dry, patient, hides a debt.",
                         "appearance": "sixties, tall, white beard, navy wool coat", "speech": "short sentences"},
                        {"name": ""}],
    "relations": ["Mira: wary of Rowan"], "threads": ["Who sealed the lower vault?"],
    "arc": {"chapters": [{"title": "Low tide", "goal": "Rowan learns the archive's rules",
                          "beats": ["Oren hands over the keys", "The vault door is found open"], "ends_when": "the vault opens"},
                         {"title": "High water", "goal": "The flood traps them", "beats": ["The stairs flood"], "ends_when": "they escape"}],
            "ending": "Rowan decides whether to keep Oren's secret"},
    "opening": "Rowan arrives at the archive at dusk.",
}


class StoryTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.user = get_user_model().objects.create_user(username="teller", persona_name="Rowan")
        self.mira = Character.objects.create(author=self.user, name="Mira", slug="story-mira-cast", description="Archivist.")
        self.client.force_login(self.user)

    def api(self, **body):
        return self.client.post(reverse("vn_scenes_api"), data=json.dumps(body), content_type="application/json")

    def make(self, persona=None):
        return stories.create(self.user, SETUP, [self.mira], persona=persona)

    def test_bulba_proposes_and_the_setup_is_trimmed(self):
        with patch.object(messenger, "ask_json", return_value=SETUP) as bulba:
            r = self.api(action="story_propose", wishes="a flooded library", cast=[self.mira.slug, "nobody"], setting="original")
        setup = r.json()["setup"]
        self.assertIn("a flooded library", bulba.call_args.args[1])
        self.assertIn("Archivist.", bulba.call_args.args[1])
        self.assertEqual([s["name"] for s in setup["side_characters"]], ["Oren Vale"])
        self.assertEqual(setup["arc"]["at"], {"chapter": 0, "beat": 0})

    def test_side_characters_belong_to_the_story_and_stay_off_the_phone(self):
        story = self.make()
        oren = Character.objects.get(side_story=story)
        self.assertEqual(oren.name, "Oren Vale")
        self.assertIn(oren, story.cast.all())
        self.assertIn("navy wool coat", messenger.char_profile(oren)["appearance_notes"])
        from mainapp.views import _user_characters
        self.assertNotIn(oren, list(_user_characters(self.user)))
        stories.delete(story)
        self.assertFalse(Character.objects.filter(pk=oren.pk).exists())

    def test_the_arc_is_hidden_until_asked_for(self):
        story = self.make()
        data = self.api(action="story_get", story_id=story.pk).json()["story"]
        self.assertNotIn("arc", data)
        self.assertNotIn("Oren hands over", json.dumps(data))
        data = self.api(action="story_show_arc", story_id=story.pk, show=True).json()["story"]
        self.assertEqual(data["arc"]["chapters"][0]["title"], "Low tide")

    def test_a_story_persona_or_the_usual_one(self):
        self.assertEqual(stories.scene_context(self.user, self.make())["user_name"], "Rowan")
        own = self.make(persona={"mode": "story", "name": "Wren", "description": "A diver."})
        ctx = stories.scene_context(self.user, own)
        self.assertEqual((ctx["user_name"], ctx["persona"]), ("Wren", "A diver."))
        self.assertIn("whale oil", ctx["scenario"])

    def test_scenes_are_steered_quietly_and_kept_with_the_bible_updated(self):
        story = self.make()
        reply = {"title": "Arrival", "handoff": "user_turn", "location": "The archive steps",
                 "beats": [{"speaker_slug": self.mira.slug, "text": "You're late."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply) as model:
            scene = vn_scenes.start_scene(self.user, characters=list(story.cast.all()), story=story)
        prompt = model.call_args.args[1]
        self.assertIn("Oren hands over the keys", prompt)  # the storyteller is steered...
        self.assertIn("never announce it", prompt)
        self.assertNotIn("Oren hands over", scene.get("direction", ""))  # ...but the direction the user sees stays theirs
        self.assertNotIn("Oren hands over", json.dumps(scene))
        self.assertEqual(scene["story_id"], story.pk)
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply) as model:
            vn_scenes.step_scene(self.user, user_input="Sorry.")
        self.assertIn("Oren hands over the keys", model.call_args.args[1])
        keeper = {"summary": "Rowan met Mira at the steps.", "world": ["The archive floods at every spring tide.", "Mira keeps a spare key."],
                  "relations": ["Mira: annoyed but curious"], "threads": ["Who sealed the lower vault?"],
                  "timeline": "Day 1, dusk: Rowan arrives.", "last": {"place": "the steps", "time": "Day 1, 19:00",
                                                                        "present": ["Mira"], "outfits": {"Mira": "grey coat"}},
                  "arc": {"beats_reached": 2, "chapter_done": True}, "chapter_card": "Rowan is in."}
        with patch.object(vn_scenes, "_call_vn_json", return_value={}), \
             patch.object(messenger, "ask_json", return_value=keeper):
            entry, _ = vn_scenes.finish_scene_with_cg(self.user, capture_image=False)
        story.refresh_from_db()
        kept = story.scenes.get()
        self.assertEqual((kept.number, kept.chapter, kept.summary), (1, 1, "Rowan met Mira at the steps."))
        self.assertEqual(kept.chapter_card["title"], "Low tide")
        self.assertEqual(story.arc["at"], {"chapter": 1, "beat": 0})
        self.assertIn("Mira keeps a spare key.", story.bible["world"])
        self.assertEqual(story.bible["last"]["outfits"], {"Mira": "grey coat"})
        self.assertEqual(entry["story"]["scene"], 1)
        self.assertIn("High water", stories.secret_direction(story))

    def test_the_next_scenes_casting_reads_the_story_not_a_phone(self):
        story = self.make()
        story.bible = {**story.bible, "last": {"place": "the steps", "time": "Day 1, 19:00", "present": ["Mira"],
                                               "outfits": {"Mira": "grey coat"}}, "timeline": ["Day 1: Rowan arrives."]}
        story.save()
        story.scenes.create(number=1, chapter=1, title="Arrival", place="the steps", summary="They met.")
        answer = {"cast": [self.mira.slug], "place": {"name": "Reading room"}, "outfits": [], "facts": [], "opening": "x"}
        with patch.object(messenger, "ask_json", return_value=answer) as bulba:
            r = self.api(action="casting_propose", story_id=story.pk)
        self.assertEqual(r.status_code, 200)
        prompt = bulba.call_args.args[1]
        for seen in ("NEXT SCENE", "The Salt Archive", "the steps", "Day 1: Rowan arrives.", "grey coat", "They met."):
            self.assertIn(seen, prompt)
        self.assertNotIn("Oren hands over", prompt)  # the casting sheet is shown: no plan in it

    def test_only_your_own_stories(self):
        story = self.make()
        self.client.force_login(get_user_model().objects.create_user(username="other"))
        self.assertEqual(self.api(action="story_get", story_id=story.pk).status_code, 400)
        self.assertEqual(self.api(action="story_list").json()["stories"], [])

    def test_side_characters_get_looks_through_their_story(self):
        story = self.make()
        oren = Character.objects.get(side_story=story)
        r = self.api(action="episode_looks", character_slugs=[oren.slug])
        self.assertEqual([p["key"] for p in r.json()["cast"]], ["user"])  # not reachable without the story
        r = self.api(action="episode_looks", story_id=story.pk, character_slugs=[oren.slug, self.mira.slug])
        self.assertEqual([p["key"] for p in r.json()["cast"]], [oren.slug, self.mira.slug, "user"])
        self.assertFalse(r.json()["cast"][0]["has_reference"])  # drawn from words

    def test_finishing_a_reopened_scene_again_rewrites_it(self):
        story = self.make()
        scene = {"id": "vns_once", "story_id": story.pk, "title": "Arrival", "location": "steps",
                 "beats": [{"speaker_name": "Mira", "text": "Late."}]}
        keeper = {"summary": "First.", "arc": {"beats_reached": 2, "chapter_done": True}, "chapter_card": "Done."}
        with patch.object(messenger, "ask_json", return_value=keeper):
            stories.record_scene(self.user, scene, {"summary": "x"})
            stories.record_scene(self.user, {**scene, "title": "Arrival, again"}, {"summary": "y"})
        story.refresh_from_db()
        self.assertEqual([(s.number, s.title) for s in story.scenes.all()], [(1, "Arrival, again")])
        self.assertEqual(story.arc["at"]["chapter"], 1)  # the chapter closed once, not twice

    def test_episode_turns_get_the_writing_steer(self):
        story = self.make()
        reply = {"title": "Arrival", "handoff": "user_turn", "beats": [{"speaker_slug": self.mira.slug, "text": "Late."}]}
        with patch.object(vn_scenes, "_call_vn_json", return_value=reply) as model:
            vn_scenes.start_scene(self.user, characters=list(story.cast.all()), story=story)
            vn_scenes.step_scene(self.user, user_input="Sorry.")
        for call in model.call_args_list:
            self.assertIn("start each beat on the action itself", call.args[1])  # "She doesn't step back..." steered out
