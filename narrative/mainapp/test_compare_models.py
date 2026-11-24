"""🧪 Comparing models on the last reply (mainapp/bulba/compare.py)."""
from django.test import TestCase


class CompareModelsTests(TestCase):
    """🧪 The last reply written again by a few models, each with its cost (bulba/compare.py)."""
    def test_compare(self):
        import json
        from unittest import mock
        from django.contrib.auth import get_user_model
        from mainapp import chats
        from mainapp.models import BulbaSession, Character
        from mainapp.bulba import compare
        from users.models import ConnectionProfile
        user = get_user_model().objects.create_user("comparer", "c@example.com", "pw12345!")
        ConnectionProfile.objects.create(user=user, name="Main", api_key="sk-or-x", model="xiaomi/mimo-v2.6-pro")
        rose = Character.objects.create(name="Rose", slug="rose-cmp", author=user, initial_message="Hi.")
        chat = chats.current(rose)
        session = BulbaSession.objects.create(user=user, target_model="x", mode="chat", chat=chat)
        out, events = compare.tool_compare_models(session, {})
        self.assertIn("call again with confirmed", out["error"])  # asks before spending
        ids = ["xiaomi/mimo-v2.6-pro", "deepseek/deepseek-v4-flash", "moonshotai/kimi-k3", "moonshotai/kimi-k3:free"]
        sent = []
        def fake(user, task, messages, **params):
            sent.append(params["model"])
            return {"content": f"Reply by {params['model']}."}, 0.002
        with mock.patch.object(compare, "_openrouter_ids", return_value=ids), \
             mock.patch("mainapp.ai_client.complete_message", side_effect=fake):
            out, events = compare.tool_compare_models(session, {"confirmed": True, "models": ["deepseek-v4-flash", "kimi-k3", "nope"]})
        self.assertEqual(sent, ["xiaomi/mimo-v2.6-pro", "deepseek/deepseek-v4-flash", "moonshotai/kimi-k3"])
        self.assertEqual(out["unknown"], ["nope"])
        self.assertEqual(len(events), 3)
        self.assertIn("$0.0020", events[1]["samples"][0]["label"])
        self.assertTrue(events[0]["samples"][0]["label"].startswith("Now"))
