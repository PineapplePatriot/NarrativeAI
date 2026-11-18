"""
📱 Every action of the Screen Hub's messenger API (/main/screen/api/), pressed once with fake AI answers: none may
crash (a crash sends an HTML error page, which the page shows as "Unexpected token '<'"), and each answers JSON.
"""
import io
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from mainapp.models import Character, MessengerThread


def png(color="red", size=(48, 48)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def upload(name="pic.png", data=None):
    f = io.BytesIO(data or png())
    f.name = name
    return f


REPLY = "hey!! you're up late\n\nwhat's going on"


@override_settings(MEDIA_ROOT="/tmp/claude-0/-home-user-NarrativeAI/0c39a082-36f6-5a20-aba0-a51e92a02661/scratchpad/test-media")
class MessengerActionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="texter", password="pw12345!")
        self.client.force_login(self.user)
        self.rose = Character.objects.create(name="Rose", slug="rose-msg", author=self.user, initial_message="Hi.",
                                             description="A florist with a sharp tongue.")
        self.sam = Character.objects.create(name="Sam", slug="sam-msg", author=self.user, initial_message="Yo.")
        self.url = reverse("messenger_api")
        patches = [
            mock.patch("mainapp.ai_client.complete", side_effect=self.fake_complete),
            mock.patch("mainapp.ai_client.generate_image", return_value=(png("blue", (64, 64)), None)),
            mock.patch("mainapp.voice.synthesize_single", return_value=b"ID3fake-mp3"),
            mock.patch("mainapp.voice.synthesize_openrouter", return_value=b"ID3fake-mp3"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_complete(self, user, task, messages, **kw):
        text = json.dumps(messages)
        if "visual_prompt" in text:
            return json.dumps({"visual_prompt": "a selfie in a flower shop", "shot_type": "selfie", "camera_angle": "high"})
        if "handle" in text or "Modern" in text or "bio" in text:
            return json.dumps({"name": "Rose", "handle": "@rose", "bio": "flowers & spite", "modern_persona": "A florist.",
                               "texting_style": "lowercase, quick", "scenario": "They met at a market.",
                               "appearance": "red hair", "description": "A florist."})
        return REPLY

    def post(self, **body):
        resp = self.client.post(self.url, json.dumps(body), content_type="application/json")
        self.assertLess(resp.status_code, 500, f"{body.get('action')} crashed: {resp.content[:300]}")
        self.assertEqual(resp["Content-Type"].split(";")[0], "application/json", body.get("action"))
        import os
        if os.environ.get("NA_SHOW"):
            print("ACTION", body.get("action"), resp.status_code, resp.content[:160])
        return resp

    def files(self, **fields):
        resp = self.client.post(self.url, fields)
        self.assertLess(resp.status_code, 500, f"upload {fields.get('kind')} crashed: {resp.content[:300]}")
        self.assertEqual(resp["Content-Type"].split(";")[0], "application/json")
        return resp

    def thread(self, *chars):
        resp = self.post(action="create_thread", character_slugs=[c.slug for c in chars] or [self.rose.slug])
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        data = resp.json()
        return (data.get("thread") or {}).get("id") or data.get("thread_id") or MessengerThread.objects.filter(user=self.user).latest("id").id

    def test_the_page_opens(self):
        self.assertEqual(self.client.get(reverse("screen_hub")).status_code, 200)
        self.assertEqual(self.client.get(self.url + "?action=poll").status_code, 200)

    def test_uploads_answer_json(self):
        tid = self.thread()
        self.assertEqual(self.files(kind="image", file=upload()).status_code, 200)
        self.assertEqual(self.files(kind="file", file=upload("note.txt", b"hello")).status_code, 200)
        self.assertEqual(self.files(kind="sticker", file=upload()).status_code, 200)
        self.assertEqual(self.files(kind="char_neutral", char_slug=self.rose.slug, file=upload()).status_code, 200)
        self.assertEqual(self.files(kind="char_extra_ref", char_slug=self.rose.slug, slot="-1", file=upload()).status_code, 200)
        self.assertTrue(tid)

    def test_texting_and_message_actions(self):
        tid = self.thread()
        out = self.post(action="send_user_message", thread_id=tid, text="hi", generate=True)
        self.assertEqual(out.status_code, 200, out.content[:300])
        self.post(action="generate_reply", thread_id=tid, instruction="")
        thread = self.post(action="load_thread", thread_id=tid).json()
        msgs = (thread.get("thread") or thread).get("messages") or []
        self.assertTrue(msgs, thread)
        mid = msgs[-1]["id"]
        for action, extra in (("react", {"emoji": "❤️"}), ("edit_message", {"text": "edited"}), ("pin_message", {}),
                              ("voice_bubble", {}), ("photo_bubble", {"kind": "casual", "prompt": ""}),
                              ("delete_message", {})):
            self.post(action=action, thread_id=tid, message_id=mid, **extra)

    def test_group_chats_profiles_and_settings(self):
        tid = self.thread(self.rose, self.sam)
        self.post(action="generate_reply", thread_id=tid)
        self.post(action="thread_settings", thread_id=tid, scenario_override="Stuck at an airport.", events=[])
        self.post(action="pin_thread", thread_id=tid)
        self.post(action="char_profile", char_slug=self.rose.slug, profile={"bio": "new bio"})
        self.post(action="user_profile", profile={"display_name": "Me", "bio": "hi"})
        self.post(action="post_story", owner="user", text="out for coffee", emoji="☕")
        self.post(action="modernize_bulba", char_slug=self.rose.slug, mode="modern_au", hint="")
        self.post(action="preview_voice", voice_id="sarah", text="Hello there")
        self.post(action="generate_char_refs", char_slug=self.rose.slug, count=1)
        self.post(action="create_char_bulba", idea="a grumpy barista", name="Vex", mode="modern_au")
        self.post(action="delete_thread", thread_id=tid)


class RegenerateAndSetupTests(MessengerActionTests):
    """↻ Try again with a note, and 🥔 Bulba's setup for characters not yet adapted for texting."""
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_try_again_replaces_the_last_reply_and_passes_the_note(self):
        tid = self.thread()
        self.post(action="send_user_message", thread_id=tid, text="hi", generate=True)
        before = MessengerThread.objects.get(id=tid).data["messages"]
        self.assertEqual(before[-1]["role"], "assistant")
        from mainapp import ai_client
        ai_client.complete.reset_mock()
        out = self.post(action="regenerate", thread_id=tid, note="Say it as a voice note.")
        self.assertEqual(out.status_code, 200, out.content[:300])
        sent = json.dumps(ai_client.complete.call_args.args[2])
        self.assertIn("Say it as a voice note.", sent)
        data = MessengerThread.objects.get(id=tid).data
        self.assertEqual([m["role"] for m in data["messages"]].count("user"), 1)
        self.assertTrue(data["regen_prev"])  # the old take, kept for now
        self.post(action="delete_message", thread_id=tid, message_id=data["messages"][-1]["id"])

    def test_nothing_to_try_again_before_a_reply(self):
        tid = self.thread()
        self.assertEqual(self.post(action="regenerate", thread_id=tid).status_code, 400)

    def test_setup_flag_modernize_and_a_new_look(self):
        from mainapp import messenger
        tid = self.thread()
        member = self.post(action="load_thread", thread_id=tid).json()["thread"]["members"][0]
        self.assertFalse(member["set_up"])  # the chat offers Bulba's setup
        self.post(action="modernize_bulba", char_slug=self.rose.slug, mode="modern_au", hint="she runs a night florist")
        self.rose.refresh_from_db()
        self.assertTrue(messenger.is_set_up(self.rose))
        out = self.post(action="setup_look", char_slug=self.rose.slug, outfit="a green apron over a black hoodie").json()
        prof = out["profile"]
        self.assertTrue(prof["neutral_url"] and prof["avatar_url"] == prof["neutral_url"])
        self.assertEqual(len(prof["extra_refs"]), 1)
        self.assertIn("Outfit in this setup: a green apron over a black hoodie", prof["appearance_notes"])
        self.rose.refresh_from_db()
        self.assertFalse(self.rose.photo_neutral)  # the roleplay card's own pictures are left alone
