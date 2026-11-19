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


class SeeingAndHearingTests(MessengerActionTests):
    """👁️🎤 The character reads what the user sends: a photo's description, a recorded voice note's words."""
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_a_recorded_voice_note_is_turned_into_words(self):
        with mock.patch("mainapp.voice.transcribe", return_value="I'm outside your lab.") as tr:
            out = self.files(kind="voice_rec", file=upload("voice.webm", b"\x1aE\xdf\xa3fake-webm")).json()
        self.assertEqual(out["transcript"], "I'm outside your lab.")
        self.assertEqual(tr.call_args.args[2], "webm")
        self.assertTrue(out["url"].endswith(".webm"))

    def test_a_sent_photo_is_looked_at_once_and_the_character_reads_what_it_shows(self):
        from mainapp import ai_client
        tid = self.thread()
        url = self.files(kind="image", file=upload()).json()["url"]
        with mock.patch("mainapp.bulba.vision.describe", return_value=("A rainy window with a mug of tea.", "x")) as d:
            msg = self.post(action="send_user_message", thread_id=tid, text="", photo={"kind": "upload", "url": url,
                                                                                   "caption": "my view"}).json()
        self.assertEqual(d.call_count, 1)
        self.assertEqual(MessengerThread.objects.get(id=tid).data["messages"][-1]["photo"]["seen"],
                         "A rainy window with a mug of tea.")
        self.post(action="generate_reply", thread_id=tid)
        prompt = json.dumps(ai_client.complete.call_args.args[2])
        self.assertIn("It shows: A rainy window with a mug of tea.", prompt)
        self.assertIn("my view", prompt)
        self.assertTrue(msg)


class CheckInTests(MessengerActionTests):
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_one_check_in_per_silence(self):
        import time as _time
        from mainapp import ai_client, messenger
        messenger.save_user_profile(self.user, {"spontaneous_texts": True, "spontaneous_minutes": 15})
        tid = self.thread()
        t = MessengerThread.objects.get(id=tid)
        t.data = {"messages": [{"id": "u1", "role": "user", "text": "night", "ts": _time.time() - 3600}]}
        t.save()
        poll = lambda: self.client.get(self.url + "?action=poll&allow_spontaneous=1").json()
        self.assertTrue(poll()["latest_unread"])
        self.assertEqual(ai_client.complete.call_count, 1)
        later = _time.time() + 3 * 3600
        with mock.patch("time.time", return_value=later):
            poll()
        self.assertEqual(ai_client.complete.call_count, 1)  # no second check-in until they answer


class ChatFilesTests(MessengerActionTests):
    """💬 New chat, branch, rename, delete."""
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_new_chat_branch_rename_and_delete(self):
        tid = self.thread()
        t = MessengerThread.objects.get(id=tid)
        t.data = {"messages": [{"id": f"m{i}", "role": "user" if i % 2 == 0 else "assistant", "text": f"text {i}",
                                **({} if i % 2 == 0 else {"sender_slug": self.rose.slug})} for i in range(6)],
                  "scenario_override": "At the market."}
        t.save()
        fresh = self.post(action="new_chat", thread_id=tid).json()["thread"]
        self.assertNotEqual(fresh["id"], tid)
        self.assertEqual(fresh["chat_name"], "Rose · chat 2")
        self.assertEqual(fresh["scenario_override"], "At the market.")
        branch = self.post(action="branch_chat", thread_id=tid, message_id="m3").json()["thread"]
        self.assertEqual([m["id"] for m in branch["messages"]], ["m0", "m1", "m2", "m3"])
        self.assertTrue(branch["branch"])
        self.assertEqual(len(MessengerThread.objects.get(id=tid).data["messages"]), 6)  # the original stays
        out = self.post(action="rename_chat", thread_id=branch["id"], title="What if I'd said yes").json()
        self.assertEqual(out["thread"]["chat_name"], "What if I'd said yes")
        self.assertEqual(len(out["threads"]), 3)
        self.post(action="delete_thread", thread_id=branch["id"])
        self.assertFalse(MessengerThread.objects.filter(id=branch["id"]).exists())
        self.assertEqual(self.post(action="branch_chat", thread_id=tid, message_id="nope").status_code, 400)


class BeforeYouStartTests(MessengerActionTests):
    """🧭 Memory, leave-on-read and a persona for one chat, asked when it starts."""
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_the_chat_persona_and_memory_choice_reach_the_model(self):
        from mainapp import ai_client
        self.user.persona_name, self.user.persona_description = "Anna", "A night-shift nurse."
        self.user.save()
        tid = self.thread()
        self.assertFalse(self.post(action="load_thread", thread_id=tid).json()["thread"]["started"])
        out = self.post(action="thread_settings", thread_id=tid, started=True, share_memory=False, leave_on_read=True,
                        persona={"name": "Mika", "description": "Rose's new upstairs neighbour, a violinist."}).json()
        self.assertTrue(out["thread"]["started"])
        self.assertEqual(out["thread"]["persona"]["name"], "Mika")
        with mock.patch("mainapp.messenger.story_memory.story_text", return_value="They kissed at the festival.") as mem:
            self.post(action="send_user_message", thread_id=tid, text="hi", generate=True)
            mem.assert_not_called()  # this chat said no to sharing memory
        prompt = json.dumps(ai_client.complete.call_args.args[2])
        self.assertIn("upstairs neighbour, a violinist", prompt)
        self.assertNotIn("night-shift nurse", prompt)
        self.assertIn("Mika", prompt)


class SetupLookAndLoreTests(TestCase):
    def test_bulba_lists_what_changed_and_asks_what_is_theirs_to_decide(self):
        from mainapp import messenger
        user = get_user_model().objects.create_user(username="asker", password="pw12345!")
        c = Character.objects.create(name="Dottore", slug="dottore-ask", author=user, initial_message="...",
                                     description="Tall, pale blue hair, a beaked half-mask.")
        reply = json.dumps({"bio": "b", "modern_persona": "A lab director.", "texting_style": "t",
                            "appearance_notes": "Tall, pale blue hair, a charcoal turtleneck and lab coat.",
                            "changes": ["Harbinger → biotech lab director", "No mask"],
                            "questions": ["Keep the mask as something he wears in the lab?"]})
        with mock.patch("mainapp.ai_client.resolve", return_value=(None, "test/model")), \
             mock.patch("mainapp.ai_client.complete", return_value=reply) as complete:
            prof = messenger.modernize_with_bulba(user, c, mode="modern_au")
        self.assertIn("ASK, DON'T DECIDE", complete.call_args.args[2][0]["content"])
        self.assertEqual(prof["setup_notes"]["questions"], ["Keep the mask as something he wears in the lab?"])
        self.assertIn("No mask", prof["setup_notes"]["changes"])
        c.refresh_from_db()
        self.assertNotIn("setup_notes", c.messenger_profile)  # shown with the draft, not kept
        self.assertEqual(c.description, "Tall, pale blue hair, a beaked half-mask.")  # the roleplay card stays


class SplitAndGroupTests(MessengerActionTests):
    """✂️ A card with several people → separate characters and a group chat; 🥔 the group's shared scenario."""
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_split_a_two_person_card_then_write_the_group_scenario(self):
        from mainapp import ai_client, card_sections
        duo = Character.objects.create(name="Twins", slug="twins-split", author=self.user, initial_message="...")
        data = card_sections.empty("ensemble", names=("Ada", "Bea"))
        data["people"][0]["sections"]["identity"]["text"] = "Ada, the older twin."
        data["people"][1]["sections"]["identity"]["text"] = "Bea, the younger twin."
        data["shared"]["setting"]["text"] = "A seaside town."
        data["shared"]["between"]["text"] = "They share a flat and a grudge."
        card_sections.apply(duo, data)
        duo.save()
        member = self.post(action="load_thread", thread_id=self.thread(duo)).json()["thread"]["members"][0]
        self.assertEqual(member["card_people"], ["Ada", "Bea"])
        out = self.post(action="split_card", char_slug=duo.slug).json()["thread"]
        self.assertTrue(out["is_group"])
        self.assertEqual(sorted(m["name"] for m in out["members"]), ["Ada", "Bea"])
        ada = Character.objects.get(author=self.user, name="Ada")
        self.assertIn("Ada, the older twin.", ada.description)
        self.assertIn("A seaside town.", ada.description)
        self.assertIn("They share a flat and a grudge.", ada.description)
        self.assertNotIn("Bea, the younger twin.", ada.description)
        duo.refresh_from_db()
        self.assertEqual(duo.sections["kind"], "ensemble")  # the original card stays
        ai_client.complete.side_effect = lambda *a, **k: json.dumps({"scenario": "The twins added you to their flat chat.",
                                                                     "title": "flat 4B 🏠"})
        g = self.post(action="group_scenario", thread_id=out["id"], hint="I'm their new flatmate").json()["thread"]
        self.assertEqual((g["scenario_override"], g["title"]), ("The twins added you to their flat chat.", "flat 4B 🏠"))
        self.assertIn("I'm their new flatmate", json.dumps(ai_client.complete.call_args.args[2]))
        self.assertEqual(self.post(action="split_card", char_slug=ada.slug).status_code, 400)  # one person: nothing to split


class PictureFixesTests(TestCase):
    def setUp(self):
        from users.models import ConnectionProfile
        self.user = get_user_model().objects.create_user(username="snapper", password="pw12345!")
        self.profile = ConnectionProfile.objects.create(user=self.user, name="Main", api_key="sk-or-x", model="x/y")
        self.c = Character.objects.create(name="Dottore", slug="dottore-snap", author=self.user, initial_message="...",
                                          messenger_profile={"art_style_notes": "painted anime", "neutral_url": "/media/x.png"})

    def test_the_model_list_asks_for_picture_makers(self):
        from mainapp import ai_client
        ai_client._IMAGE_MODELS.update(at=0, list=[])
        resp = mock.Mock(ok=True)
        resp.json.return_value = {"data": [{"id": "microsoft/mai-image-2.7", "name": "MAI",
                                            "architecture": {"output_modalities": ["image"], "input_modalities": ["text", "image"]}}]}
        with mock.patch("mainapp.ai_client.requests.get", return_value=resp) as get:
            models = ai_client.image_models()
        self.assertEqual(get.call_args.kwargs["params"], {"output_modalities": "image"})
        self.assertEqual(models[0]["id"], "microsoft/mai-image-2.7")
        ai_client._IMAGE_MODELS.update(at=0, list=[])

    def test_a_photo_without_them_leaves_their_portraits_out(self):
        from mainapp import messenger
        with mock.patch("mainapp.messenger.make_picture", return_value=(png(), None)) as make, \
             mock.patch("mainapp.messenger.load_character_references", return_value=[(png(), "image/png")]):
            messenger.generate_messenger_photo(self.user, self.c, "a photo of your lunch, without you")
        prompt, refs = make.call_args.args[1], make.call_args.kwargs["references"]
        self.assertIn("NO PEOPLE", prompt)
        self.assertEqual(refs, [])  # an art style in words: no portraits at all
        with mock.patch("mainapp.messenger.make_picture", return_value=(png(), None)) as make, \
             mock.patch("mainapp.messenger.load_character_references", return_value=[(png(), "image/png")]):
            messenger.generate_messenger_photo(self.user, self.c, "No people: the rain on my lab window")
        self.assertNotIn("No people:", make.call_args.args[1].split("Photo subject & scene:")[1])
        self.assertTrue(messenger._wants_no_person("сфоткай обід без себе"))
        self.assertFalse(messenger._wants_no_person("a selfie in the lab"))

    def test_nanogpt_keys_use_mai_too(self):
        from mainapp import ai_client
        from users.models import ConnectionProfile
        self.profile.provider = ConnectionProfile.PROVIDER_NANOGPT
        self.profile.save()
        import base64
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"data": [{"b64_json": base64.b64encode(png()).decode()}]}
        with mock.patch("mainapp.ai_client.requests.post", return_value=resp) as post:
            ai_client.generate_image(self.user, "x", references=[(png(), "image/png")], model="microsoft/mai-image-2.7")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "microsoft/mai-image-2.5/edit")


class SmallThingsTests(MessengerActionTests):
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_edits_are_noticed_and_whole_files_read(self):
        from mainapp import ai_client
        tid = self.thread()
        sent = self.post(action="send_user_message", thread_id=tid, text="I hate you").json()
        mid = (sent.get("user_message") or sent.get("message"))["id"]
        self.post(action="edit_message", thread_id=tid, message_id=mid, text="I hate that I miss you")
        self.post(action="edit_message", thread_id=tid, message_id=mid, text="I miss you")
        table = "| day | shift |\n|---|---|\n" + "\n".join(f"| d{i} | late |" for i in range(80))
        self.post(action="send_user_message", thread_id=tid, text="my week", file={"name": "rota.md", "content": table})
        self.post(action="generate_reply", thread_id=tid)
        prompt = json.dumps(ai_client.complete.call_args.args[2], ensure_ascii=False)
        self.assertIn('it first said: \\"I hate you\\"', prompt)  # the first version, not the middle one
        self.assertIn("| d79 | late |", prompt)  # the whole file, not its first 300 characters
        self.assertIn("my week", prompt)
        self.assertIn("A reaction ALONE", prompt)


class StatusAndPresenceTests(MessengerActionTests):
    """✨ Picture statuses, characters' own statuses; 🟢 presence."""
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_statuses_with_pictures_and_their_own(self):
        from mainapp import ai_client, messenger
        tid = self.thread()
        ai_client.complete.side_effect = lambda *a, **k: "ok [STATUS: ☕ | third coffee | PHOTO: No people: a mug on a lab bench]"
        self.post(action="send_user_message", thread_id=tid, text="hi", generate=True)
        self.rose.refresh_from_db()
        story = messenger.char_profile(self.rose)["stories"][0]
        self.assertEqual((story["text"], story["photo_prompt"]), ("third coffee", "No people: a mug on a lab bench"))
        out = self.post(action="story_picture", owner=self.rose.slug, story_id=story["id"]).json()
        self.assertTrue(out["story"]["image_url"])
        # her own status: due (6+ hours since the last), posted on a poll
        self.rose.messenger_profile = {**self.rose.messenger_profile, "modern_persona": "A florist.", "stories": []}
        self.rose.save()
        ai_client.complete.side_effect = lambda *a, **k: json.dumps({"emoji": "🌷", "text": "tulips in. finally.", "photo": ""})
        self.client.get(self.url + "?action=poll")
        self.rose.refresh_from_db()
        mine = messenger.char_profile(self.rose)["stories"]
        self.assertEqual((mine[0]["text"], mine[0].get("own")), ("tulips in. finally.", True))
        self.assertFalse(messenger.status_due(self.rose))
        messenger.save_user_profile(self.user, {"auto_statuses": False})
        self.assertFalse(messenger.user_profile(self.user)["auto_statuses"])

    def test_presence(self):
        import time as _time
        from mainapp import messenger
        now = _time.time()
        data = {"messages": [{"role": "assistant", "ts": now - 60, "time": "10:00"}]}
        self.assertEqual(messenger.presence(data, now)["state"], "online")
        data["messages"][0]["ts"] = now - 3600
        self.assertEqual(messenger.presence(data, now)["label"], "last seen 10:00")
        data["messages"].append({"role": "assistant", "deliver_at": now + 120, "late_reason": "busy at the lab"})
        self.assertEqual(messenger.presence(data, now)["state"], "busy")
        data["messages"][-1]["late_reason"] = "petty"
        self.assertEqual(messenger.presence(data, now)["state"], "away")


class UserPictureTests(MessengerActionTests):
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_a_picture_of_me_with_references_then_sent(self):
        from django.core.files.base import ContentFile
        from mainapp import ai_client
        self.user.persona_name = "Mika"
        self.user.persona_photo_neutral.save("mika.png", ContentFile(png("green")), save=True)
        tid = self.thread()
        ref = self.files(kind="image", file=upload()).json()["url"]
        out = self.post(action="user_picture", thread_id=tid, prompt="at the bus stop in the rain", refs=[ref], with_me=True).json()
        self.assertTrue(out["url"])
        self.assertEqual(out["seen"], "Mika: at the bus stop in the rain")
        kwargs = ai_client.generate_image.call_args.kwargs
        self.assertEqual(len(kwargs["references"]), 2)  # my persona picture + the upload
        self.assertIn("Mika is in it", ai_client.generate_image.call_args.args[1])
        self.post(action="send_user_message", thread_id=tid, text="",
                  photo={"kind": "generated", "url": out["url"], "caption": "told you", "seen": out["seen"]})
        self.post(action="generate_reply", thread_id=tid)
        self.assertIn("It shows: Mika: at the bus stop in the rain", json.dumps(ai_client.complete.call_args.args[2]))
        self.assertEqual(self.post(action="user_picture", thread_id=tid, prompt="").status_code, 400)


class OneReferenceTests(MessengerActionTests):
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_one_picture_at_a_time(self):
        from mainapp import messenger
        self.rose.messenger_profile = {"appearance_notes": "Red hair, green apron."}
        self.rose.save()
        self.assertEqual(self.post(action="one_reference", char_slug=self.rose.slug, slot=0).status_code, 400)  # neutral first
        prof = self.post(action="one_reference", char_slug=self.rose.slug, slot=-1).json()["profile"]
        self.assertTrue(prof["neutral_url"])
        prof = self.post(action="one_reference", char_slug=self.rose.slug, slot=0).json()["profile"]
        first = prof["extra_refs"][0]
        prof = self.post(action="one_reference", char_slug=self.rose.slug, slot=0).json()["profile"]
        self.assertEqual(len(prof["extra_refs"]), 1)  # redone in place
        self.assertNotEqual(prof["extra_refs"][0], first)
        self.assertTrue(messenger.char_profile(Character.objects.get(id=self.rose.id))["neutral_url"])


class StickerPackTests(MessengerActionTests):
    test_the_page_opens = test_uploads_answer_json = test_texting_and_message_actions = None
    test_group_chats_profiles_and_settings = None

    def test_their_own_pack_replaces_the_roleplay_moods(self):
        out = self.post(action="make_sticker", char_slug=self.rose.slug, mood="smug").json()
        self.assertEqual([s["mood"] for s in out["profile"]["sticker_pack"]], ["smug"])
        self.assertEqual([s["mood"] for s in out["stickers"]], ["smug"])
        again = self.post(action="make_sticker", char_slug=self.rose.slug, mood="smug").json()
        self.assertEqual(len(again["profile"]["sticker_pack"]), 1)  # redone in place

    def test_a_telegram_pack_by_link(self):
        def fake_get(url, params=None, timeout=None):
            r = mock.Mock()
            if url.endswith("getStickerSet"):
                r.json.return_value = {"ok": True, "result": {"title": "Cats", "stickers": [
                    {"file_id": "a", "emoji": "😼"}, {"file_id": "b", "emoji": "🙀", "is_video": True},
                    {"file_id": "c", "emoji": "😹", "is_animated": True}]}}
            elif url.endswith("getFile"):
                r.json.return_value = {"result": {"file_path": f"stickers/{params['file_id']}"}}
            else:
                r.content = b"RIFFfake"
            return r
        with self.settings(TELEGRAM_BOT_TOKEN="123:abc"), mock.patch("requests.get", side_effect=fake_get):
            out = self.post(action="telegram_pack", link="https://t.me/addstickers/CatsPack").json()
        self.assertEqual((out["title"], out["added"], out["skipped"]), ("Cats", 2, 1))
        mine = out["user_profile"]["custom_stickers"]
        self.assertEqual([s["video"] for s in mine], [False, True])
        with self.settings(TELEGRAM_BOT_TOKEN=""):
            self.assertIn("TELEGRAM_BOT_TOKEN", self.post(action="telegram_pack", link="CatsPack").json()["error"])
