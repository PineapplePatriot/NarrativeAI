import json
from unittest.mock import patch
from django.test import SimpleTestCase
from mainapp import lorebook, translation


class TranslationTests(SimpleTestCase):
    def test_english_bypasses_provider(self):
        with patch.object(translation.ai_client, "complete") as complete:
            self.assertEqual(translation.translate(None, "Hello", "en"), "Hello")
        complete.assert_not_called()

    def test_task_preserves_original_and_metadata(self):
        message = ("assistant", "12:00", "The hospital is closed.", "sad", 1, {"reasoning": "private"})
        with patch.object(translation.ai_client, "complete", return_value=json.dumps({"text": "Лікарня закрита."})) as complete:
            text = translation.translate(None, message[2], "uk")
        paired = translation.with_translation(message, text, "uk")
        self.assertEqual(paired[2], message[2])
        self.assertEqual(paired[5]["reasoning"], "private")
        self.assertEqual(translation.display_text(paired, "uk"), text)
        self.assertEqual(translation.display_text(paired, "pl"), message[2])
        self.assertEqual(complete.call_args.args[1], "translation")

    def test_lore_matches_both_versions_without_doubling_depth(self):
        message = translation.with_translation(("assistant", "", "The hospital is closed.", "", 1), "Лікарня закрита.", "uk")
        book = lorebook.normalize_book({"settings": {"scan_depth": 1}, "entries": [
            {"keys": ["лікарня"], "content": "Ukrainian entry"},
            {"keys": ["hospital"], "content": "English entry"},
        ]})
        result = lorebook.activate(book, [("user", "", "Hello", "", 1), message])
        self.assertEqual({e["content"] for e in result["entries"]}, {"Ukrainian entry", "English entry"})

    def test_stale_translation_is_never_shown_or_matched(self):
        from mainapp import chats
        message = translation.with_translation(("assistant", "", "hospital", "", 1), "лікарня", "uk")
        edited = chats.set_text(message, "station")
        self.assertIsNone(translation.translation_of(edited))
        self.assertEqual(lorebook._message_text(edited), "station")

    def test_edit_builds_pair_only_after_success(self):
        message = translation.with_translation(("assistant", "", "Hello", "", 1), "Привіт", "uk")
        with patch.object(translation.ai_client, "complete", return_value='{"text":"Goodbye"}'):
            edited = translation.synchronize_edit(None, message, "До побачення", "uk")
        self.assertEqual(edited[2], "Goodbye")
        self.assertEqual(translation.display_text(edited, "uk"), "До побачення")
        self.assertEqual(message[2], "Hello")

    def test_bad_output_or_changed_markers_fails_without_mutation(self):
        for output in ('not json', '{}', '{"text":""}', '{"text":"Translated without marker"}'):
            with self.subTest(output=output), patch.object(translation.ai_client, "complete", return_value=output):
                with self.assertRaises(translation.TranslationError):
                    translation.translate(None, "<b>Hello</b> [[extra 1]]", "uk")

    def test_preserves_formatting_in_translation(self):
        with patch.object(translation.ai_client, "complete", return_value=json.dumps({"text": '<b>Привіт</b> {{char}} [[extra 1]]'})):
            self.assertIn("Привіт", translation.translate(None, '<b>Hello</b> {{char}} [[extra 1]]', "uk"))
