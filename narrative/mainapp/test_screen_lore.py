import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from mainapp import lorebook, messenger, screen_lore
from mainapp.models import Character, Worldbook


class ChatLoreTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable(); self.addCleanup(settings.disable)
        self.user = get_user_model().objects.create_user(username="lore-owner")
        self.other = get_user_model().objects.create_user(username="other-owner")
        self.char = Character.objects.create(author=self.user, name="Mira", slug="lore-mira")
        self.thread = messenger.create_thread(self.user, [self.char])
        self.second = messenger.create_thread(self.user, [self.char])
        self.client.force_login(self.user)
        self.book = lorebook.normalize_book({"title": "Archive", "entries": [
            {"keys": ["brass"], "content": "The brass key opens Gate Nine."},
            {"keys": ["secret"], "content": "Disabled secret.", "enabled": False}]})

    def post(self, action, **data):
        return self.client.post(reverse("screen_lore_api"),
            data=json.dumps({"action": action, "thread_id": self.thread.pk, **data}), content_type="application/json")

    def test_local_lore_is_isolated_and_preserved_by_normal_message_saves(self):
        self.assertEqual(self.post("save", book=self.book).status_code, 200)
        self.thread.refresh_from_db()
        data = messenger.thread_data(self.thread)
        data["messages"].append({"role": "user", "text": "Where is the brass key?"})
        messenger.save_thread_data(self.thread, data)
        prompt = json.dumps(messenger.build_messenger_prompt(self.user, self.thread))
        other_prompt = json.dumps(messenger.build_messenger_prompt(self.user, self.second))
        self.assertIn("opens Gate Nine", prompt)
        self.assertNotIn("opens Gate Nine", other_prompt)
        self.assertNotIn("Disabled secret", prompt)

    def test_modernizing_prompts_for_chat_lore_without_destroying_local_book(self):
        self.post("save", book=self.book)
        messenger.save_char_profile(self.char, {"mode": "modern_au", "modern_persona": "A modern archivist."})
        self.thread.refresh_from_db(); self.second.refresh_from_db()
        self.assertTrue(screen_lore.describe(self.thread)["pending"])
        self.assertEqual(self.thread.data["lorebook"]["title"], "Archive")
        self.assertEqual(screen_lore.describe(self.second)["mode"], "off")
        self.assertTrue(screen_lore.describe(self.second)["pending"])
        self.post("mode", mode="off")
        self.thread.refresh_from_db()
        self.assertFalse(screen_lore.describe(self.thread)["pending"])
        self.assertEqual(screen_lore.books_for(self.thread), [])

    def test_new_chat_for_modernized_character_also_offers_lore_setup(self):
        messenger.save_char_profile(self.char, {"modern_persona": "A modern archivist.", "mode": "modern_au"})
        new = messenger.create_thread(self.user, [self.char])
        self.assertTrue(new.data["lore_pending"])
        self.assertEqual(new.data["lore_mode"], "off")

    def test_older_modernized_chat_gets_lore_onboarding(self):
        self.char.messenger_profile = {"mode": "modern_au", "modern_persona": "A modern archivist."}
        self.char.save(update_fields=["messenger_profile"])
        self.assertTrue(screen_lore.describe(self.thread)["pending"])
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data["lore_mode"], "off")

    def test_in_flight_reply_save_preserves_new_lore(self):
        stale = type(self.thread).objects.get(pk=self.thread.pk)
        prepared = messenger.thread_data(stale)
        self.post("save", book=self.book)
        prepared["messages"].append({"role": "assistant", "text": "The key is here."})
        messenger.save_thread_data(stale, prepared)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data["lorebook"]["title"], "Archive")
        self.assertEqual(self.thread.data["lore_mode"], "local")

    def test_copy_edits_do_not_change_the_source_book(self):
        source = Worldbook.objects.create(author=self.user, title="Source", slug="lore-source")
        lorebook.save_worldbook(source, self.book)
        self.assertEqual(self.post("copy", source_id=source.pk).status_code, 200)
        altered = {**self.book, "title": "Different chat"}
        self.post("save", book=altered)
        source.refresh_from_db()
        self.assertEqual(lorebook.load_worldbook(source)["title"], "Archive")

    def test_draft_needs_review_and_does_not_replace_active_lore(self):
        self.post("save", book=self.book)
        draft = {"title": "Suggested", "entries": [{"constant": True, "content": "Suggested setting."}]}
        with patch.object(messenger, "ask_json", return_value=draft) as ask:
            response = self.post("draft", directions="Keep the established archive.")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["book"]["title"], "Archive")
        self.assertEqual(response.json()["draft"]["title"], "Suggested")
        self.assertIn("Keep the established archive", ask.call_args.args[1])

    def test_other_users_chats_and_books_are_not_accessible(self):
        stranger = messenger.create_thread(self.other, [self.char])
        response = self.client.get(reverse("screen_lore_api"), {"thread_id": stranger.pk})
        self.assertEqual(response.status_code, 404)
        source = Worldbook.objects.create(author=self.other, title="Private", slug="private-source")
        self.assertEqual(self.post("copy", source_id=source.pk).status_code, 400)

    def test_getting_lore_does_not_call_a_model(self):
        with patch("mainapp.ai_client.complete") as model:
            response = self.client.get(reverse("screen_lore_api"), {"thread_id": self.thread.pk})
        self.assertEqual(response.status_code, 200)
        model.assert_not_called()

    def test_bulba_lore_card_is_reviewable_and_undoable(self):
        from mainapp.bulba import texting
        from mainapp.models import BulbaSession
        session = BulbaSession.objects.create(user=self.user, thread=self.thread, mode="texting", target_model="generic")
        result, _ = texting.tool_propose_texting_lore(session, {"book": self.book})
        self.assertEqual(result["status"], "waiting for Apply")
        self.thread.refresh_from_db()
        self.assertNotIn("lorebook", self.thread.data)

        proposal = session.proposals[-1]
        texting.apply(session, proposal)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data["lorebook"]["title"], "Archive")
        read, _ = texting.tool_read_texting_chat(session, {})
        self.assertEqual(read["chat_lore"]["saved_book"]["title"], "Archive")
        texting.undo(session, proposal)
        self.thread.refresh_from_db()
        self.assertNotIn("lorebook", self.thread.data)

    def test_undoing_modernization_restores_lore_selection_without_removing_messages(self):
        from mainapp.bulba import texting
        from mainapp.models import BulbaSession
        self.post("save", book=self.book)
        session = BulbaSession.objects.create(user=self.user, thread=self.thread, mode="texting", target_model="generic")
        texting.tool_propose_texting_profile(session, {"changes": {"mode": "modern_au", "modern_persona": "A modern archivist."}})
        proposal = session.proposals[-1]
        texting.apply(session, proposal)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data["lore_mode"], "off")
        data = messenger.thread_data(self.thread)
        data["messages"].append({"role": "user", "text": "A new message."})
        messenger.save_thread_data(self.thread, data)
        texting.undo(session, proposal)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data["lore_mode"], "local")
        self.assertEqual(self.thread.data["messages"][-1]["text"], "A new message.")

    def test_stale_lore_save_is_rejected_without_overwriting_newer_book(self):
        initial = self.client.get(reverse("screen_lore_api"), {"thread_id": self.thread.pk}).json()
        self.post("save", book=self.book)
        response = self.post("save", book={"title": "Stale draft", "entries": []}, version=initial["version"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["current"]["book"]["title"], "Archive")
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data["lorebook"]["title"], "Archive")

    def test_copy_preview_requires_an_explicit_save_to_replace_chat_lore(self):
        self.post("save", book=self.book)
        source = Worldbook.objects.create(author=self.user, title="Other", slug="preview-source")
        lorebook.save_worldbook(source, {"title": "Other world", "entries": []})
        response = self.post("copy", source_id=source.pk, preview=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["preview_book"]["title"], "Other world")
        self.assertEqual(response.json()["book"]["title"], "Archive")
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.data["lorebook"]["title"], "Archive")
