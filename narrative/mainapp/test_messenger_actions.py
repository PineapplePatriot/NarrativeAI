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
            mock.patch("mainapp.ai_client.resolve", return_value=(None, "test/model")),
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


class BulbaJsonTests(TestCase):
    """Bulba's answers for the messenger: thinking, fences and cut-off answers still give a profile."""
    def test_reading_lenient_json(self):
        from mainapp.messenger import _read_json
        self.assertEqual(_read_json('<think>hmm {not this}</think>```json\n{"bio": "hi", "n": 1}\n```'), {"bio": "hi", "n": 1})
        cut = '{"handle": "@shinso", "bio": "Не питай.", "modern_persona": "Студент, що мовчить", "texting_style": "коротко'
        self.assertEqual(_read_json(cut), {"handle": "@shinso", "bio": "Не питай.", "modern_persona": "Студент, що мовчить"})
        self.assertEqual(_read_json("no json here"), {})

    def test_a_second_try_when_the_first_answer_is_cut_off(self):
        from mainapp import messenger
        user = get_user_model().objects.create_user(username="jsoner", password="pw12345!")
        answers = ['{"bio": "short', '{"bio": "ok", "modern_persona": "a student", "texting_style": "terse"}']
        with mock.patch("mainapp.ai_client.resolve", return_value=(None, "xiaomi/mimo-v2.6-pro")), \
             mock.patch("mainapp.ai_client.complete", side_effect=answers) as complete:
            data = messenger.ask_json(user, "make a profile", need=("bio", "modern_persona", "texting_style"))
        self.assertEqual(data["texting_style"], "terse")
        self.assertGreaterEqual(complete.call_args_list[0].kwargs["max_tokens"], 1600 + 3000)  # room to think
        self.assertIn("JSON object only", complete.call_args_list[1].args[2][0]["content"])


class SetupDirectionsTests(TestCase):
    def test_their_directions_come_last_and_win(self):
        from mainapp import messenger
        user = get_user_model().objects.create_user(username="director", password="pw12345!")
        c = Character.objects.create(name="Shinso", slug="shinso-dir", author=user, initial_message="...",
                                     scenario="They meet in a hero school sparring match.")
        reply = json.dumps({"bio": "b", "modern_persona": "p", "texting_style": "t", "scenario": "s"})
        with mock.patch("mainapp.ai_client.resolve", return_value=(None, "test/model")), \
             mock.patch("mainapp.ai_client.complete", return_value=reply) as complete:
            messenger.modernize_with_bulba(user, c, hint="We met at a 24-hour laundromat at 3am.")
        prompt = complete.call_args.args[2][0]["content"]
        self.assertGreater(prompt.index("24-hour laundromat"), prompt.index("hero school sparring"))
        self.assertIn("the directions win", prompt)
        self.assertIn("binding", prompt)


class TagReadingTests(TestCase):
    def test_a_voice_note_keeps_its_whole_line_with_delivery_tags_inside(self):
        from mainapp import messenger
        user = get_user_model().objects.create_user(username="voicer", password="pw12345!")
        c = Character.objects.create(name="Rose", slug="rose-voice", author=user, initial_message="Hi.")
        parsed = messenger.parse_ai_reply("[VOICE: [sighs] fine. [laughs] come over, I'll put the kettle on]", [c])
        bubbles = parsed["bubbles"] if isinstance(parsed, dict) else parsed
        voice = next(b["voice"] for b in bubbles if b.get("voice"))
        self.assertEqual(voice["transcript"], "[sighs] fine. [laughs] come over, I'll put the kettle on")
        self.assertEqual(messenger.take_tag("look [PHOTO: me at the [old] desk] ok", ("PHOTO",)),
                         ("PHOTO", "me at the [old] desk", "look  ok"))


class PictureModelTests(TestCase):
    def test_the_chosen_picture_model_and_image_only_requests(self):
        from mainapp import ai_client, messenger
        from users.models import ConnectionProfile
        user = get_user_model().objects.create_user(username="painter", password="pw12345!")
        ConnectionProfile.objects.create(user=user, name="Main", api_key="sk-or-x", model="x/y")
        messenger.save_user_profile(user, {"image_model": "microsoft/mai-image-2.7"})
        self.assertEqual(messenger.user_profile(user)["image_model"], "microsoft/mai-image-2.7")
        messenger.save_user_profile(user, {"image_model": "some/unknown"})  # not on the list: ignored
        self.assertEqual(messenger.user_profile(user)["image_model"], "microsoft/mai-image-2.7")
        import base64
        sent = {}

        def fake_post(url, headers=None, json=None, timeout=None, **kw):
            sent.update(json)
            resp = mock.Mock(status_code=200)
            data = "data:image/png;base64," + base64.b64encode(png()).decode()
            resp.json.return_value = {"choices": [{"message": {"images": [{"image_url": {"url": data}}]}}], "usage": {}}
            return resp
        listed = [{"id": "microsoft/mai-image-2.7", "name": "MAI", "text_out": False, "takes_pictures": True}]
        with mock.patch("mainapp.ai_client.image_models", return_value=listed), \
             mock.patch("mainapp.ai_client.requests.post", side_effect=fake_post):
            messenger.make_picture(user, "a selfie", references=[(png(), "image/png")])
        self.assertEqual((sent["model"], sent["modalities"]), ("microsoft/mai-image-2.7", ["image"]))
        self.assertEqual(sent["messages"][0]["content"][1]["type"], "image_url")  # the reference went along


class RedoOneMessageTests(MessengerActionTests):
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_any_of_their_messages_again_with_a_note_and_the_chat_before_it(self):
        tid = self.thread()
        t = MessengerThread.objects.get(id=tid)
        t.data = {"messages": [
            {"id": "u1", "role": "user", "text": "are you up?"},
            {"id": "a1", "role": "assistant", "sender_slug": self.rose.slug, "sender_name": "Rose", "text": "obviously"},
            {"id": "a2", "role": "assistant", "sender_slug": self.rose.slug, "sender_name": "Rose", "text": "go to sleep"},
            {"id": "a3", "role": "assistant", "sender_slug": self.rose.slug, "sender_name": "Rose",
             "voice": {"transcript": "[sighs] fine", "audio_url": "/x.mp3"}, "text": ""},
        ]}
        t.save()
        from mainapp import ai_client
        ai_client.complete.reset_mock()
        ai_client.complete.side_effect = lambda *a, **k: "Rose: never. come over"
        out = self.post(action="redo_message", thread_id=tid, message_id="a1", note="warmer").json()
        self.assertEqual(out["message"]["text"], "never. come over")  # the name in front comes off
        sent = json.dumps(ai_client.complete.call_args.args[2])
        self.assertIn("obviously", sent)  # the old version, in the instruction
        self.assertIn("warmer", sent)
        self.assertNotIn("go to sleep", sent)  # the chat as it was before that message
        msgs = MessengerThread.objects.get(id=tid).data["messages"]
        self.assertEqual([m.get("text") for m in msgs[:3]], ["are you up?", "never. come over", "go to sleep"])
        voice = self.post(action="redo_message", thread_id=tid, message_id="a3").json()["message"]["voice"]
        self.assertEqual((voice["transcript"], voice["audio_url"]), ("never. come over", ""))  # made again on play
        self.assertEqual(self.post(action="redo_message", thread_id=tid, message_id="u1").status_code, 400)


class LeaveOnReadTests(MessengerActionTests):
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_a_late_reply_waits_hidden_and_no_second_reply_meanwhile(self):
        import time as _time
        from mainapp import ai_client, messenger
        tid = self.thread()
        self.post(action="thread_settings", thread_id=tid, leave_on_read=True)
        ai_client.complete.side_effect = lambda *a, **k: "[LATER: 3] ugh. fine. |||BUBBLE||| what"
        self.post(action="send_user_message", thread_id=tid, text="you there?")
        out = self.post(action="generate_reply", thread_id=tid).json()
        self.assertGreater(out["thread"]["waiting"], 170)
        self.assertEqual([m["role"] for m in out["thread"]["messages"]], ["user"])  # hidden for now
        prompt = json.dumps(ai_client.complete.call_args.args[2])
        self.assertIn("LEAVING ON READ IS ALLOWED", prompt)
        ai_client.complete.reset_mock()
        self.post(action="send_user_message", thread_id=tid, text="hello??")
        self.assertGreater(self.post(action="generate_reply", thread_id=tid).json()["thread"]["waiting"], 0)
        ai_client.complete.assert_not_called()  # they're away: no second reply on top
        later = _time.time() + 4 * 60
        with mock.patch("mainapp.messenger.time.time", return_value=later):
            shown = messenger.serialize_thread_full(MessengerThread.objects.get(id=tid), self.user)
        self.assertEqual([m.get("text") for m in shown["messages"] if m["role"] == "assistant"], ["ugh. fine.", "what"])
        self.assertNotIn("LATER", json.dumps(shown["messages"]))

    def test_without_the_switch_the_tag_is_ignored(self):
        from mainapp import ai_client
        tid = self.thread()
        ai_client.complete.side_effect = lambda *a, **k: "[LATER: 3] hey"
        self.post(action="send_user_message", thread_id=tid, text="hi")
        out = self.post(action="generate_reply", thread_id=tid).json()
        self.assertEqual(out["thread"]["waiting"], 0)
        self.assertEqual(out["thread"]["messages"][-1]["text"], "hey")
