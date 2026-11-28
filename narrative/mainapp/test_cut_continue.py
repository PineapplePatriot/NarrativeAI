"""✂️ Cut & continue: the latest reply kept up to a sentence (a new swipe), then continued, with a note if any."""
import json

from mainapp import tests as base


class CutContinueTests(base.ChatPromptTests):
    def test_cut_keeps_the_whole_reply_one_swipe_away(self):
        self.post({"action": "chat", "message": "Tell me."})
        msgs = self.saved_messages()
        from mainapp import chats
        msgs[-1] = chats.set_text(msgs[-1], "She smiles. She opens the door. She leaves.")
        data = chats.read(self.character.chats.first())
        data["messages"] = msgs
        chats.write(self.character.chats.first(), data)
        r = self.post({"action": "cut", "keep": "She smiles. She opens the door. "}).json()
        self.assertTrue(r["success"], r)
        self.assertEqual(r["reply"], "She smiles. She opens the door.")
        self.assertEqual(r["swipes"], {"count": 2, "current": 1})
        self.assertEqual(self.saved_messages()[-1][2], "She smiles. She opens the door.")
        # not a start of the reply (it changed since) / the whole reply / not the last reply: refused
        self.assertTrue(self.post({"action": "cut", "keep": "Something else."}).json().get("resync"))
        self.assertFalse(self.post({"action": "cut", "keep": "She smiles. She opens the door."}).json()["success"])

    def test_continue_takes_their_note(self):
        self.post({"action": "chat", "message": "Tell me."})
        self.post({"action": "continue", "direction": "she says no"})
        sent = json.dumps(self.sent[-1]["messages"])
        self.assertIn("Where it goes from here: she says no", sent)
        self.post({"action": "continue"})
        self.assertNotIn("Where it goes from here", json.dumps(self.sent[-1]["messages"]))



for _name in [n for n in vars(base.ChatPromptTests) if n.startswith("test_")]:  # the inherited ones run in their own class
    setattr(CutContinueTests, _name, None)


class ContinueLikeANewReplyTests(base.ChatPromptTests):
    """Continue gets what a new reply gets on top of the preset (one function builds both: views.reply_notes)."""
    def test_continue_has_the_same_notes(self):
        self.post({"action": "chat", "message": "Tell me."})
        new_reply = json.dumps(self.sent[-1]["messages"])
        self.post({"action": "continue"})
        cont = json.dumps(self.sent[-1]["messages"])
        self.assertIn("Keep out of it", new_reply)
        self.assertIn("Keep out of it", cont)  # the habits line (it was missing from Continue)

    def test_fires_on_limits_are_kept_by_the_editor(self):
        from django.urls import reverse
        from mainapp import presets
        obj = presets.get_active(self.user)
        data = presets.normalize(obj.data)
        data["blocks"][0]["triggers"] = ["normal", "swipe"]
        r = self.client.post(reverse("presets"), json.dumps({"action": "save_full", "id": obj.id, "blocks": data["blocks"],
                             "utility": data["utility"], "options": data["options"]}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content[:200])
        obj.refresh_from_db()
        self.assertEqual(presets.normalize(obj.data)["blocks"][0]["triggers"], ["normal", "swipe"])
        self.assertFalse(presets.fires_on(presets.normalize(obj.data)["blocks"][0], "continue"))


for _name in [n for n in vars(base.ChatPromptTests) if n.startswith("test_")]:
    setattr(ContinueLikeANewReplyTests, _name, None)
