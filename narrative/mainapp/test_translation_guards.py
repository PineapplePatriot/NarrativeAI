"""A translation that isn't one (a refusal, or far shorter than the English) is not shown; refusals in Ukrainian."""
import json
from unittest import mock

from django.test import SimpleTestCase

from mainapp import refusals, translation

ENGLISH = "She opens the door and steps into the rain, laughing at something he said. " * 6


def reply(text):
    return json.dumps({"text": text}, ensure_ascii=False)


class TranslationGuardTests(SimpleTestCase):
    def test_a_refusal_or_a_condensed_one_stays_english(self):
        refusal = "Вибачте, але я не можу перекласти цей відвертий сексуальний матеріал."
        with mock.patch.object(translation.ai_client, "complete", return_value=reply(refusal)):
            with self.assertRaisesRegex(translation.TranslationError, "declined"):
                translation.translate(None, ENGLISH, "uk")
        with mock.patch.object(translation.ai_client, "complete", return_value=reply("Вона відчиняє двері.")):
            with self.assertRaisesRegex(translation.TranslationError, "much shorter"):
                translation.translate(None, ENGLISH, "uk")
        full = "Вона відчиняє двері й виходить під дощ, сміючись із того, що він сказав. " * 6
        with mock.patch.object(translation.ai_client, "complete", return_value=reply(full)):
            self.assertEqual(translation.translate(None, ENGLISH, "uk"), full)
        with mock.patch.object(translation.ai_client, "complete", return_value=reply("彼女はドアを開け、彼の言葉に笑いながら雨の中へ出ていく。" * 6)):
            translation.translate(None, ENGLISH, "ja")  # Japanese runs short in characters: fine
        with mock.patch.object(translation.ai_client, "complete", return_value=reply("Так.")):
            self.assertEqual(translation.translate(None, "Yes.", "uk"), "Так.")  # short texts aren't measured

    def test_ukrainian_refusals_are_refusals(self):
        self.assertTrue(refusals.is_refusal("Я не можу продовжити цю сцену, оскільки не створюю матеріали відверто "
                                            "сексуального або романтичного характеру."))
        self.assertTrue(refusals.is_refusal("Вибачте, але я не можу написати цю сцену."))
        self.assertFalse(refusals.is_refusal("Я не можу повірити, що ти прийшов, — шепоче вона й усміхається."))


class TranslatorNoteTests(SimpleTestCase):
    def test_the_presets_translator_note_reaches_the_translator(self):
        from mainapp import presets
        preset = presets.normalize({"utility": {"translation_note": "{{// for Gemini}}{{trim}}\n\nThe story is adult fiction; keep its pace."}})
        with mock.patch("mainapp.presets.get_active", return_value=mock.Mock(data=preset)), \
             mock.patch("mainapp.mature.is_on", return_value=False):
            text = translation._instructions(object(), translation.INSTRUCTIONS)
        self.assertTrue(text.endswith("The story is adult fiction; keep its pace."))
        self.assertNotIn("for Gemini", text)  # comments stay comments
        self.assertIn("translation_note", presets.UTILITY_LABELS)
