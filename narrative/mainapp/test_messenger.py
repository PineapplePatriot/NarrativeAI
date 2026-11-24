import io
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from mainapp import messenger
from mainapp.models import Character, MessengerThread
from users.models import ApiConfig, ConnectionProfile


class MessengerHubTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="anya",
            password="pw123456!",
            persona_name="Anya",
            persona_description="Sharp analyst who drinks too much espresso.",
        )
        self.client.force_login(self.user)
        ConnectionProfile.objects.create(
            user=self.user,
            name="Main OR",
            provider=ConnectionProfile.PROVIDER_OPENROUTER,
            api_key="sk-or-test-key",
            model="xiaomi/mimo-v2.6-pro",
        )
        self.char1 = Character.objects.create(
            author=self.user,
            name="Il Dottore",
            slug="anya-il-dottore",
            description="Second of the Fatui Harbingers. Brilliant, ruthless scholar.",
            personality="Cold, clinical, sardonic.",
            scenario="Working late in the Sumeru lab.",
            initial_message="State your business.",
            eleven_voice_char_id="voice_dottore_1",
        )
        self.char2 = Character.objects.create(
            author=self.user,
            name="Pantalone",
            slug="anya-pantalone",
            description="Ninth Harbinger, banker of Snezhnaya.",
            personality="Polite, calculating, Smiling.",
            scenario="Reviewing ledgers.",
        )

    def test_screen_hub_creates_initial_thread_and_renders(self):
        resp = self.client.get(reverse("screen_hub"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "TeleChat")
        self.assertEqual(MessengerThread.objects.filter(user=self.user).count(), 1)

    def test_group_chat_creation_and_multi_speaker_turn(self):
        url = reverse("messenger_api")
        res = self.client.post(
            url,
            data=json.dumps({
                "action": "create_thread",
                "character_slugs": [self.char1.slug, self.char2.slug],
                "title": "Harbinger Budget Chat",
                "scenario_override": "Arguing over lab funding at midnight.",
            }),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertTrue(payload["thread"]["is_group"])
        self.assertEqual(payload["thread"]["title"], "Harbinger Budget Chat")
        tid = payload["thread"]["id"]

        # Send user message
        send_res = self.client.post(
            url,
            data=json.dumps({
                "action": "send_user_message",
                "thread_id": tid,
                "text": "Who spent the entire quarter's budget on glass tubes?",
                "generate": False,
            }),
            content_type="application/json",
        )
        self.assertEqual(send_res.status_code, 200)

        fake_ai_reply = (
            "Il Dottore: [REACT: 👀] They are precision quartz resonators, not 'glass tubes'.\n"
            "|||BUBBLE|||\n"
            "Pantalone: Whatever they are, the invoice has six zeroes. [FILE: invoice_402.txt | Total due: 4,200,000 Mora]"
        )
        with patch("mainapp.ai_client.complete", return_value=fake_ai_reply):
            gen_res = self.client.post(
                url,
                data=json.dumps({"action": "generate_reply", "thread_id": tid}),
                content_type="application/json",
            )
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        bubbles = data["turn"]["bubbles"]
        self.assertEqual(len(bubbles), 2)
        self.assertEqual(bubbles[0]["sender_slug"], self.char1.slug)
        self.assertEqual(bubbles[1]["sender_slug"], self.char2.slug)
        self.assertEqual(bubbles[1]["file"]["name"], "invoice_402.txt")
        # Check reaction was applied to user's message
        user_msg = data["thread"]["messages"][0]
        self.assertIn("👀", user_msg["reactions"])

    def test_bulba_modern_au_keeps_original_card_untouched(self):
        url = reverse("messenger_api")
        fake_bulba_json = json.dumps({
            "handle": "@dr_zandik",
            "status_emoji": "🧪",
            "bio": "Head of Biotech R&D. Don't call before 10 AM.",
            "modern_persona": "Director of a private biomedical institute in Zurich.",
            "texting_style": "Dry, full punctuation, never uses exclamation marks.",
            "scenario": "You are his newly hired lab ethics auditor.",
            "first_text": "Did you sign off on protocol 14 yet?",
        })
        with patch("mainapp.ai_client.complete", return_value=fake_bulba_json):
            res = self.client.post(
                url,
                data=json.dumps({
                    "action": "modernize_bulba",
                    "char_slug": self.char1.slug,
                    "mode": "modern_au",
                    "hint": "Biotech director",
                }),
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 200)
        prof = res.json()["profile"]
        self.assertEqual(prof["mode"], "modern_au")
        self.assertEqual(prof["handle"], "@dr_zandik")
        self.assertIn(" Zurich", prof["modern_persona"])

        # Original RP card must be untouched
        self.char1.refresh_from_db()
        self.assertEqual(self.char1.description, "Second of the Fatui Harbingers. Brilliant, ruthless scholar.")
        self.assertEqual(self.char1.scenario, "Working late in the Sumeru lab.")

    def test_profile_bio_and_status_updates_from_ai_and_user(self):
        thread = messenger.create_thread(self.user, [self.char1])
        fake_ai = (
            "[BIO: Do not disturb — running diagnostics.] "
            "[STATUS: ⚡ | Third coffee since midnight.] "
            "I'm locked in the cleanroom until 4 AM."
        )
        with patch("mainapp.ai_client.complete", return_value=fake_ai):
            turn = messenger.generate_turn(self.user, thread)
        self.assertEqual(len(turn["bubbles"]), 1)
        self.assertEqual(len(turn["system_notices"]), 2)
        self.char1.refresh_from_db()
        prof = messenger.char_profile(self.char1)
        self.assertEqual(prof["bio"], "Do not disturb — running diagnostics.")
        self.assertEqual(prof["stories"][0]["text"], "Third coffee since midnight.")

    def test_voice_and_nano_banana_photo_bubbles(self):
        ApiConfig.objects.create(user=self.user, eleven_key="el-test-key")
        thread = messenger.create_thread(self.user, [self.char1])
        td = messenger.thread_data(thread)
        td["messages"].append({
            "id": "m_voice1",
            "role": "assistant",
            "sender_slug": self.char1.slug,
            "sender_name": self.char1.name,
            "text": "[sighs] Listen carefully.",
            "voice": {"transcript": "[sighs] Listen carefully.", "audio_url": "", "duration": 3},
            "time": "02:15",
            "ts": 1700000000,
            "reactions": {},
        })
        messenger.save_thread_data(thread, td)

        url = reverse("messenger_api")
        with patch("mainapp.voice.synthesize_single", return_value=b"ID3-fake-mp3-bytes"):
            v_res = self.client.post(
                url,
                data=json.dumps({"action": "voice_bubble", "thread_id": thread.id, "message_id": "m_voice1"}),
                content_type="application/json",
            )
        self.assertEqual(v_res.status_code, 200)
        self.assertTrue(v_res.json()["audio_url"].endswith(".mp3"))

        with patch("mainapp.ai_client.generate_image", return_value=(b"\x89PNG\r\n\x1a\nfake", 0.02)) as mock_img:
            p_res = self.client.post(
                url,
                data=json.dumps({
                    "action": "photo_bubble",
                    "thread_id": thread.id,
                    "char_slug": self.char1.slug,
                    "kind": "casual",
                    "prompt": "Late night lab desk with glowing vials",
                }),
                content_type="application/json",
            )
        self.assertEqual(p_res.status_code, 200)
        self.assertTrue(p_res.json()["url"].endswith(".png"))
        # Food / desk / scenery photo must be detected as pov_object with style lock
        called_prompt = mock_img.call_args[0][1]
        self.assertIn("CRITICAL STYLE LOCK", called_prompt)
        self.assertIn("Camera angle & framing:", called_prompt)

    def test_voice_preview_with_custom_voice_id(self):
        url = reverse("messenger_api")
        with patch("mainapp.voice.synthesize_single", return_value=b"ID3-preview-bytes") as mock_tts:
            res = self.client.post(
                url,
                data=json.dumps({
                    "action": "preview_voice",
                    "char_slug": self.char1.slug,
                    "voice_id": "JBFqnCBsd6RMkjVDRZzb",
                    "voice_model": "elevenlabs/eleven-v4-turbo",
                }),
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["audio_url"].endswith(".mp3"))
        self.assertEqual(mock_tts.call_args[1]["voice_id"], "JBFqnCBsd6RMkjVDRZzb")

    def test_create_messenger_character_with_bulba_standalone(self):
        url = reverse("messenger_api")
        fake_bulba_char = json.dumps({
            "name": "Kaveh",
            "handle": "@light_of_kshahrewar",
            "status_emoji": "📐",
            "bio": "Independent architect. Commissions open (please).",
            "modern_persona": "Freelance sustainable architect in Milan drowning in client revisions and espresso.",
            "texting_style": "Expressive, rapid-fire double texts, dramatic punctuation, vents warmly.",
            "appearance_notes": "Blonde hair with red geometric clips, carmine eyes, linen shirt with rolled sleeves, drafting pencil behind ear.",
            "art_style_notes": "Crisp anime illustration, warm golden-hour lighting, cel-shaded detail.",
            "voice_id": "liam",
            "scenario": "Texting you at 1 AM because a client asked to remove a load-bearing column.",
            "first_text": "Tell me honestly — if I scream into a throw pillow right now, does that count as structural engineering?",
            "tags": ["architect", "roommate", "modern-au"],
        })
        with patch("mainapp.ai_client.complete", return_value=fake_bulba_char), \
             patch("mainapp.ai_client.generate_image", return_value=(b"\x89PNG\r\n\x1a\nfake", 0.02)):
            res = self.client.post(
                url,
                data=json.dumps({
                    "action": "create_char_bulba",
                    "name": "Kaveh",
                    "idea": "Stressed architect friend in Milan",
                    "mode": "modern_au",
                    "generate_pics": True,
                }),
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["character"]["name"], "Kaveh")
        self.assertEqual(data["character"]["handle"], "@light_of_kshahrewar")
        self.assertTrue(data["character"]["neutral_url"].endswith(".png"))
        self.assertEqual(len(data["character"]["extra_refs"]), 1)
        self.assertIn("thread", data)

    def test_multi_reference_and_varied_selfie_angle_generation(self):
        # Configure 1 neutral + 2 extra references on char1
        messenger.save_char_profile(self.char1, {
            "neutral_url": "/media/test_neutral.png",
            "extra_refs": ["/media/test_ref1.png", "/media/test_ref2.png"],
            "appearance_notes": "Pale skin, crimson eyes, blue-white hair, ear cuff.",
            "art_style_notes": "Dark anime painting style.",
        })
        fake_refs = [
            (b"neutral-bytes", "image/png"),
            (b"ref1-bytes", "image/png"),
            (b"ref2-bytes", "image/png"),
        ]
        with patch("mainapp.messenger.load_character_references", return_value=fake_refs), \
             patch("mainapp.ai_client.generate_image", return_value=(b"\x89PNG\r\n\x1a\nfake", 0.02)) as mock_gen:
            url, _ = messenger.generate_messenger_photo(
                self.user,
                self.char1,
                description="Loosening tie in the elevator mirror after hours",
                kind="tease",
            )
        self.assertTrue(url.endswith(".png"))
        self.assertEqual(len(mock_gen.call_args[1]["references"]), 3)
        prompt_sent = mock_gen.call_args[0][1]
        self.assertIn("Camera angle & composition", prompt_sent)
        self.assertIn("CRITICAL IDENTITY & STYLE LOCK", prompt_sent)
        self.assertIn("Dark anime painting style.", prompt_sent)

    def test_automatic_per_model_texting_rules_switch(self):
        thread = messenger.create_thread(self.user, [self.char1])
        # Initial profile in setUp is xiaomi/mimo-v2.6-pro
        info_mimo = messenger.active_model_texting_rules(self.user)
        self.assertIn("mimo", info_mimo["profile_id"])
        self.assertIn("ANTI-RECAP & ANTI-ECHO", info_mimo["rules"])

        # Switch user's active connection profile model to Gemini 2.5 Pro mid-chat
        prof = ConnectionProfile.objects.filter(user=self.user).first()
        prof.model = "google/gemini-2.5-pro"
        prof.save()

        info_gemini = messenger.active_model_texting_rules(self.user)
        self.assertEqual(info_gemini["model_id"], "google/gemini-2.5-pro")
        self.assertIn("Strict Phone Horizon", info_gemini["rules"])

        # Prompt built for the very next message must automatically include Gemini rules
        messages = messenger.build_messenger_prompt(self.user, thread)
        sys_prompt = messages[0]["content"]
        self.assertIn("ACTIVE MODEL TEXTING CALIBRATION (Gemini 4 Argon)", sys_prompt)
        self.assertIn("Strict Phone Horizon", sys_prompt)

    def test_frankenstein_stage_direction_stripping_and_poll(self):
        cleaned = messenger.strip_stage_directions("*he sighs and looks down at his phone screen* Fine. Send me the file.")
        self.assertEqual(cleaned, "Fine. Send me the file.")

        poll_res = self.client.get(reverse("messenger_api") + "?action=poll")
        self.assertEqual(poll_res.status_code, 200)
        self.assertIn("total_unread", poll_res.json())

    def test_multipart_photo_and_reference_uploads(self):
        url = reverse("messenger_api")
        fake_png = SimpleUploadedFile("neutral.png", b"\x89PNG\r\n\x1a\nfake", content_type="image/png")
        res_neutral = self.client.post(
            url,
            data={
                "kind": "char_neutral",
                "char_slug": self.char1.slug,
                "file": fake_png,
            },
        )
        self.assertEqual(res_neutral.status_code, 200)
        n_data = res_neutral.json()
        self.assertTrue(n_data["url"].endswith(".png"))
        self.assertEqual(n_data["profile"]["neutral_url"], n_data["url"])

        fake_ref = SimpleUploadedFile("extra1.png", b"\x89PNG\r\n\x1a\nfake2", content_type="image/png")
        res_extra = self.client.post(
            url,
            data={
                "kind": "char_extra_ref",
                "char_slug": self.char1.slug,
                "slot": "0",
                "file": fake_ref,
            },
        )
        self.assertEqual(res_extra.status_code, 200)
        e_data = res_extra.json()
        self.assertEqual(len(e_data["profile"]["extra_refs"]), 1)
        self.assertEqual(e_data["profile"]["extra_refs"][0], e_data["url"])

        fake_chat_img = SimpleUploadedFile("chat_snap.jpg", b"\xff\xd8\xff\xe0fakejpg", content_type="image/jpeg")
        res_img = self.client.post(
            url,
            data={
                "kind": "image",
                "file": fake_chat_img,
            },
        )
        self.assertEqual(res_img.status_code, 200)
        self.assertTrue(res_img.json()["url"].endswith(".jpg"))

    def test_subtext_feed_burner_aita_and_forward_to_telechat(self):
        url = reverse("subtext_api")
        fake_wave = json.dumps({
            "posts": [
                {
                    "author_slug": self.char1.slug,
                    "visibility": "burner",
                    "title": "",
                    "text": "If one more banker asks me to itemize centrifuge coolant I am locking the vault from the outside.",
                    "subtweet_note": "Locked 2 AM rant",
                    "photo_prompt": "Messy late-night lab desk with cold espresso",
                    "comments": [
                        {
                            "author_slug": self.char2.slug,
                            "is_burner": False,
                            "verdict": "",
                            "text": "You forgot to remove me from your close friends list, Doctor.",
                        }
                    ],
                },
                {
                    "author_slug": self.char2.slug,
                    "visibility": "aita",
                    "title": "AITA for freezing a colleague's discretionary card at midnight?",
                    "text": "He spent 4.2 million on quartz tubes without a receipt.",
                    "subtweet_note": "Anonymous AITA thread",
                    "photo_prompt": "",
                    "comments": [
                        {
                            "author_slug": self.char1.slug,
                            "is_burner": True,
                            "verdict": "YTA",
                            "text": "They were precision resonators.",
                        }
                    ],
                },
            ]
        })
        with patch("mainapp.ai_client.complete", return_value=fake_wave):
            res = self.client.post(
                url,
                data=json.dumps({
                    "action": "generate_wave",
                    "mode": "mix",
                    "character_slugs": [self.char1.slug, self.char2.slug],
                }),
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 200)
        new_posts = res.json()["new_posts"]
        self.assertEqual(len(new_posts), 2)
        burner_post = new_posts[0]
        aita_post = new_posts[1]
        self.assertEqual(burner_post["visibility"], "burner")
        self.assertTrue(burner_post["handle"].endswith("_priv"))
        self.assertEqual(len(burner_post["comments"]), 1)
        self.assertEqual(aita_post["aita_votes"]["yta"], 1)

        # User votes NTA on the AITA thread
        vote_res = self.client.post(
            url,
            data=json.dumps({"action": "vote_aita", "post_id": aita_post["id"], "verdict": "NTA"}),
            content_type="application/json",
        )
        self.assertEqual(vote_res.status_code, 200)
        self.assertEqual(vote_res.json()["aita_votes"]["nta"], 1)

        # User forwards Dottore's locked burner post straight into his TeleChat DM
        with patch("mainapp.ai_client.complete", return_value="Who gave you access to that account?"):
            fwd_res = self.client.post(
                url,
                data=json.dumps({
                    "action": "forward_to_telechat",
                    "post_id": burner_post["id"],
                    "comment": "Saw your locked burner post.",
                }),
                content_type="application/json",
            )
        self.assertEqual(fwd_res.status_code, 200)
        fwd_data = fwd_res.json()
        self.assertIn("Locked Burner Post", fwd_data["user_message"]["text"])
        self.assertEqual(fwd_data["turn"]["bubbles"][0]["text"], "Who gave you access to that account?")

    def test_vn_meetup_scene_dynamic_sprites_and_finale_cg_gallery(self):
        from . import sprites
        thread = messenger.create_thread(self.user, [self.char1])
        self.client.post(
            reverse("messenger_api"),
            data=json.dumps({
                "action": "send_user_message",
                "thread_id": thread.id,
                "text": "Meet me at the cafe, I'm on my way!",
                "generate": False,
            }),
            content_type="application/json",
        )

        url = reverse("vn_scenes_api")
        cue_res = self.client.post(
            url,
            data=json.dumps({"action": "check_meetup", "thread_id": thread.id}),
            content_type="application/json",
        )
        self.assertEqual(cue_res.status_code, 200)
        self.assertTrue(cue_res.json()["meetup_cue"]["ready"])

        fake_start = json.dumps({
            "title": "Midnight Espresso Meet-Up",
            "location": "Neon Corner Cafe",
            "music_id": "builtin_music_0",
            "background_id": "builtin_bg_0",
            "beats": [
                {
                    "speaker": "narrator",
                    "kind": "narration",
                    "emotion": "neutral",
                    "text": "Rain streaks the cafe window as the bell above the door chimes.",
                },
                {
                    "speaker": self.char1.slug,
                    "kind": "dialogue",
                    "emotion": "flustered",
                    "text": "You're actually early for once. Don't look at me like that.",
                },
            ],
            "handoff": "user_turn",
            "choices": [
                "*slides a hot espresso across the booth* \"For you.\"",
                "\"You ran here in the rain, didn't you?\"",
            ],
        })
        with patch("mainapp.ai_client.complete", return_value=fake_start):
            start_res = self.client.post(
                url,
                data=json.dumps({
                    "action": "start_scene",
                    "thread_id": thread.id,
                    "location_hint": "Neon Corner Cafe",
                }),
                content_type="application/json",
            )
        self.assertEqual(start_res.status_code, 200)
        scene = start_res.json()["scene"]
        self.assertEqual(scene["title"], "Midnight Espresso Meet-Up")
        self.assertEqual(len(scene["beats"]), 2)
        char_beat = scene["beats"][1]
        self.assertEqual(char_beat["emotion"], "flustered")
        self.assertEqual(char_beat["sprite_url"], "")  # no episode look yet: the stage shows the name only
        self.char1.refresh_from_db()
        self.assertNotIn("flustered", sprites.extras(self.char1))

        # Step the scene forward with user action/dialogue
        fake_step = json.dumps({
            "beats": [
                {
                    "speaker": "narrator",
                    "kind": "narration",
                    "emotion": "neutral",
                    "text": "He wraps both hands around the warm porcelain cup.",
                },
                {
                    "speaker": self.char1.slug,
                    "kind": "dialogue",
                    "emotion": "flustered",
                    "text": "...Acceptable. At least someone in this city knows how to pull a proper shot.",
                },
            ],
            "handoff": "climax_ready",
            "choices": ["*clinks cups together*"],
        })
        with patch("mainapp.ai_client.complete", return_value=fake_step):
            step_res = self.client.post(
                url,
                data=json.dumps({
                    "action": "step_scene",
                    "user_input": "*slides a hot espresso across the booth* \"For you.\"",
                }),
                content_type="application/json",
            )
        self.assertEqual(step_res.status_code, 200)
        stepped_scene = step_res.json()["scene"]
        self.assertEqual(stepped_scene["handoff"], "climax_ready")
        # Because 'flustered' was saved permanently on self.char1, the new beat reuses it without needing gen!

        # End the scene on a full generated Finale Event CG -> saved in gallery & logged to TeleChat
        fake_cg_distill = json.dumps({
            "visual_prompt": "Cinematic widescreen VN Event CG in a rainy neon cafe booth, Dottore holding a steaming espresso cup across from the viewer, warm amber reflections.",
            "summary": "Met up at the Neon Corner Cafe during a rainstorm and shared late-night espresso.",
            "quote": "At least someone in this city knows how to pull a proper shot.",
        })
        fake_cg_bytes = b"\x89PNG\r\n\x1a\nfinalecg"
        with patch("mainapp.ai_client.complete", return_value=fake_cg_distill), \
             patch("mainapp.messenger.make_picture", return_value=(fake_cg_bytes, 0.04)):
            fin_res = self.client.post(
                url,
                data=json.dumps({"action": "finish_scene", "cg_hint": "Close-up across the rainy booth"}),
                content_type="application/json",
            )
        self.assertEqual(fin_res.status_code, 200)
        fin_data = fin_res.json()
        entry = fin_data["gallery_entry"]
        self.assertEqual(entry["title"], "Midnight Espresso Meet-Up")
        self.assertTrue(entry["cg_url"].endswith(".png"))
        self.assertEqual(len(fin_data["vn_scenes"]["gallery"]), 1)
        self.assertIsNone(fin_data["vn_scenes"]["active_scene"])

        # Verify the linked TeleChat thread received both the scene summary and the Finale CG photo bubble
        thread.refresh_from_db()
        td = messenger.thread_data(thread)
        self.assertTrue(any(m.get("episode") for m in td["messages"]))
        self.assertTrue(any((m.get("photo") or {}).get("url") == entry["cg_url"] for m in td["messages"]))




