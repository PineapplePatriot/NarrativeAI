"""↻ A chat page reload says why (logged), and translating a reply never needs one: it's found by its text."""
from unittest import mock

from mainapp import tests as base


class ReloadAndTranslateTests(base.ChatPromptTests):
    def test_a_reply_is_found_by_its_text_when_the_numbering_is_off(self):
        self.post({"action": "chat", "message": "Hi."})
        self.user.display_language = "uk"
        self.user.save()
        reply = self.saved_messages()[-1][2]
        with mock.patch("mainapp.translation.translate", return_value="Відповідь."), \
             mock.patch("mainapp.translation.translate_extras", return_value=[]):
            d = self.post({"action": "translate", "index": 99, "text": reply}).json()
        self.assertTrue(d["success"], d)
        self.assertEqual(d["text"], "Відповідь.")
        with mock.patch("mainapp.translation.translate", return_value="x"):
            d = self.post({"action": "translate", "index": 99, "text": "not in the chat"}).json()
        self.assertFalse(d["success"])
        self.assertNotIn("resync", d)  # the English stays; no reload

    def test_the_reason_for_a_reload_is_logged(self):
        with self.assertLogs("mainapp.views", level="WARNING") as logs:
            self.assertTrue(self.post({"action": "reload_note", "why": "the connection dropped mid-reply"}).json()["success"])
        self.assertIn("the connection dropped mid-reply", "\n".join(logs.output))


for _name in [n for n in vars(base.ChatPromptTests) if n.startswith("test_")]:
    setattr(ReloadAndTranslateTests, _name, None)
