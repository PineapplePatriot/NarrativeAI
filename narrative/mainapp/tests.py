import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from mainapp.lorebook import activate, format_for_prompt, normalize_book, to_sillytavern
from mainapp.models import Worldbook


def make_book(entries, **settings):
    return normalize_book({"entries": entries, "settings": settings})


def fired(book, messages):
    result = activate(book, messages)
    return [r["label"] for r in result["report"] if r["status"] == "included"]


class KeywordMatchingTests(SimpleTestCase):
    def test_keyword_fires_case_insensitive(self):
        book = make_book([{"comment": "Dottore", "keys": ["Dottore"], "content": "A mad scientist."}])
        self.assertEqual(fired(book, ["Is dottore in his lab?"]), ["Dottore"])

    def test_no_keyword_no_fire(self):
        book = make_book([{"comment": "Dottore", "keys": ["Dottore"], "content": "A mad scientist."}])
        self.assertEqual(fired(book, ["Let's go to the market."]), [])

    def test_whole_words_by_default(self):
        book = make_book([{"comment": "Cat", "keys": ["cat"], "content": "A cat."}])
        self.assertEqual(fired(book, ["The catalogue is open."]), [])
        self.assertEqual(fired(book, ["A cat, sleeping."]), ["Cat"])

    def test_whole_words_off(self):
        book = make_book([{"comment": "Cat", "keys": ["cat"], "content": "A cat."}], match_whole_words=False)
        self.assertEqual(fired(book, ["The catalogue is open."]), ["Cat"])

    def test_case_sensitive_entry_override(self):
        book = make_book([{"comment": "Rose", "keys": ["Rose"], "content": "A woman.", "case_sensitive": True}])
        self.assertEqual(fired(book, ["a rose garden"]), [])
        self.assertEqual(fired(book, ["Rose waves"]), ["Rose"])

    def test_multi_word_and_unicode_keys(self):
        book = make_book([
            {"comment": "Tower", "keys": ["Ivory Tower"], "content": "Tall."},
            {"comment": "Kyiv", "keys": ["Київ"], "content": "Capital."},
        ])
        self.assertEqual(sorted(fired(book, ["We reach the ivory tower.", "Потім до Києва? Ні, Київ."])),
                         ["Kyiv", "Tower"])

    def test_regex_key(self):
        book = make_book([{"comment": "Dragon", "keys": ["/drag(on|ons)/i"], "content": "Big."}])
        self.assertEqual(fired(book, ["DRAGONS above!"]), ["Dragon"])

    def test_scan_depth_limits_history(self):
        book = make_book([{"comment": "Sword", "keys": ["sword"], "content": "Sharp."}], scan_depth=2)
        msgs = ["I drew my sword.", "Then we walked.", "And talked."]
        self.assertEqual(fired(book, msgs), [])
        self.assertEqual(fired(book, msgs[:2]), ["Sword"])

    def test_entry_scan_depth_override(self):
        book = make_book([{"comment": "Sword", "keys": ["sword"], "content": "Sharp.", "scan_depth": 5}],
                         scan_depth=1)
        self.assertEqual(fired(book, ["I drew my sword.", "Then we walked."]), ["Sword"])

    def test_chat_log_message_format(self):
        book = make_book([{"comment": "Sword", "keys": ["sword"], "content": "Sharp."}])
        log = [["user", "10:00", "My sword!", "neutral", 1]]
        self.assertEqual(fired(book, log), ["Sword"])


class SecondaryLogicTests(SimpleTestCase):
    def entry(self, logic):
        return make_book([{"comment": "E", "keys": ["Dottore"], "secondary_keys": ["lab", "experiment"],
                           "selective_logic": logic, "content": "x"}])

    def test_and_any(self):
        book = self.entry("AND_ANY")
        self.assertEqual(fired(book, ["Dottore in the lab"]), ["E"])
        self.assertEqual(fired(book, ["Dottore at home"]), [])

    def test_and_all(self):
        book = self.entry("AND_ALL")
        self.assertEqual(fired(book, ["Dottore in the lab"]), [])
        self.assertEqual(fired(book, ["Dottore's lab experiment"]), ["E"])

    def test_not_any(self):
        book = self.entry("NOT_ANY")
        self.assertEqual(fired(book, ["Dottore at home"]), ["E"])
        self.assertEqual(fired(book, ["Dottore in the lab"]), [])

    def test_not_all(self):
        book = self.entry("NOT_ALL")
        self.assertEqual(fired(book, ["Dottore in the lab"]), ["E"])
        self.assertEqual(fired(book, ["Dottore's lab experiment"]), [])


class ActivationRulesTests(SimpleTestCase):
    def test_constant_always_included(self):
        book = make_book([{"comment": "World", "constant": True, "content": "Magic exists."}])
        self.assertEqual(fired(book, ["hello"]), ["World"])

    def test_disabled_is_reported_not_included(self):
        book = make_book([{"comment": "Off", "keys": ["x"], "content": "c", "enabled": False}])
        report = activate(book, ["x"])["report"]
        self.assertEqual([(r["label"], r["status"]) for r in report], [("Off", "disabled")])
        self.assertEqual(activate(book, ["x"])["entries"], [])

    def test_budget_keeps_highest_order(self):
        book = make_book([
            {"comment": "Low", "keys": ["a"], "content": "x" * 400, "order": 1},
            {"comment": "High", "keys": ["a"], "content": "y" * 400, "order": 50},
        ], token_budget=150)
        result = activate(book, ["a"])
        statuses = {r["label"]: r["status"] for r in result["report"]}
        self.assertEqual(statuses, {"High": "included", "Low": "over_budget"})

    def test_prompt_order_most_important_last(self):
        book = make_book([
            {"comment": "High", "keys": ["a"], "content": "H", "order": 50},
            {"comment": "Low", "keys": ["a"], "content": "L", "order": 1},
        ])
        text = format_for_prompt(activate(book, ["a"])["entries"])
        self.assertLess(text.index("[Low]"), text.index("[High]"))

    def test_recursion(self):
        entries = [
            {"comment": "Dottore", "keys": ["Dottore"], "content": "Works for the Tsaritsa."},
            {"comment": "Tsaritsa", "keys": ["Tsaritsa"], "content": "The Cryo Archon."},
        ]
        self.assertEqual(fired(make_book(entries), ["Dottore?"]), ["Dottore"])
        self.assertEqual(sorted(fired(make_book(entries, recursive_scan=True), ["Dottore?"])),
                         ["Dottore", "Tsaritsa"])

    def test_prevent_and_exclude_recursion(self):
        entries = [
            {"comment": "Dottore", "keys": ["Dottore"], "content": "Works for the Tsaritsa.",
             "prevent_recursion": True},
            {"comment": "Tsaritsa", "keys": ["Tsaritsa"], "content": "The Cryo Archon."},
        ]
        self.assertEqual(fired(make_book(entries, recursive_scan=True), ["Dottore?"]), ["Dottore"])
        entries[0]["prevent_recursion"] = False
        entries[1]["exclude_recursion"] = True
        self.assertEqual(fired(make_book(entries, recursive_scan=True), ["Dottore?"]), ["Dottore"])

    def test_semantic_missing_package_is_reported(self):
        book = make_book([{"comment": "E", "keys": ["zzz"], "content": "c"}], semantic_enabled=True)
        result = activate(book, ["hello"])
        self.assertEqual(result["entries"], [])
        # Either the package is missing (note) or it ran; both must not crash
        self.assertIsInstance(result["notes"], list)


class ImportTests(SimpleTestCase):
    ST_FILE = {"entries": {
        "0": {"uid": 0, "key": ["Dottore"], "keysecondary": ["lab"], "selectiveLogic": 3,
              "comment": "Doc", "content": "Scientist.", "constant": False, "disable": False,
              "order": 120, "caseSensitive": None, "matchWholeWords": None, "scanDepth": 3},
        "1": {"uid": 1, "key": [], "comment": "World", "content": "Magic.", "constant": True,
              "disable": True, "order": 10},
    }}

    def test_sillytavern_world_info(self):
        book = normalize_book(self.ST_FILE)
        doc, world = book["entries"]
        self.assertEqual(doc["keys"], ["Dottore"])
        self.assertEqual(doc["secondary_keys"], ["lab"])
        self.assertEqual(doc["selective_logic"], "AND_ALL")
        self.assertEqual(doc["order"], 120)
        self.assertEqual(doc["scan_depth"], 3)
        self.assertIsNone(doc["case_sensitive"])
        self.assertTrue(world["constant"])
        self.assertFalse(world["enabled"])

    def test_character_card_v2(self):
        card = {"spec": "chara_card_v2", "data": {"name": "Rose", "character_book": {
            "name": "Rose's book", "scan_depth": 6,
            "entries": [{"keys": ["garden"], "content": "She loves it.", "enabled": True,
                         "insertion_order": 7, "secondary_keys": [], "extensions": {"match_whole_words": False}}],
        }}}
        book = normalize_book(card)
        self.assertEqual(book["title"], "Rose's book")
        self.assertEqual(book["settings"]["scan_depth"], 6)
        entry = book["entries"][0]
        self.assertEqual(entry["order"], 7)
        self.assertFalse(entry["match_whole_words"])

    def test_old_native_format(self):
        book = normalize_book({"entries": [
            {"id": 1, "key": "Dottore, Doctor", "tags": ["npc"], "priority": 40, "enabled": True, "value": "x"}]})
        entry = book["entries"][0]
        self.assertEqual(entry["keys"], ["Dottore", "Doctor"])
        self.assertEqual(entry["content"], "x")
        self.assertEqual(entry["order"], 40)

    def test_round_trip_through_sillytavern_export(self):
        book = normalize_book(self.ST_FILE)
        again = normalize_book(to_sillytavern(book))
        for a, b in zip(book["entries"], again["entries"]):
            self.assertEqual(a, b)

    def test_duplicate_uids_fixed(self):
        book = normalize_book({"entries": [{"uid": 1, "keys": ["a"], "content": "x"},
                                           {"uid": 1, "keys": ["b"], "content": "y"}]})
        self.assertEqual(len({e["uid"] for e in book["entries"]}), 2)


@override_settings(MEDIA_ROOT="/tmp/narrative-test-media")
class WorldbookViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ann", password="pw12345!")
        self.client.force_login(self.user)

    def post_json(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_create_with_import_then_test_and_export(self):
        resp = self.post_json(reverse("worldbook_create"),
                              {"title": "Teyvat", "import": ImportTests.ST_FILE})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["count"], 2)
        wb = Worldbook.objects.get(author=self.user)

        page = self.client.get(reverse("worldbook_detail", args=[wb.slug]))
        self.assertContains(page, "Teyvat")

        book = page.context["worldbook_json"]
        resp = self.post_json(reverse("worldbook_test", args=[wb.slug]),
                              {"book": book, "messages": ["Dottore's lab"]})
        self.assertEqual([r["label"] for r in resp.json()["report"]], ["Doc"])

        resp = self.client.get(reverse("worldbook_export", args=[wb.slug]) + "?format=sillytavern")
        self.assertIn('"0"', resp.content.decode())

    def test_duplicate_titles_get_unique_slugs(self):
        self.post_json(reverse("worldbook_create"), {"title": "Lore"})
        self.post_json(reverse("worldbook_create"), {"title": "Lore"})
        self.assertEqual(sorted(Worldbook.objects.values_list("slug", flat=True)), ["lore", "lore-2"])

    def test_save_and_delete(self):
        self.post_json(reverse("worldbook_create"), {"title": "Lore"})
        url = reverse("worldbook_detail", args=["lore"])
        resp = self.post_json(url, {"title": "Lore v2", "description": "", "settings": {"scan_depth": 9},
                                    "entries": [{"keys": ["a"], "content": "x"}]})
        self.assertEqual(resp.json()["count"], 1)
        wb = Worldbook.objects.get(slug="lore")
        self.assertEqual(wb.title, "Lore v2")
        self.assertEqual(self.client.get(url).context["worldbook_json"]["settings"]["scan_depth"], 9)

        resp = self.client.post(reverse("worldbook_delete", args=["lore"]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Worldbook.objects.exists())

    def test_other_users_book_is_hidden(self):
        other = get_user_model().objects.create_user(username="bob", password="pw12345!")
        Worldbook.objects.create(title="Secret", slug="secret", author=other)
        self.assertEqual(self.client.get(reverse("worldbook_detail", args=["secret"])).status_code, 404)
        self.assertEqual(self.client.post(reverse("worldbook_delete", args=["secret"])).status_code, 404)


class ChatPromptTests(TestCase):
    """The chat view, with OpenRouter replaced by a fake."""

    def setUp(self):
        import shutil
        import tempfile
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

        from mainapp.models import Character
        from users.models import ConnectionProfile

        self.user = get_user_model().objects.create_user(username="chatter", password="pw12345!")
        ConnectionProfile.objects.create(user=self.user, name="Main", api_key="test-key", model="test/model")
        self.character = Character.objects.create(name="Rose", slug="rose-chat-test", author=self.user,
                                                  initial_message="Hello, traveller.")
        self.client.force_login(self.user)
        self.url = reverse("chat", args=[self.character.slug])
        self.sent = []      # payloads of the main chat calls
        self.all_calls = []  # every payload, including emotion/summary calls
        self.reply_status = 200

    def fake_post(self, url, headers=None, json=None, timeout=None):
        from unittest import mock
        self.all_calls.append(json)
        first = json["messages"][0]["content"]
        is_emotion = "response_format" in json
        is_summary = first.startswith(("Existing summary", "Summarize this entire"))
        if not (is_emotion or is_summary):
            self.sent.append(json)
        resp = mock.Mock()
        resp.status_code = self.reply_status
        payload = ({"choices": [{"message": {"content": "A reply."}}]} if self.reply_status < 400
                   else {"error": {"message": "Invalid credentials"}})
        resp.json.return_value = payload
        return resp

    def post(self, data):
        from unittest import mock
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def saved_messages(self):
        self.character.refresh_from_db()
        with open(self.character.chat_log_file.path, encoding="utf-8") as f:
            return json.load(f)["messages"]

    def test_history_is_sent_once(self):
        self.post({"action": "chat", "message": "Where is the tower?"})
        self.post({"action": "chat", "message": "Let's go there."})
        messages = self.sent[-1]["messages"]
        joined = "\n".join(m["content"] for m in messages)
        self.assertNotIn("[CHAT HISTORY]", joined)
        self.assertNotIn("[LAST USER MESSAGE]", joined)
        self.assertEqual(joined.count("Where is the tower?"), 1)
        self.assertEqual(messages[-1], {"role": "user", "content": "Let's go there."})

    def test_regenerate_does_not_add_empty_user_message(self):
        self.post({"action": "chat", "message": "Hi!"})
        before = self.saved_messages()
        self.post({"action": "regenerate"})
        after = self.saved_messages()
        self.assertEqual(len(after), len(before))
        self.assertEqual([m[0] for m in after], ["assistant", "user", "assistant"])
        self.assertFalse(any(m[0] == "user" and not m[2] for m in after))
        self.assertEqual(self.sent[-1]["messages"][-1], {"role": "user", "content": "Hi!"})

    def test_ai_error_is_shown_and_user_message_kept(self):
        self.reply_status = 401
        resp = self.post({"action": "chat", "message": "Hello?"})
        self.assertEqual(resp.status_code, 502)
        self.assertIn("Invalid credentials", resp.json()["error"])
        self.assertEqual([m[0] for m in self.saved_messages()], ["assistant", "user"])
        # Regenerate then answers the kept message
        self.reply_status = 200
        self.post({"action": "regenerate"})
        self.assertEqual([m[0] for m in self.saved_messages()], ["assistant", "user", "assistant"])

    def test_emotion_detection_can_be_turned_off(self):
        from users.models import TaskSetting
        self.post({"action": "chat", "message": "Hi"})
        self.assertTrue(any("response_format" in c for c in self.all_calls))
        TaskSetting.objects.create(user=self.user, task="emotion", enabled=False)
        self.all_calls.clear()
        self.post({"action": "chat", "message": "Hi again"})
        self.assertFalse(any("response_format" in c for c in self.all_calls))

    def test_summary_append_only_covers_new_messages(self):
        self.post({"action": "chat", "message": "We enter the cave."})
        self.post({"action": "summarize", "mode": "append"})
        summary_call = self.all_calls[-1]["messages"][1]["content"]
        self.assertIn("We enter the cave.", summary_call)

        self.post({"action": "chat", "message": "A dragon wakes up."})
        self.post({"action": "summarize", "mode": "append"})
        summary_call = self.all_calls[-1]["messages"][1]["content"]
        self.assertIn("A dragon wakes up.", summary_call)
        self.assertNotIn("We enter the cave.", summary_call)

        resp = self.post({"action": "summarize", "mode": "append"})
        self.assertFalse(resp.json()["success"])  # nothing new

    def test_automatic_summary_is_flagged_when_due(self):
        from users.models import TaskSetting
        TaskSetting.objects.create(user=self.user, task="summary", mode="auto", interval=4)
        first = self.post({"action": "chat", "message": "One"}).json()  # greeting + 2 = 3 messages
        self.assertFalse(first["summary_due"])
        second = self.post({"action": "chat", "message": "Two"}).json()  # 5 messages
        self.assertTrue(second["summary_due"])

    def test_chat_page_redirects_without_connection(self):
        from users.models import ConnectionProfile
        ConnectionProfile.objects.filter(user=self.user).delete()
        resp = self.client.get(self.url)
        self.assertRedirects(resp, reverse("users:api_config") + f"?next={self.url}", fetch_redirect_response=False)


class TaskRoutingTests(TestCase):
    def setUp(self):
        from users.models import ConnectionProfile
        self.user = get_user_model().objects.create_user(username="router", password="pw12345!")
        self.main = ConnectionProfile.objects.create(user=self.user, name="Main", api_key="k1", model="big/model")
        self.cheap = ConnectionProfile.objects.create(user=self.user, name="Cheap", api_key="k2", model="small/model")

    def test_task_without_setting_uses_main(self):
        from mainapp.ai_client import resolve
        self.assertEqual(resolve(self.user, "summary"), (self.main, "big/model"))

    def test_task_follows_main_chat_model_override(self):
        from mainapp.ai_client import resolve
        from users.models import TaskSetting
        TaskSetting.objects.create(user=self.user, task="chat", profile=self.main, model="big/other")
        self.assertEqual(resolve(self.user, "summary"), (self.main, "big/other"))

    def test_task_with_own_profile_and_override(self):
        from mainapp.ai_client import resolve
        from users.models import TaskSetting
        TaskSetting.objects.create(user=self.user, task="summary", profile=self.cheap)
        self.assertEqual(resolve(self.user, "summary"), (self.cheap, "small/model"))
        TaskSetting.objects.filter(task="summary").update(model="small/v2")
        self.assertEqual(resolve(self.user, "summary"), (self.cheap, "small/v2"))

    def test_request_goes_to_profile_url_with_its_key(self):
        from unittest import mock
        from mainapp.ai_client import complete
        from users.models import ConnectionProfile, TaskSetting
        local = ConnectionProfile.objects.create(user=self.user, name="Local", provider="openai_compatible",
                                                 base_url="http://localhost:5001/v1/", model="local-model")
        TaskSetting.objects.create(user=self.user, task="emotion", profile=local)
        with mock.patch("mainapp.ai_client.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
            self.assertEqual(complete(self.user, "emotion", [], temperature=0, max_tokens=None), "ok")
        url, = post.call_args.args
        self.assertEqual(url, "http://localhost:5001/v1/chat/completions")
        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])
        self.assertEqual(post.call_args.kwargs["json"], {"model": "local-model", "messages": [], "temperature": 0})

    def test_error_inside_200_response(self):
        from unittest import mock
        from mainapp.ai_client import AIError, complete
        with mock.patch("mainapp.ai_client.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"error": {"message": "Model is overloaded"}}
            with self.assertRaisesMessage(AIError, "Model is overloaded"):
                complete(self.user, "chat", [])

    def test_no_connection(self):
        from mainapp.ai_client import NoConnection, complete
        other = get_user_model().objects.create_user(username="nobody", password="pw12345!")
        with self.assertRaises(NoConnection):
            complete(other, "chat", [])


class ConnectionsPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="conn", password="pw12345!")
        self.client.force_login(self.user)
        self.url = reverse("users:api_config")

    def save(self, data):
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def test_first_setup_and_key_kept_when_blank(self):
        from users.models import ConnectionProfile, TaskSetting
        resp = self.save({"profiles": [{"id": "new-1", "name": "Main", "provider": "openrouter",
                                        "api_key": "sk-or-secret-1234", "model": "a/b"}], "tasks": []})
        self.assertEqual(resp.status_code, 200, resp.content)
        profile = ConnectionProfile.objects.get(user=self.user)
        self.assertEqual(TaskSetting.objects.get(user=self.user, task="chat").profile, profile)
        # The key never goes back to the browser
        self.assertNotIn("sk-or-secret", resp.content.decode())
        self.assertNotIn("sk-or-secret", self.client.get(self.url).content.decode())

        self.save({"profiles": [{"id": profile.id, "name": "Main", "provider": "openrouter",
                                 "api_key": "", "model": "a/c"}], "tasks": []})
        profile.refresh_from_db()
        self.assertEqual((profile.api_key, profile.model), ("sk-or-secret-1234", "a/c"))

    def test_task_can_point_at_new_profile(self):
        from users.models import TaskSetting
        resp = self.save({
            "profiles": [
                {"id": "new-1", "name": "Main", "provider": "openrouter", "api_key": "k", "model": "big"},
                {"id": "new-2", "name": "Cheap", "provider": "openrouter", "api_key": "k", "model": "small"},
            ],
            "tasks": [{"task": "summary", "profile_id": "new-2", "model": "", "mode": "auto", "interval": 6}],
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        ts = TaskSetting.objects.get(user=self.user, task="summary")
        self.assertEqual((ts.profile.name, ts.mode, ts.interval), ("Cheap", "auto", 6))

    def test_validation(self):
        resp = self.save({"profiles": [{"id": "new-1", "name": "Main", "provider": "openrouter",
                                        "api_key": "", "model": "a/b"}]})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("API key", resp.json()["error"])
        resp = self.save({"profiles": [{"id": "new-1", "name": "Local", "provider": "openai_compatible",
                                        "base_url": "localhost", "model": "m"}]})
        self.assertIn("base URL", resp.json()["error"])

    def test_removing_profile_resets_tasks(self):
        from users.models import ConnectionProfile, TaskSetting
        self.save({"profiles": [
            {"id": "new-1", "name": "Main", "provider": "openrouter", "api_key": "k", "model": "big"},
            {"id": "new-2", "name": "Cheap", "provider": "openrouter", "api_key": "k", "model": "small"}],
            "tasks": [{"task": "summary", "profile_id": "new-2"}]})
        main = ConnectionProfile.objects.get(name="Main")
        self.save({"profiles": [{"id": main.id, "name": "Main", "provider": "openrouter", "model": "big"}],
                   "tasks": [{"task": "summary", "profile_id": None}]})
        self.assertIsNone(TaskSetting.objects.get(user=self.user, task="summary").profile)
        self.assertEqual(ConnectionProfile.objects.filter(user=self.user).count(), 1)
