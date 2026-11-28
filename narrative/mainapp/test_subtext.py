import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from mainapp import messenger, subtext
from mainapp.models import Character


class SubtextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="poster", persona_name="Rowan")
        self.mira = Character.objects.create(author=self.user, name="Mira", slug="st-mira", description="Archivist.")
        self.ivo = Character.objects.create(author=self.user, name="Ivo", slug="st-ivo", description="Courier.")
        self.kade = Character.objects.create(author=self.user, name="Kade", slug="st-kade", description="Smuggler.")
        self.client.force_login(self.user)

    def api(self, **body):
        return self.client.post(reverse("subtext_api"), data=json.dumps(body), content_type="application/json")

    def wave(self, answer, **body):
        with patch.object(messenger, "ask_json", return_value=answer) as model:
            r = self.api(action="generate_wave", **body)
        return r, model

    def test_a_burner_is_seen_only_by_its_followers_and_who_knows(self):
        self.api(action="set_followers", owner=self.mira.slug, followers=[self.ivo.slug, "nobody"])
        answer = {"posts": [{"author": self.mira.slug, "account": "burner", "text": "Mira: Some people never return keys.",
                             "replies": [{"author": self.ivo.slug, "text": "Ouch."},
                                         {"author": self.kade.slug, "text": "Who?"}]}]}  # Kade can't see it
        r, model = self.wave(answer, character_slugs=[self.mira.slug, self.ivo.slug, self.kade.slug])
        post = r.json()["subtext"]["posts"][0]
        self.assertEqual(post["text"], "Some people never return keys.")  # no "Mira:" label
        self.assertEqual([c["author"] for c in post["comments"]], [self.ivo.slug])
        self.assertEqual(sorted(post["seen_by"]), sorted([self.mira.slug, self.ivo.slug]))
        self.assertFalse(post["you_see"])
        self.assertIn("start each beat on the action itself", model.call_args.args[1])  # the writing steer
        block = subtext.seen_block(self.user, [self.kade])
        self.assertEqual(block, "")  # Kade has seen nothing
        r = self.api(action="set_knows", post_id=post["id"], key=self.kade.slug, how="Ivo showed him")
        self.assertIn(self.kade.slug, r.json()["subtext"]["posts"][0]["seen_by"])
        self.assertIn("Some people never return keys", subtext.seen_block(self.user, [self.kade]))

    def test_an_aita_author_is_anonymous_until_someone_knows(self):
        answer = {"posts": [{"author": self.ivo.slug, "account": "aita", "title": "AITA for keeping the parcel?",
                             "text": "It was addressed to nobody.", "replies": [{"author": self.mira.slug, "verdict": "yta", "text": "Yes."}]}]}
        r, _ = self.wave(answer, character_slugs=[self.ivo.slug, self.mira.slug])
        post = r.json()["subtext"]["posts"][0]
        self.assertEqual(post["votes"]["yta"], 1)
        self.assertNotIn("only Mira know", subtext.seen_block(self.user, [self.mira, self.ivo]))
        self.api(action="set_knows", post_id=post["id"], key=self.mira.slug)
        self.assertIn("only Mira, Ivo know that", subtext.seen_block(self.user, [self.mira, self.ivo]))

    def test_you_post_reply_react_vote_and_cant_reply_to_what_you_cant_see(self):
        with patch.object(messenger, "ask_json", return_value={"replies": [{"author": self.mira.slug, "text": "Bold."}]}):
            r = self.api(action="create_post", text="Back at the archive.", account="main")
        post = r.json()["subtext"]["posts"][0]
        self.assertEqual([c["text"] for c in post["comments"]], ["Bold."])
        r = self.api(action="react_post", post_id=post["id"], emoji="🔥")
        self.assertEqual(r.json()["subtext"]["posts"][0]["reactions"], {"🔥": ["user"]})
        state = subtext.load(self.user)
        state["posts"].insert(0, subtext._new_post(self.mira.slug, "burner", "", "Locked thoughts."))
        subtext.save(self.user, state)
        locked = subtext.load(self.user)["posts"][0]["id"]
        self.assertEqual(self.api(action="add_comment", post_id=locked, text="Hi").status_code, 400)
        self.api(action="set_followers", owner=self.mira.slug, followers=["user"])
        self.assertEqual(self.api(action="add_comment", post_id=locked, text="Hi", ask_replies=False).status_code, 200)

    def test_sending_a_post_to_a_dm_lets_them_know(self):
        state = subtext.load(self.user)
        state["posts"].insert(0, subtext._new_post(self.mira.slug, "burner", "", "Locked thoughts."))
        subtext.save(self.user, state)
        pid = state["posts"][0]["id"]
        with patch.object(messenger, "generate_turn", return_value={"bubbles": []}) as turn:
            r = self.api(action="forward_to_telechat", post_id=pid, char_slug=self.ivo.slug, comment="Look.")
        self.assertEqual(r.status_code, 200)
        self.assertIn(self.ivo.slug, r.json()["subtext"]["posts"][0]["seen_by"])
        self.assertIn("You hadn't seen it before", turn.call_args.kwargs["extra_instruction"])

    def test_old_posts_still_read(self):
        from mainapp.models import ChatSettings
        obj, _ = ChatSettings.objects.get_or_create(author=self.user)
        obj.appearance = {"subtext": {"posts": [{"id": "st_old", "author_slug": self.mira.slug, "visibility": "public",
                                                 "text": "Old.", "aita_votes": {"nta": 1}, "comments": [
                                                     {"author_slug": self.ivo.slug, "is_burner": True, "text": "x"}]}]}}
        obj.save()
        post = self.client.get(reverse("subtext_api")).json()["subtext"]["posts"][0]
        self.assertEqual((post["author"], post["account"], post["votes"]["nta"]), (self.mira.slug, "main", 1))
        self.assertEqual(post["comments"][0]["account"], "burner")

    def test_statuses_show_in_the_feed(self):
        messenger.save_char_profile(self.mira, {"stories": [{"id": "s1", "text": "Closed early.", "ts": 1}]})
        data = self.client.get(reverse("subtext_api")).json()["subtext"]
        self.assertEqual(data["statuses"][0]["text"], "Closed early.")
