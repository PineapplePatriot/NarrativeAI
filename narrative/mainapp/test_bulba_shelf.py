"""📚 Bulba sees all their presets: list, read, switch, mix; and a preset sent as a file (mainapp/bulba/shelf.py)."""
import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from mainapp import presets
from mainapp.bulba import actions, doctor, shelf
from mainapp.models import BulbaSession, Preset


def docx(paragraphs):
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    style = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
    body = "".join(f"<w:p>{style if h else ''}<w:r><w:t>{t}</w:t></w:r></w:p>" for h, t in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document {w}><w:body>{body}</w:body></w:document>")
    return buf.getvalue()


class ShelfTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="shelf", password="pw12345!")
        self.active = presets.get_active(self.user)
        data = presets.normalize(self.active.data)
        data["blocks"].insert(0, {"name": "Pacing", "kind": "prompt", "role": "system", "content": "Slow burn.", "enabled": True})
        self.other = Preset.objects.create(user=self.user, name="Old favourite", data=presets.normalize(data))
        self.session = BulbaSession.objects.create(user=self.user, target_model="x", mode="setup")

    def test_list_read_and_mix(self):
        rows = shelf.tool_list_presets(self.session, {})[0]["presets"]
        self.assertEqual({r["name"] for r in rows}, {self.active.name, "Old favourite"})
        self.assertTrue(rows[0]["active"])
        self.assertIn("Pacing", shelf.tool_read_preset(self.session, {"preset": "old fav"})[0]["outline"])
        self.assertEqual(shelf.tool_read_preset(self.session, {"preset": "Old favourite", "block": "pacing"})[0]["content"], "Slow burn.")
        out, _ = doctor.tool_propose_preset_edit(self.session, {"edits": [{"from_preset": "Old favourite", "from_block": "Pacing"}],
                                                               "why": "mix"})
        actions.apply(self.session, out["proposal"])
        active = presets.normalize(presets.get_active(self.user).data)
        self.assertEqual(next(b for b in active["blocks"] if b["name"] == "Pacing")["content"], "Slow burn.")

    def test_switch_and_undo(self):
        out, _ = shelf.tool_propose_preset_switch(self.session, {"preset": "Old favourite"})
        actions.apply(self.session, out["proposal"])
        self.assertEqual(presets.get_active(self.user).name, "Old favourite")
        actions.undo(self.session, out["proposal"])
        self.assertEqual(presets.get_active(self.user).id, self.active.id)

    def test_a_written_out_preset_keeps_the_slots(self):
        raw = docx([(True, "Style"), (False, "Write in past tense."), (False, "Short paragraphs."),
                    (True, "Rules"), (False, "Never speak for the user.")])
        obj = shelf.save_file(self.user, "My prompt.docx", raw)
        data = presets.normalize(obj.data)
        self.assertFalse(obj.is_active)
        on = [b for b in data["blocks"] if b["kind"] == "prompt" and b["enabled"]]
        self.assertEqual([b["name"] for b in on][1:], ["Rules"])
        self.assertTrue(on[0]["name"].startswith("Style"))  # "Style (file)" when their preset has a Style block too
        self.assertIn("Short paragraphs.", on[0]["content"])
        self.assertTrue(any(b["kind"] == "marker" for b in data["blocks"]))  # the card, the chat... still there
        md = shelf.from_file(self.user, "x.md", b"# Tone\nWarm.\n# Length\nTwo paragraphs.")[0]
        self.assertEqual([b["name"] for b in md["blocks"] if b["kind"] == "prompt" and b["enabled"]], ["Tone", "Length"])
        with self.assertRaises(ValueError):
            shelf.from_file(self.user, "x.pdf", b"%PDF")

    def test_sent_with_the_paperclip_in_a_chat(self):
        from unittest import mock
        self.client.force_login(self.user)
        f = SimpleUploadedFile("st.json", json.dumps({"prompts": [{"identifier": "main", "name": "Main", "content": "Be vivid."}],
                                                      "prompt_order": []}).encode(), content_type="application/json")
        with mock.patch("mainapp.bulba.agent.run_turn", return_value=[]) as turn, \
             mock.patch("mainapp.views._bulba_for_request", return_value=self.session):
            r = self.client.post(reverse("bulba_api"), {"preset_file": f, "text": "mix the main bit in"})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertIn("not switched on", r.json()["events"][0]["text"])
        self.assertIn("mix the main bit in", turn.call_args.kwargs["model_note"])
        self.assertEqual(presets.get_active(self.user).id, self.active.id)
