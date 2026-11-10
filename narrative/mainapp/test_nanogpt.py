import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from mainapp import ai_client, nanogpt

IDS = ["z-ai/glm-5.3", "z-ai/glm-5.3:thinking", "moonshotai/kimi-k3", "deepseek/deepseek-v4-pro",
       "xiaomi/mimo-v2.6-pro", "google/gemini-3.8-flash-preview", "google/gemini-4-argon", "anthropic/claude-opus-5.5"]


class ModelNameTests(SimpleTestCase):
    def test_app_model_names_are_matched_to_nanogpt_spelling(self):
        self.assertEqual(nanogpt.model_for("z-ai/glm-5.3", ids=IDS), "z-ai/glm-5.3")  # same name: as is
        self.assertEqual(nanogpt.model_for("anthropic/claude-opus-5-5", ids=IDS), "anthropic/claude-opus-5.5")  # profile pattern
        self.assertEqual(nanogpt.model_for("google/gemini-3.8-flash", ids=IDS), "google/gemini-3.8-flash-preview")
        self.assertEqual(nanogpt.model_for("zai-org/glm-5.3", ids=IDS), "z-ai/glm-5.3")  # another maker prefix, plain id preferred
        self.assertEqual(nanogpt.model_for("some/unknown", ids=IDS), "some/unknown")  # nothing better: unchanged
        self.assertEqual(nanogpt.model_for("z-ai/glm-5.3", ids=[]), "z-ai/glm-5.3")  # list unreadable: unchanged


class NanoGPTConnectionTests(TestCase):
    def setUp(self):
        from users.models import ConnectionProfile
        self.user = get_user_model().objects.create_user(username="nano", password="pw12345!")
        self.profile = ConnectionProfile.objects.create(user=self.user, name="Main", provider="nanogpt",
                                                        api_key="nano-key", model="anthropic/claude-opus-5-5")
        nanogpt._CATALOG.update(at=10 ** 12, ids=IDS)
        self.addCleanup(nanogpt._CATALOG.update, at=0, ids=[])

    def test_requests_go_to_nanogpt_with_its_model_names_and_no_openrouter_extras(self):
        sent = []

        def fake(url, headers=None, json=None, **kw):
            sent.append((url, headers, json))
            return mock.Mock(status_code=200, json=mock.Mock(return_value={"choices": [{"message": {"content": "Hi."}}]}))

        with mock.patch("mainapp.ai_client.requests.post", side_effect=fake):
            self.assertEqual(ai_client.complete(self.user, "chat", [{"role": "user", "content": "Hello"}]), "Hi.")
            ai_client.complete(self.user, "bulba", [{"role": "user", "content": "Hello"}])
            ai_client.complete(self.user, "translation", [{"role": "user", "content": "Hello"}])
        url, headers, payload = sent[0]
        self.assertTrue(url.startswith("https://nano-gpt.com/api/v1/chat/completions"))
        self.assertEqual(headers["Authorization"], "Bearer nano-key")
        self.assertEqual(payload["model"], "anthropic/claude-opus-5.5")
        for field in ("usage", "provider", "safety_settings", "plugins"):
            self.assertNotIn(field, payload)
        self.assertEqual(sent[1][2]["model"], "xiaomi/mimo-v2.6-pro")  # Bulba's own model, on NanoGPT too
        self.assertEqual(sent[2][2]["model"], "google/gemini-3.8-flash-preview")  # the translator

    def test_welcome_saves_a_nanogpt_key(self):
        self.profile.delete()
        self.client.force_login(self.user)
        with mock.patch("mainapp.ai_client.test_connection", return_value=(True, "ok")) as check:
            resp = self.client.post(reverse("users:welcome"), json.dumps(
                {"provider": "nanogpt", "api_key": "nk-123", "model": "glm-5-3"}), content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(check.call_args[0][0], "nanogpt")
        from users.models import ConnectionProfile
        p = ConnectionProfile.objects.get(user=self.user)
        self.assertEqual((p.provider, p.api_key, p.api_url), ("nanogpt", "nk-123", "https://nano-gpt.com/api/v1"))

    def test_key_check(self):
        ok_list = mock.Mock(status_code=200, ok=True, json=mock.Mock(return_value={"data": [{"id": i} for i in IDS]}))
        with mock.patch("mainapp.ai_client.requests.get", return_value=ok_list), \
                mock.patch("mainapp.nanogpt.requests.get", return_value=ok_list):
            self.assertTrue(ai_client.test_connection("nanogpt", "", "k", "z-ai/glm-5.3")[0])
            ok, msg = ai_client.test_connection("nanogpt", "", "k", "nobody/has-this")
            self.assertFalse(ok)
            self.assertIn("doesn't list", msg)
        with mock.patch("mainapp.ai_client.requests.get", return_value=mock.Mock(status_code=401)):
            self.assertEqual(ai_client.test_connection("nanogpt", "", "bad", "")[1], "NanoGPT rejected this key.")

    def test_web_search_becomes_the_online_suffix(self):
        sent = []
        reply = {"choices": [{"message": {"content": "Found it.", "annotations": []}}]}

        def fake(url, headers=None, json=None, **kw):
            sent.append(json)
            return mock.Mock(status_code=200, json=mock.Mock(return_value=reply))

        with mock.patch("mainapp.ai_client.requests.post", side_effect=fake):
            ai_client.complete_message(self.user, "bulba", [{"role": "user", "content": "Who is Il Dottore?"}],
                                       plugins=[{"id": "web", "max_results": 5}])
        self.assertEqual(sent[0]["model"], "xiaomi/mimo-v2.6-pro:online")
        self.assertNotIn("plugins", sent[0])

    def test_pictures_come_from_nanogpts_image_endpoint_with_the_reference(self):
        import base64
        png = b"\x89PNG fake"
        sent = []

        def fake(url, headers=None, json=None, **kw):
            sent.append((url, json))
            return mock.Mock(status_code=200, json=mock.Mock(return_value={
                "data": [{"b64_json": base64.b64encode(png).decode()}], "cost": 0.04}))

        with mock.patch("mainapp.ai_client.requests.post", side_effect=fake):
            data, cost = ai_client.generate_image(self.user, "Rose, smiling", reference=b"ref", reference_type="image/png")
        self.assertEqual((data, cost), (png, 0.04))
        url, payload = sent[0]
        self.assertEqual(url, "https://nano-gpt.com/api/v1/images/generations")
        self.assertEqual(payload["model"], "nano-banana-2")
        self.assertTrue(payload["imageDataUrl"].startswith("data:image/png;base64,"))
