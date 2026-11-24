"""
👥 Screen group chats and texting details: one speaker per bubble, replies left on read, edits, stickers.
"""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from mainapp import messenger
from mainapp.models import Character, MessengerThread


class GroupTextingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="grouper", password="pw12345!")
        self.client.force_login(self.user)
        self.pan = Character.objects.create(name="Pantalone", slug="pan-g", author=self.user, initial_message="Hm.")
        self.dot = Character.objects.create(name="Il Dottore", slug="dot-g", author=self.user, initial_message="Yes?")
        self.thread = messenger.create_thread(self.user, [self.pan, self.dot])

    def senders(self, parsed):
        bubbles = parsed["bubbles"] if isinstance(parsed, dict) else parsed
        return [(b.get("sender_name"), b.get("text")) for b in bubbles]

    def test_a_line_for_someone_else_becomes_their_own_bubble(self):
        raw = ("Pantalone: There is, admittedly, a chair in my office with better company than a centrifuge.\n\n"
               "Il Dottore: I do itemise. It is one of my few pleasures.")
        out = self.senders(messenger.parse_ai_reply(raw, [self.pan, self.dot], is_group=True))
        self.assertEqual([s for s, _ in out], ["Pantalone", "Il Dottore"])
        self.assertTrue(out[1][1].startswith("I do itemise"))

    def test_a_reply_left_on_read_waits_even_when_the_model_forgets_the_tag(self):
        data = dict(self.thread.data or {})
        data["leave_on_read"] = True
        self.thread.data = data
        self.thread.save()
        with mock.patch("mainapp.ai_client.resolve", return_value=(None, "test/model")), \
             mock.patch("mainapp.ai_client.complete", return_value="Pantalone: later, my dear.") as complete, \
             mock.patch("mainapp.messenger.LEAVE_ON_READ_CHANCE", 1.0):
            out = messenger.generate_turn(self.user, self.thread)
        self.assertIn("THIS REPLY COMES LATER", json.dumps(complete.call_args.args[2]))
        self.thread.refresh_from_db()
        waiting = messenger.waiting_reply(messenger.thread_data(self.thread))
        self.assertTrue(waiting or out.get("later"), out)

    def test_an_edit_before_anyone_answered_hides_the_first_version(self):
        data = messenger.thread_data(self.thread)
        data["messages"] = [{"id": "u1", "role": "user", "text": "I hate it", "time": "10:00", "ts": 1}]
        self.thread.data = {**(self.thread.data or {}), "messages": data["messages"]}
        self.thread.save()
        url = reverse("messenger_api")
        self.client.post(url, json.dumps({"action": "edit_message", "thread_id": self.thread.id, "message_id": "u1",
                                          "text": "I love it"}), content_type="application/json")
        self.thread.refresh_from_db()
        msg = messenger.thread_data(self.thread)["messages"][0]
        self.assertEqual(msg["text"], "I love it")
        self.assertNotIn("edited_from", msg)  # nobody had read it yet
        # once someone answered, an edit is noticed (they read the first version)
        self.thread.data = {**self.thread.data, "messages": [
            {"id": "u1", "role": "user", "text": "I love it", "time": "10:00", "ts": 1},
            {"id": "a1", "role": "assistant", "sender_name": "Pantalone", "text": "Do you.", "time": "10:01", "ts": 2}]}
        self.thread.save()
        self.client.post(url, json.dumps({"action": "edit_message", "thread_id": self.thread.id, "message_id": "u1",
                                          "text": "I adore it"}), content_type="application/json")
        self.thread.refresh_from_db()
        self.assertEqual(messenger.thread_data(self.thread)["messages"][0].get("edited_from"), "I love it")

    def test_characters_see_what_a_sticker_shows(self):
        with mock.patch("mainapp.messenger.see_photo", return_value="a potato rolling its eyes") as look:
            st = messenger.see_sticker(self.user, {"name": "Bulba Judging", "emoji": "🥔😒", "url": "/media/st/judge.png"})
            again = messenger.see_sticker(self.user, {"name": "Bulba Judging", "url": "/media/st/judge.png"})
        self.assertEqual(st["seen"], "a potato rolling its eyes")
        self.assertEqual(again["seen"], "a potato rolling its eyes")
        self.assertEqual(look.call_count, 1)  # looked at once
        self.thread.data = {**(self.thread.data or {}), "messages": [
            {"id": "u1", "role": "user", "text": "", "sticker": st, "time": "10:00", "ts": 1}]}
        self.thread.save()
        with mock.patch("mainapp.ai_client.resolve", return_value=(None, "test/model")):
            prompt = json.dumps(messenger.build_messenger_prompt(self.user, self.thread), ensure_ascii=False)
        self.assertIn("It shows: a potato rolling its eyes", prompt)

    def test_conversation_is_the_default_and_lively_can_be_picked(self):
        with mock.patch("mainapp.ai_client.resolve", return_value=(None, "test/model")):
            prompt = json.dumps(messenger.build_messenger_prompt(self.user, self.thread))
        self.assertIn("CONVERSATION:", prompt)
        self.assertIn("ONE PERSON PER BUBBLE", prompt)
        self.client.post(reverse("messenger_api"), json.dumps({"action": "thread_settings", "thread_id": self.thread.id,
                                                               "group_mode": "lively"}), content_type="application/json")
        self.thread.refresh_from_db()
        self.assertEqual(messenger.thread_data(self.thread)["group_mode"], "lively")
        with mock.patch("mainapp.ai_client.resolve", return_value=(None, "test/model")):
            prompt = json.dumps(messenger.build_messenger_prompt(self.user, self.thread))
        self.assertIn("LIVELY:", prompt)

    def test_a_group_shows_its_members_until_it_has_its_own_picture(self):
        with mock.patch("mainapp.messenger.char_avatar", side_effect=lambda c: f"/media/{c.slug}.png"):
            summary = messenger.serialize_thread_summary(self.thread)
        self.assertEqual(summary["avatar_url"], "")
        self.assertEqual(sorted(summary["avatar_urls"]), ["/media/dot-g.png", "/media/pan-g.png"])
        with mock.patch("mainapp.messenger.make_picture", return_value=(b"\x89PNG fake", 0)), \
             mock.patch("mainapp.messenger.load_character_references", return_value=[]):
            out = self.client.post(reverse("messenger_api"), json.dumps(
                {"action": "group_avatar", "thread_id": self.thread.id, "what": "at a casino table"}),
                content_type="application/json").json()
        self.assertIn("messenger/avatars/group-", out["thread"]["avatar_url"])
        out = self.client.post(reverse("messenger_api"), json.dumps(
            {"action": "group_avatar", "thread_id": self.thread.id, "clear": True}), content_type="application/json").json()
        self.assertEqual(out["thread"]["avatar_url"], "")

    def test_a_member_can_change_the_group_picture(self):
        parsed = messenger.parse_ai_reply("Pantalone: there. [GROUP_AVATAR: the two of us at a casino table]",
                                          [self.pan, self.dot], is_group=True)
        self.assertEqual([u["kind"] for u in parsed["profile_updates"]], ["group_avatar"])

    def test_a_reply_that_was_all_thinking_is_tried_again_without_thinking(self):
        answers = ["<think>Pantalone wants... wait, let me reconsider...</think>", "Pantalone: Fine. Ten minutes."]
        with mock.patch("mainapp.ai_client.resolve", return_value=(None, "xiaomi/mimo-v2.6-pro")), \
             mock.patch("mainapp.ai_client.complete", side_effect=answers) as complete:
            out = messenger.generate_turn(self.user, self.thread)
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(complete.call_args_list[1].kwargs.get("reasoning"), {"enabled": False})
        self.assertIn("Ten minutes", json.dumps(out.get("bubbles") or [], ensure_ascii=False))
