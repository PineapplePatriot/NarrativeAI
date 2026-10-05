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

    def fake_post(self, url, headers=None, json=None, timeout=None, **kwargs):
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

    def saved_messages(self, chat=None):
        from mainapp import chats
        return chats.read(chat or self.character.chats.first())["messages"]

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
        self.assertRedirects(resp, reverse("users:welcome"), fetch_redirect_response=False)


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


class TrackerLogicTests(SimpleTestCase):
    def config(self, *ids, **extra):
        from mainapp.trackers import normalize_config
        return normalize_config({"trackers": {i: {"on": True} for i in ids}, **extra})

    def spec(self, tid, config=None):
        from mainapp.trackers import tracker_spec
        return tracker_spec(tid, config or self.config(tid))

    def test_defaults_only_world_on(self):
        from mainapp.trackers import enabled_trackers, normalize_config
        self.assertEqual([s["id"] for s in enabled_trackers(normalize_config({}))], ["world"])

    def test_object_merge_respects_locks(self):
        from mainapp.trackers import merge
        old = {"location": "Tavern", "weather": "Rain"}
        new = merge(self.spec("world"), old, {"location": "Docks", "weather": "Sun", "bogus": 1},
                    {"world.weather"})
        self.assertEqual(new, {"location": "Docks", "weather": "Rain"})

    def test_list_merge_locks_fields_and_keeps_locked_items(self):
        from mainapp.trackers import merge
        spec = self.spec("characters")
        old = [{"name": "Rose", "mood": "calm", "appearance": "", "outfit": "red coat", "thoughts": ""},
               {"name": "Guard", "mood": "bored", "appearance": "", "outfit": "", "thoughts": ""}]
        update = [{"name": "rose", "mood": "angry", "outfit": "nothing"}]  # Guard dropped
        locks = {"characters[rose].outfit", "characters[guard].mood"}
        result = merge(spec, old, update, locks)
        self.assertEqual([(i["name"], i["mood"], i["outfit"]) for i in result],
                         [("rose", "angry", "red coat"), ("Guard", "bored", "")])

    def test_coercion(self):
        from mainapp.trackers import coerce_tracker
        rel = coerce_tracker(self.spec("relationships"), [
            {"name": "Rose", "affection": "250", "trust": "about 40", "tension": None},
            {"name": "rose", "affection": 1},  # duplicate key
            {"affection": 5},                  # no key
        ])
        self.assertEqual(len(rel), 1)
        self.assertEqual((rel[0]["affection"], rel[0]["trust"], rel[0]["tension"]), (100, 40, 0))
        world = coerce_tracker(self.spec("world"), {"present": "Rose, Guard; Cat"})
        self.assertEqual(world["present"], ["Rose", "Guard", "Cat"])

    def test_custom_fields(self):
        from mainapp.trackers import coerce_tracker, enabled_trackers
        config = self.config("custom", custom_fields=[
            {"label": "Gold coins", "type": "number"}, {"label": "Sanity", "type": "meter", "min": 0, "max": 10},
            {"label": ""}, {"label": "Gold coins"}])
        self.assertEqual([f["key"] for f in config["custom_fields"]], ["gold_coins", "sanity", "gold_coins_"])
        spec = self.spec("custom", config)
        self.assertEqual(coerce_tracker(spec, {"gold_coins": "12 gp", "sanity": 99}), {"gold_coins": 12, "sanity": 10})
        # A custom tracker with no fields is not "on"
        self.assertNotIn("custom", [s["id"] for s in enabled_trackers(self.config("custom"))])

    def test_parse_update_tolerates_fences(self):
        from mainapp.trackers import parse_update
        self.assertEqual(parse_update('Sure!\n```json\n{"world": {"time": "dusk"}}\n```'), {"world": {"time": "dusk"}})
        with self.assertRaises(ValueError):
            parse_update("I cannot do that")

    def test_apply_update_only_and_prompt_text(self):
        from mainapp.trackers import apply_update, format_for_prompt, normalize_state
        config = self.config("world", "relationships")
        config["trackers"]["relationships"]["prompt"] = False
        state = normalize_state({}, config)
        changed = apply_update(config, state, {
            "world": {"location": "Lab", "present": ["Rose"]},
            "relationships": [{"name": "Rose", "trust": 30}],
            "stats": [{"name": "HP", "value": 3}],  # not enabled: ignored
        }, only=None)
        self.assertEqual(changed, ["world", "relationships"])
        text = format_for_prompt(config, state)
        self.assertIn("Location: Lab", text)
        self.assertNotIn("Rose: ", text)  # relationships not added to the prompt

        changed = apply_update(config, state, {"world": {"location": "Street"}, "relationships": []},
                               only=["relationships"])
        self.assertEqual(state["values"]["world"]["location"], "Lab")
        self.assertEqual(changed, ["relationships"])


class TrackerChatTests(ChatPromptTests):
    """Tracker actions in the chat view (reuses the fake AI from ChatPromptTests)."""

    def setUp(self):
        super().setUp()
        self.character.tracker_config = {"trackers": {"world": {"on": True}, "characters": {"on": True}}}
        self.character.save()
        self.tracker_reply = '{"world": {"location": "Alchemy lab", "weather": "storm"}}'

    def fake_post(self, url, headers=None, json=None, timeout=None):
        from unittest import mock
        if json["messages"][0]["content"].startswith("You keep the story-state trackers"):
            self.all_calls.append(json)
            resp = mock.Mock(status_code=200)
            resp.json.return_value = {"choices": [{"message": {"content": self.tracker_reply}}]}
            return resp
        return super().fake_post(url, headers, json, timeout)

    def test_update_save_lock_and_prompt(self):
        reply = self.post({"action": "chat", "message": "I step into the lab."}).json()
        self.assertTrue(reply["trackers_due"])  # default: automatic every 2 messages

        state = self.post({"action": "update_trackers"}).json()["state"]
        self.assertEqual(state["values"]["world"]["location"], "Alchemy lab")
        self.assertEqual(state["upto"], 3)

        # Lock the weather by hand, then the AI tries to change it
        state["values"]["world"]["weather"] = "clear"
        state["locks"] = ["world.weather"]
        self.post({"action": "save_trackers", "values": state["values"], "locks": state["locks"]})
        self.tracker_reply = '{"world": {"weather": "hail", "time": "midnight"}}'
        state = self.post({"action": "update_trackers"}).json()["state"]
        self.assertEqual(state["values"]["world"]["weather"], "clear")
        self.assertEqual(state["values"]["world"]["time"], "midnight")

        # The state reaches the main prompt
        self.post({"action": "chat", "message": "What time is it?"})
        system_text = "\n".join(m["content"] for m in self.sent[-1]["messages"] if m["role"] == "system")
        self.assertIn("Location: Alchemy lab", system_text)

    def test_bad_tracker_reply_is_reported(self):
        self.tracker_reply = "Sorry, I can't."
        resp = self.post({"action": "update_trackers"}).json()
        self.assertFalse(resp["success"])
        self.assertIn("JSON", resp["error"])

    def test_no_trackers_means_not_due(self):
        self.character.tracker_config = {"trackers": {"world": {"on": False}}}
        self.character.save()
        self.assertFalse(self.post({"action": "chat", "message": "Hi"}).json()["trackers_due"])

    def test_setup_page_saves_config(self):
        url = reverse("tracker_setup", args=[self.character.slug])
        self.assertEqual(self.client.get(url).status_code, 200)
        resp = self.client.post(url, json.dumps({"trackers": {"stats": {"on": True, "prompt": False}},
                                                 "layout": {"side": "left", "hud": False}}),
                                content_type="application/json")
        config = resp.json()["config"]
        self.assertTrue(config["trackers"]["stats"]["on"])
        self.assertFalse(config["trackers"]["stats"]["prompt"])
        self.assertEqual((config["layout"]["side"], config["layout"]["hud"]), ("left", False))


class SamplerTests(SimpleTestCase):
    def test_everything_off_by_default_and_clamped(self):
        from mainapp.samplers import normalize, to_api_params
        values = normalize({"temperature": {"on": True, "value": 9}, "top_k": {"value": "abc"}})
        self.assertEqual(values["temperature"], {"on": True, "value": 2})
        self.assertEqual(values["top_k"], {"on": False, "value": 0})
        self.assertEqual(to_api_params(normalize({}), "any/model"), ({}, []))

    def test_params_and_model_guard(self):
        from mainapp.samplers import normalize, to_api_params
        values = normalize({
            "temperature": {"on": True, "value": 0.7}, "top_p": {"on": True, "value": 0.9},
            "max_tokens": {"on": True, "value": 4000}, "context_size": {"on": True, "value": 8000},
            "reasoning_effort": {"on": True, "value": "high"}, "stop": {"on": True, "value": "\\nUser:, ###"},
        })
        params, skipped = to_api_params(values, "mistralai/mistral-large")
        self.assertEqual(params, {"temperature": 0.7, "top_p": 0.9, "max_tokens": 4000,
                                  "reasoning": {"effort": "high"}, "stop": ["\nUser:", "###"]})
        self.assertEqual(skipped, [])
        for model in ("anthropic/claude-opus-5.5", "anthropic/claude-opus-4.7", "anthropic/claude-sonnet-5.5",
                      "anthropic/claude-fable-5.1"):
            params, skipped = to_api_params(values, model)
            self.assertNotIn("temperature", params, model)
            self.assertEqual(sorted(skipped), ["temperature", "top_p"])
        for model in ("anthropic/claude-sonnet-4.6", "anthropic/claude-haiku-4.5"):
            self.assertIn("temperature", to_api_params(values, model)[0], model)
        # Opus 4.6 takes temperature only with thinking off (here thinking is on: effort "high")
        self.assertNotIn("temperature", to_api_params(values, "anthropic/claude-opus-4.6")[0])
        values["reasoning_effort"] = {"on": True, "value": "off"}
        self.assertEqual(to_api_params(values, "anthropic/claude-opus-4.6")[0]["temperature"], 0.7)

    def test_trim_history_keeps_newest_and_starts_with_user(self):
        from mainapp.samplers import normalize, trim_history
        system = [{"role": "system", "content": "s" * 300}]
        chat = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"{i} " + "x" * 297} for i in range(10)]
        values = normalize({"context_size": {"on": True, "value": 1024}})
        kept, dropped = trim_history(system, chat, values)
        self.assertEqual(kept[-1], chat[-1])
        self.assertEqual(kept[0]["role"], "user")
        self.assertEqual(dropped, len(chat) - len(kept))
        self.assertTrue(0 < len(kept) < len(chat))
        # Off = nothing trimmed
        self.assertEqual(trim_history(system, chat, normalize({}))[1], 0)


class SamplerChatTests(ChatPromptTests):
    def test_samplers_sent_as_parameters_not_prompt_text(self):
        from mainapp.models import ChatSettings
        ChatSettings.objects.create(author=self.user, samplers={
            "temperature": {"on": True, "value": 0.6}, "max_tokens": {"on": True, "value": 1234}})
        self.post({"action": "chat", "message": "Hello"})
        payload = self.sent[-1]
        self.assertEqual((payload["temperature"], payload["max_tokens"]), (0.6, 1234))
        self.assertNotIn("sampling", payload)
        self.assertFalse(any("[CORE SETTINGS]" in m["content"] for m in payload["messages"]))

    def test_sampler_page_saves(self):
        url = reverse("samplers")
        self.assertContains(self.client.get(url), "test/model")
        resp = self.client.post(url, json.dumps({"verbosity": {"on": True, "value": "low"}}),
                                content_type="application/json")
        self.assertEqual(resp.json()["samplers"]["verbosity"], {"on": True, "value": "low"})


ST_PRESET = {
    "temperature": 0.9, "top_p": 1, "top_k": 0, "openai_max_tokens": 900, "reasoning_effort": "auto",
    "squash_system_messages": False, "continue_nudge_prompt": "[Go on]", "assistant_prefill": "",
    "extensions": {"regex_scripts": [{"scriptName": "Pretty"}]}, "function_calling": True,
    "prompts": [
        {"identifier": "main", "name": "Main", "role": "system", "content": "You are {{char}}. {{getvar::tone}}"},
        {"identifier": "hdr", "name": "── Toggles", "role": "system", "content": ""},
        {"identifier": "tone", "name": "Grim tone", "role": "system", "content": "{{setvar::tone::Be grim.}}{{// note}}"},
        {"identifier": "nudge", "name": "Nudge", "role": "user", "content": "[Stay in character]",
         "injection_position": 1, "injection_depth": 0, "injection_order": 100},
        {"identifier": "deep", "name": "Deep", "role": "system", "content": "DEEP",
         "injection_position": 1, "injection_depth": 2},
        {"identifier": "chatHistory", "name": "Chat History", "marker": True},
        {"identifier": "charDescription", "name": "Char Description", "marker": True},
        {"identifier": "worldInfoAfter", "name": "World Info (after)", "marker": True},
        {"identifier": "jailbreak", "name": "Post-History", "role": "system", "content": "Reply as {{char}} only."},
        {"identifier": "orphan", "name": "Not in order", "content": "x"},
    ],
    "prompt_order": [
        {"character_id": 100000, "order": [{"identifier": "main", "enabled": True}]},
        {"character_id": 100001, "order": [
            {"identifier": "main", "enabled": True}, {"identifier": "charDescription", "enabled": True},
            {"identifier": "hdr", "enabled": True}, {"identifier": "tone", "enabled": True},
            {"identifier": "nudge", "enabled": True}, {"identifier": "deep", "enabled": True},
            {"identifier": "worldInfoAfter", "enabled": True},
            {"identifier": "chatHistory", "enabled": True}, {"identifier": "jailbreak", "enabled": True}]},
    ],
}
HISTORY = [{"role": "assistant", "content": "Hello."}, {"role": "user", "content": "Hi."},
           {"role": "assistant", "content": "What now?"}, {"role": "user", "content": "Let's go."}]
NAMES = {"char": "Rose", "user": "Ann"}


class PresetImportTests(SimpleTestCase):
    def test_sillytavern_import(self):
        from mainapp.presets import from_any
        preset, _ = from_any(ST_PRESET)
        kinds = [(b["id"], b["kind"]) for b in preset["blocks"]]
        self.assertEqual(kinds[:3], [("main", "prompt"), ("charDescription", "marker"), ("hdr", "header")])
        nudge = next(b for b in preset["blocks"] if b["id"] == "nudge")
        self.assertEqual((nudge["position"], nudge["depth"], nudge["role"]), ("in_chat", 0, "user"))
        s = preset["samplers"]
        self.assertEqual(s["temperature"], {"on": True, "value": 0.9})
        self.assertFalse(s["top_p"]["on"])       # neutral value: left off
        self.assertFalse(s["reasoning_effort"]["on"])  # "auto"
        self.assertEqual(s["max_tokens"], {"on": True, "value": 900})
        self.assertEqual(preset["utility"]["continue_nudge"], "[Go on]")
        self.assertTrue(preset["extras"]["function_calling"])
        self.assertEqual(preset["extras"]["unused_prompts"][0]["identifier"], "orphan")

    def test_round_trip(self):
        from mainapp.presets import from_any, to_sillytavern
        preset, _ = from_any(ST_PRESET)
        again, _ = from_any(to_sillytavern(preset))
        self.assertEqual(again["blocks"], preset["blocks"])
        self.assertEqual(again["samplers"], preset["samplers"])
        # Regex scripts come back complete (all SillyTavern fields filled in) and stay stable
        scripts = to_sillytavern(again)["extensions"]["regex_scripts"]
        self.assertEqual([r["scriptName"] for r in scripts], ["Pretty"])
        self.assertEqual(to_sillytavern(from_any(to_sillytavern(again))[0])["extensions"]["regex_scripts"], scripts)

    def test_native_round_trip_and_bad_file(self):
        from mainapp.presets import from_any, to_native
        preset, _ = from_any(ST_PRESET)
        again, name = from_any(to_native(preset, "Mine"))
        self.assertEqual((again, name), (preset, "Mine"))
        with self.assertRaises(ValueError):
            from_any({"hello": 1})


class MacroTests(SimpleTestCase):
    def run_macros(self, text, values=None):
        import random
        from mainapp.presets import MacroContext, expand
        ctx = MacroContext({"char": "Rose", "user": "Ann", "description": "", **(values or {})}, random.Random(3))
        expand(text, ctx, collect=True)
        return expand(text, ctx), ctx

    def test_variables_work_in_any_order(self):
        out, _ = self.run_macros("[{{getvar::mood}}]{{setvar::mood::calm}}")
        self.assertEqual(out, "[calm]")

    def test_conditionals(self):
        out, _ = self.run_macros("{{setvar::g::Noir}}{{#if .g}}G={{getvar::g}}{{/if}}"
                                 "{{#if .missing}}no{{else}}yes{{/if}}{{#if !description}}empty{{/if}}")
        self.assertEqual(out, "G=Noiryesempty")

    def test_misc_macros(self):
        out, ctx = self.run_macros("{{char}}/{{user}}{{// gone}}\n{{trim}}\nA{{noop}} {{roll: 1d1+2}} "
                                   "{{random::x::x}} {{random: y, y}} {{incvar::n}}{{incvar::n}}{{getvar::n}} {{madeup}}")
        self.assertEqual(out, "Rose/AnnA 3 x y 2 {{madeup}}")
        self.assertIn("madeup", ctx.unknown)


class PresetAssemblyTests(SimpleTestCase):
    def assemble(self, preset=None, model="some/model", **opts):
        import random
        from mainapp.presets import assemble, from_any
        preset = preset or from_any(ST_PRESET)[0]
        preset["options"].update(opts)
        return assemble(preset, {"char_description": "An alchemist.", "lore": "[Lore] Dragons exist."},
                        HISTORY, NAMES, model, random.Random(1))

    def test_order_slots_and_injections(self):
        r = self.assemble()
        roles = [(m["role"], m["content"][:12]) for m in r["messages"]]
        self.assertEqual(roles, [
            ("system", "You are Rose"), ("system", "An alchemist"), ("system", "[Lore] Drago"),
            ("assistant", "Hello."), ("user", "Hi."), ("system", "DEEP"), ("assistant", "What now?"),
            ("user", "Let's go."), ("user", "[Stay in cha"), ("system", "Reply as Ros")])
        self.assertEqual(r["messages"][0]["content"], "You are Rose. Be grim.")
        self.assertEqual(r["params"], {"temperature": 0.9, "max_tokens": 900})

    def test_disabled_blocks_and_missing_history(self):
        from mainapp.presets import from_any
        preset = from_any(ST_PRESET)[0]
        for b in preset["blocks"]:
            if b["id"] in ("tone", "chatHistory"):
                b["enabled"] = False
        r = self.assemble(preset)
        self.assertEqual(r["messages"][0]["content"], "You are Rose.")  # variable gone with its block
        self.assertNotIn("Let's go.", [m["content"] for m in r["messages"]])
        self.assertTrue(any("Chat history" in n for n in r["notes"]))

    def test_post_processing_modes(self):
        merged = self.assemble(post_processing="merge")["messages"]
        self.assertEqual(merged[0]["role"], "system")
        self.assertTrue(all(a["role"] != b["role"] for a, b in zip(merged, merged[1:])))

        strict = self.assemble(post_processing="strict")["messages"]
        self.assertEqual([m["role"] for m in strict][:2], ["system", "user"])
        self.assertEqual(sum(m["role"] == "system" for m in strict), 1)

        single = self.assemble(post_processing="single_user")["messages"]
        self.assertEqual(len(single), 1)
        self.assertEqual(single[0]["role"], "user")
        self.assertIn("Ann: Let's go.", single[0]["content"])
        self.assertIn("Rose: What now?", single[0]["content"])

    def test_prefill_dropped_for_models_that_reject_it(self):
        from mainapp.presets import from_any
        preset = from_any(ST_PRESET)[0]
        preset["utility"]["assistant_prefill"] = "*Rose*"
        self.assertEqual(self.assemble(preset, model="mistral/x")["messages"][-1],
                         {"role": "assistant", "content": "*Rose*"})
        r = self.assemble(from_any({**ST_PRESET, "assistant_prefill": "*Rose*"})[0], model="anthropic/claude-opus-5.5")
        self.assertNotEqual(r["messages"][-1]["role"], "assistant")
        self.assertTrue(any("prefill" in n for n in r["notes"]))
        self.assertNotIn("temperature", r["params"])


class DefaultPresetTests(TestCase):
    def setUp(self):
        import shutil
        import tempfile
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.media = media
        self.user = get_user_model().objects.create_user(username="pre", password="pw12345!")

    def test_fresh_user_gets_library_defaults(self):
        from mainapp.presets import get_active, normalize
        obj = get_active(self.user)
        preset = normalize(obj.data)
        names = {b["name"]: b for b in preset["blocks"]}
        self.assertTrue(names["System/Assistant Identity"]["enabled"])
        self.assertFalse(names["The Goth"]["enabled"])  # AVI voices start off
        self.assertEqual([b["marker"] for b in preset["blocks"] if b["kind"] == "marker"][-2:],
                         ["chat_history", "director_note"])
        self.assertEqual(get_active(self.user).id, obj.id)  # created once

    def test_old_settings_are_carried_over(self):
        import os
        from django.core.files.base import ContentFile
        from mainapp.models import ChatSettings
        from mainapp.presets import get_active, normalize
        cs = ChatSettings(author=self.user, samplers={"temperature": {"on": True, "value": 0.5}})
        cs.json_file.save("s.json", ContentFile(json.dumps({"prompts": {
            "system": "OLD MAIN", "jailbreak": "OLD JB", "continue": "Keep going!", "custom": {"c1": {"name": "Mine", "prompt": "CUSTOM"}}},
            "nsfw": {"styles": {"dark": {"name": "Dark", "prompt": "DARK"}}}}).encode()), save=True)
        os.makedirs(os.path.join(self.media, "chat_settings2"), exist_ok=True)
        with open(os.path.join(self.media, "chat_settings2", f"chat_settings2_{self.user.id}.json"), "w") as f:
            json.dump({"avis": {"goth": {"enabled": True, "content": "MY GOTH"}}}, f)
        preset = normalize(get_active(self.user).data)
        by_name = {b["name"]: b for b in preset["blocks"]}
        self.assertTrue(by_name["Main prompt"]["enabled"])
        self.assertTrue(by_name["Mine"]["enabled"])
        self.assertFalse(by_name["Dark"]["enabled"])
        self.assertEqual((by_name["The Goth"]["content"], by_name["The Goth"]["enabled"]), ("MY GOTH", True))
        self.assertFalse(by_name["System/Assistant Identity"]["enabled"])  # not on in the saved Prompting Ground
        names = [b["name"] for b in preset["blocks"]]
        self.assertGreater(names.index("Post-history instructions"), names.index("Chat history"))
        self.assertEqual(preset["utility"]["continue_nudge"], "Keep going!")
        self.assertEqual(preset["samplers"]["temperature"], {"on": True, "value": 0.5})


class PresetPageTests(ChatPromptTests):
    def page_post(self, data):
        return self.client.post(reverse("presets"), json.dumps(data), content_type="application/json")

    def test_import_activate_toggle_and_chat_uses_it(self):
        from mainapp.models import Preset
        self.assertEqual(self.client.get(reverse("presets")).status_code, 200)
        resp = self.page_post({"action": "import", "data": ST_PRESET, "name": "Tavern"}).json()
        tavern = Preset.objects.get(id=resp["selected"])
        self.assertFalse(tavern.is_active)
        self.page_post({"action": "activate", "id": tavern.id})
        self.page_post({"action": "save", "id": tavern.id, "enabled": {"jailbreak": False},
                        "post_processing": "merge"})

        self.post({"action": "chat", "message": "Hello there"})
        sent = self.sent[-1]
        text = "\n".join(m["content"] for m in sent["messages"])
        self.assertIn("You are Rose. Be grim.", text)
        self.assertNotIn("Reply as Rose only.", text)
        self.assertNotIn("[SYSTEM PROMPTS]", text)
        self.assertEqual(sent["temperature"], 0.9)

        preview = self.page_post({"action": "preview", "id": tavern.id, "character": self.character.slug}).json()
        self.assertTrue(preview["messages"])

        export = self.client.get(reverse("preset_export", args=[tavern.id]) + "?format=sillytavern")
        self.assertEqual(json.loads(export.content)["prompt_order"][0]["character_id"], 100001)

    def test_cannot_delete_last_preset(self):
        from mainapp.presets import get_active
        only = get_active(self.user)
        self.assertEqual(self.page_post({"action": "delete", "id": only.id}).status_code, 400)

    def test_samplers_page_edits_active_preset(self):
        from mainapp.presets import get_active
        self.client.post(reverse("samplers"), json.dumps({"max_tokens": {"on": True, "value": 777}}),
                         content_type="application/json")
        self.assertEqual(get_active(self.user).data["samplers"]["max_tokens"], {"on": True, "value": 777})


class PrefillGuardTests(SimpleTestCase):
    def test_chat_ending_with_character_turn_is_kept(self):
        import random
        from mainapp.presets import assemble, from_any
        preset = from_any(ST_PRESET)[0]
        preset["blocks"] = [b for b in preset["blocks"] if b["id"] in ("main", "chatHistory")]
        r = assemble(preset, {}, HISTORY[:3], NAMES, "anthropic/claude-opus-5.5", random.Random(1))
        self.assertEqual(r["messages"][-1], {"role": "assistant", "content": "What now?"})
        self.assertFalse(any("prefill" in n for n in r["notes"]))


class PresetEditorTests(ChatPromptTests):
    def page_post(self, data):
        return self.client.post(reverse("presets"), json.dumps(data), content_type="application/json")

    def test_save_full_edits_order_and_keeps_samplers_and_extras(self):
        from mainapp.models import Preset
        tavern_id = self.page_post({"action": "import", "data": ST_PRESET, "name": "Tavern"}).json()["selected"]
        preset = self.page_post({"action": "save", "id": tavern_id, "enabled": {}}).json()["preset"]
        blocks = preset["blocks"]
        blocks[0]["content"] = "EDITED {{char}}"
        blocks.reverse()
        blocks.append({"id": "new1", "kind": "prompt", "name": "Added", "content": "NEW", "role": "user",
                       "position": "in_chat", "depth": 1})
        resp = self.page_post({"action": "save_full", "id": tavern_id, "blocks": blocks,
                               "utility": {**preset["utility"], "assistant_prefill": "*Rose*"},
                               "options": {"post_processing": "strict"},
                               "samplers": {"temperature": {"on": False}}, "extras": {}})
        self.assertEqual(resp.status_code, 200, resp.content)
        saved = Preset.objects.get(id=tavern_id).data
        self.assertEqual(saved["blocks"][-1]["name"], "Added")
        self.assertEqual(saved["blocks"][-2]["content"], "EDITED {{char}}")
        self.assertEqual(saved["blocks"][-1]["position"], "in_chat")
        self.assertEqual(saved["utility"]["assistant_prefill"], "*Rose*")
        self.assertEqual(saved["options"]["post_processing"], "strict")
        self.assertTrue(saved["samplers"]["temperature"]["on"])          # not editable here
        self.assertEqual(saved["extras"]["function_calling"], True)    # kept

    def test_save_full_rejects_garbage(self):
        tavern_id = self.page_post({"action": "import", "data": ST_PRESET}).json()["selected"]
        self.assertEqual(self.page_post({"action": "save_full", "id": tavern_id, "blocks": "nope"}).status_code, 400)


def sse(*events):
    """Server-sent event lines as a provider would stream them."""
    lines = [": OPENROUTER PROCESSING", ""]
    for e in events:
        lines += ["data: " + (e if isinstance(e, str) else json.dumps(e)), ""]
    return lines


def delta(text):
    return {"choices": [{"delta": {"content": text}}]}


class StreamClientTests(TestCase):
    def setUp(self):
        from users.models import ConnectionProfile
        self.user = get_user_model().objects.create_user(username="streamer", password="pw12345!")
        ConnectionProfile.objects.create(user=self.user, name="Main", api_key="k", model="m")

    def run_stream(self, lines, status=200):
        from unittest import mock
        from mainapp import ai_client
        resp = mock.MagicMock(status_code=status)
        resp.iter_lines.return_value = lines
        resp.json.return_value = {"error": {"message": "bad key"}}
        resp.__enter__.return_value = resp
        with mock.patch("mainapp.ai_client.requests.post", return_value=resp) as post:
            out = list(ai_client.stream(self.user, "chat", [], max_tokens=10))
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        return out

    def test_pieces_in_order_and_done(self):
        out = self.run_stream(sse(delta("Hel"), {"choices": [{"delta": {}}]}, delta("lo"), "[DONE]", delta("ignored")))
        self.assertEqual(out, ["Hel", "lo"])

    def test_errors(self):
        from mainapp.ai_client import AIError
        with self.assertRaisesMessage(AIError, "overloaded"):
            self.run_stream(sse(delta("Hi"), {"error": {"message": "overloaded"}}))
        with self.assertRaisesMessage(AIError, "bad key"):
            self.run_stream([], status=401)


class StreamChatTests(ChatPromptTests):
    """The chat view streaming a reply (reuses the fake AI from ChatPromptTests)."""

    def setUp(self):
        super().setUp()
        self.stream_lines = sse(delta("Once "), delta("upon "), delta("a time."), "[DONE]")

    def fake_post(self, url, headers=None, json=None, timeout=None, **kwargs):
        from unittest import mock
        if not kwargs.get("stream"):
            return super().fake_post(url, headers, json, timeout)
        self.sent.append(json)
        resp = mock.MagicMock(status_code=200)
        resp.iter_lines.return_value = self.stream_lines
        resp.__enter__.return_value = resp
        return resp

    def stream_post(self, data):
        from unittest import mock
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            resp = self.client.post(self.url, json.dumps({**data, "stream": True}), content_type="application/json")
            events = [json.loads(line) for line in b"".join(resp.streaming_content).decode().splitlines() if line]
        return resp, events

    def test_streamed_reply_is_sent_and_saved(self):
        resp, events = self.stream_post({"action": "chat", "message": "Tell me a story"})
        self.assertEqual(resp["Content-Type"], "application/x-ndjson")
        self.assertEqual([e["text"] for e in events if e["type"] == "delta"], ["Once ", "upon ", "a time."])
        done = events[-1]
        self.assertEqual((done["type"], done["reply"]), ("done", "Once upon a time."))
        self.assertIn("summary_due", done)
        self.assertEqual(self.saved_messages()[-1][2], "Once upon a time.")

    def test_stop_keeps_partial_text(self):
        from unittest import mock
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            resp = self.client.post(self.url, json.dumps({"action": "chat", "message": "Go", "stream": True}),
                                    content_type="application/json")
            stream = iter(resp.streaming_content)
            next(stream)          # the first words arrive...
            resp.close()          # ...then the page stops reading
        saved = self.saved_messages()
        self.assertEqual([m[0] for m in saved], ["assistant", "user", "assistant"])
        self.assertEqual(saved[-1][2], "Once")

    def test_error_mid_stream_keeps_partial_and_reports(self):
        self.stream_lines = sse(delta("Half a "), {"error": {"message": "provider crashed"}})
        _, events = self.stream_post({"action": "chat", "message": "Go"})
        self.assertEqual(events[-1]["type"], "error")
        self.assertTrue(events[-1]["kept"])
        self.assertEqual(self.saved_messages()[-1][2], "Half a")

    def test_preset_can_turn_streaming_off(self):
        from mainapp.presets import get_active
        obj = get_active(self.user)
        obj.data = {**obj.data, "options": {**obj.data.get("options", {}), "streaming": False}}
        obj.save()
        from unittest import mock
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            resp = self.client.post(self.url, json.dumps({"action": "chat", "message": "Hi", "stream": True}),
                                    content_type="application/json")
        self.assertEqual(resp.json()["reply"], "A reply.")


class CharacterAccessTests(ChatPromptTests):
    def test_other_users_cannot_open_or_post_to_a_chat(self):
        from users.models import ConnectionProfile
        intruder = get_user_model().objects.create_user(username="intruder", password="pw12345!")
        ConnectionProfile.objects.create(user=intruder, name="Main", api_key="k", model="m")
        self.client.force_login(intruder)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        resp = self.client.post(self.url, json.dumps({"action": "chat", "message": "hi"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)  # to the login page


@override_settings(DEBUG=True)
class PrivateMediaTests(SimpleTestCase):
    def test_chat_logs_and_lorebooks_are_not_served(self):
        for path in ("/media/chat_logs/demo_rose_chat.json", "/media/worldbooks_json/x.json",
                     "/media/settings_json/a.json", "/media/chat_settings2/b.json"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class MultipleChatsTests(ChatPromptTests):
    def chat_url(self, chat):
        return f"{self.url}?chat={chat.id}"

    def post_to(self, chat, data):
        from unittest import mock
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            return self.client.post(self.chat_url(chat), json.dumps(data), content_type="application/json")

    def test_first_visit_creates_a_chat_with_the_greeting(self):
        self.client.get(self.url)
        self.assertEqual(self.character.chats.count(), 1)
        self.assertEqual(self.saved_messages()[0][2], "Hello, traveller.")

    def test_new_chat_starts_fresh_and_keeps_the_old_one(self):
        self.post({"action": "chat", "message": "First chat message"})
        first = self.character.chats.get()
        data = self.post({"action": "new_chat"}).json()
        second = self.character.chats.get(id=data["go_to"])
        self.assertEqual(len(data["chats"]), 2)
        self.assertEqual([m[2] for m in self.saved_messages(second)], ["Hello, traveller."])
        self.post_to(second, {"action": "chat", "message": "Second chat message"})
        self.assertIn("First chat message", [m[2] for m in self.saved_messages(first)])
        self.assertNotIn("Second chat message", [m[2] for m in self.saved_messages(first)])
        self.assertIn("Second chat message", [m[2] for m in self.saved_messages(second)])
        # The history sent to the model is only this chat's
        joined = "\n".join(m["content"] for m in self.sent[-1]["messages"])
        self.assertNotIn("First chat message", joined)

    def test_without_an_id_the_most_recent_chat_opens(self):
        self.client.get(self.url)
        first = self.character.chats.get()
        second_id = self.post({"action": "new_chat"}).json()["go_to"]
        self.post_to(first, {"action": "chat", "message": "Back to the first"})
        page = self.client.get(self.url)
        self.assertEqual(page.context["chat"].id, first.id)
        page = self.client.get(f"{self.url}?chat={second_id}")
        self.assertEqual(page.context["chat"].id, second_id)

    def test_rename_and_delete(self):
        self.client.get(self.url)
        first = self.character.chats.get()
        second_id = self.post({"action": "new_chat"}).json()["go_to"]
        data = self.post_to(first, {"action": "rename_chat", "id": second_id, "title": "  Side quest "}).json()
        self.assertIn("Side quest", [c["title"] for c in data["chats"]])
        path = first.log_file.path
        data = self.post_to(first, {"action": "delete_chat", "id": first.id}).json()
        self.assertEqual(data["go_to"], second_id)
        self.assertEqual(list(self.character.chats.values_list("id", flat=True)), [second_id])
        import os
        self.assertFalse(os.path.exists(path))

    def test_other_characters_chats_are_off_limits(self):
        from mainapp.models import Character
        self.client.get(self.url)
        other = Character.objects.create(name="Other", slug="other-chat-test", author=self.user)
        self.client.get(reverse("chat", args=[other.slug]))
        other_chat = other.chats.get()
        self.assertEqual(self.client.get(f"{self.url}?chat={other_chat.id}").status_code, 404)
        resp = self.post({"action": "delete_chat", "id": other_chat.id})
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(other.chats.exists())

    def test_old_single_log_becomes_chat_1(self):
        from django.core.files.base import ContentFile
        old = [["assistant", "10:00", "From the old days", "neutral"]]
        self.character.chat_log_file.save("old.json", ContentFile(json.dumps(old)), save=True)
        self.client.get(self.url)
        chat = self.character.chats.get()
        self.assertEqual(chat.title, "Chat 1")
        self.assertEqual(self.saved_messages(chat)[0][2], "From the old days")


class SwipeTests(ChatPromptTests):
    """Regenerate keeps the old reply as a swipe; ‹ › switch between them."""

    def setUp(self):
        super().setUp()
        self.replies = iter(f"Version {n}." for n in range(1, 20))

    def fake_post(self, url, headers=None, json=None, timeout=None, **kwargs):
        resp = super().fake_post(url, headers, json, timeout, **kwargs)
        if self.sent and self.sent[-1] is json and self.reply_status < 400:
            resp.json.return_value = {"choices": [{"message": {"content": next(self.replies)}}]}
        return resp

    def test_regenerate_adds_a_version_and_swipe_switches(self):
        self.post({"action": "chat", "message": "Hi"})
        data = self.post({"action": "regenerate"}).json()
        self.assertEqual(data["reply"], "Version 2.")
        self.assertEqual(data["swipes"], {"count": 2, "current": 1})
        saved = self.saved_messages()
        self.assertEqual(len(saved), 3)  # still one reply, not two
        self.assertEqual(saved[-1][2], "Version 2.")

        data = self.post({"action": "swipe", "to": 0}).json()
        self.assertEqual((data["reply"], data["swipes"]), ("Version 1.", {"count": 2, "current": 0}))
        self.assertEqual(self.saved_messages()[-1][2], "Version 1.")

        # The version on screen is what the AI sees next
        self.post({"action": "chat", "message": "And then?"})
        history = [m["content"] for m in self.sent[-1]["messages"]]
        self.assertIn("Version 1.", "\n".join(history))
        self.assertNotIn("Version 2.", "\n".join(history))

    def test_third_version_and_bad_index(self):
        self.post({"action": "chat", "message": "Hi"})
        self.post({"action": "regenerate"})
        data = self.post({"action": "regenerate"}).json()
        self.assertEqual(data["swipes"], {"count": 3, "current": 2})
        self.assertFalse(self.post({"action": "swipe", "to": 5}).json()["success"])

    def test_failed_regenerate_keeps_the_old_reply(self):
        self.post({"action": "chat", "message": "Hi"})
        self.reply_status = 401
        resp = self.post({"action": "regenerate"})
        self.assertEqual(resp.status_code, 502)
        saved = self.saved_messages()
        self.assertEqual((saved[-1][0], saved[-1][2]), ("assistant", "Version 1."))

    def test_edit_changes_the_shown_version_only(self):
        self.post({"action": "chat", "message": "Hi"})
        self.post({"action": "regenerate"})
        self.post({"action": "edit", "index": 2, "text": "Edited two."})
        self.assertEqual(self.post({"action": "swipe", "to": 0}).json()["reply"], "Version 1.")
        self.assertEqual(self.post({"action": "swipe", "to": 1}).json()["reply"], "Edited two.")

    def test_page_and_delete_report_the_counter(self):
        self.post({"action": "chat", "message": "Hi"})
        self.post({"action": "regenerate"})
        page = self.client.get(self.url)
        self.assertEqual(page.context["swipes"], {"count": 2, "current": 1})
        self.assertContains(page, "Version 2.")
        self.post({"action": "chat", "message": "More"})
        data = self.post({"action": "delete", "index": 3}).json()  # back to the swiped reply
        self.assertEqual(data["swipes"], {"count": 2, "current": 1})

    def test_swipe_only_on_the_ai_last_reply(self):
        self.post({"action": "chat", "message": "Hi"})
        self.post({"action": "delete", "index": 2})  # last message is now the user's
        self.assertFalse(self.post({"action": "swipe", "to": 0}).json()["success"])


class SwipeStreamTests(StreamChatTests):
    def test_stopped_regenerate_keeps_both(self):
        from unittest import mock
        self.stream_post({"action": "chat", "message": "Go"})
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            resp = self.client.post(self.url, json.dumps({"action": "regenerate", "stream": True}),
                                    content_type="application/json")
            stream = iter(resp.streaming_content)
            next(stream)
            resp.close()
        saved = self.saved_messages()
        self.assertEqual(saved[-1][2], "Once")
        self.assertEqual([v["text"] for v in saved[-1][5]["swipes"]], ["Once upon a time.", "Once"])

    def test_regenerate_stopped_before_any_text_keeps_the_old_reply(self):
        from unittest import mock
        self.stream_post({"action": "chat", "message": "Go"})
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            resp = self.client.post(self.url, json.dumps({"action": "regenerate", "stream": True}),
                                    content_type="application/json")
            iter(resp.streaming_content)
            resp.close()
        self.assertEqual(self.saved_messages()[-1][2], "Once upon a time.")


class SummaryPartsAndBranchTests(TrackerChatTests):
    """Summary pieces follow deletes, trackers rewind, and branches take what they need."""

    def setUp(self):
        super().setUp()
        self.summaries = iter(f"Summary {n}." for n in range(1, 20))

    def fake_post(self, url, headers=None, json=None, timeout=None, **kwargs):
        first = json["messages"][0]["content"]
        resp = super().fake_post(url, headers, json, timeout)
        if first.startswith(("Existing summary", "Summarize this entire")):
            resp.json.return_value = {"choices": [{"message": {"content": next(self.summaries)}}]}
        return resp

    def chat_file(self, chat=None):
        from mainapp import chats
        return chats.read(chat or self.character.chats.first())

    def build_story(self):
        """greeting, user, reply (summary 1 covers 3) + user, reply (summary 2 covers 5)."""
        self.post({"action": "chat", "message": "One"})
        self.post({"action": "summarize"})
        self.post({"action": "update_trackers"})          # snapshot at 3
        self.post({"action": "chat", "message": "Two"})
        self.post({"action": "summarize"})
        self.tracker_reply = '{"world": {"location": "Cellar"}}'
        self.post({"action": "update_trackers"})          # snapshot at 5

    def test_summary_is_kept_in_pieces(self):
        self.build_story()
        data = self.chat_file()
        self.assertEqual([(p["from"], p["to"]) for p in data["summary_parts"]], [(0, 3), (3, 5)])
        self.assertEqual(data["summary"], "Summary 1.\n\nSummary 2.")
        self.assertEqual(data["summary_upto"], 5)
        # The second run only sent the new messages, with the first piece as context
        call = [c for c in self.all_calls if c["messages"][0]["content"].startswith("Existing summary")][-1]
        self.assertIn("Summary 1.", call["messages"][0]["content"])
        self.assertNotIn("One", call["messages"][1]["content"])
        self.assertIn("Two", call["messages"][1]["content"])

    def test_delete_drops_summary_pieces_and_rewinds_trackers(self):
        self.build_story()
        resp = self.post({"action": "delete", "index": 4}).json()  # removes the second reply
        self.assertEqual(resp["summary"], "Summary 1.")
        self.assertEqual(resp["summary_upto"], 3)
        self.assertEqual(resp["trackers"]["values"]["world"]["location"], "Alchemy lab")
        data = self.chat_file()
        self.assertEqual(len(data["summary_parts"]), 1)
        self.assertEqual([s["at"] for s in data["tracker_history"]], [3])
        # Deleting into the first piece clears the summary
        resp = self.post({"action": "delete", "index": 1}).json()
        self.assertEqual((resp["summary"], resp["summary_upto"]), ("", 0))
        self.assertEqual(resp["trackers"]["values"], {})

    def test_regen_replaces_all_pieces(self):
        self.build_story()
        data = self.post({"action": "summarize", "mode": "regen"}).json()
        self.assertEqual(data["summary"], "Summary 3.")
        self.assertEqual([(p["from"], p["to"]) for p in self.chat_file()["summary_parts"]], [(0, 5)])

    def test_branch_info(self):
        self.build_story()
        info = self.post({"action": "branch_info", "index": 3}).json()  # messages 1-4
        self.assertEqual(info["count"], 4)
        self.assertEqual(info["summary"], "Summary 1.")  # piece 2 covered message 5
        self.assertTrue(info["has_trackers"])
        self.assertEqual(info["summary_model"], "test/model")
        self.assertFalse(self.post({"action": "branch_info", "index": 99}).json()["success"])

    def branch(self, **body):
        from unittest import mock
        original = self.character.chats.get(parent=None)  # the address names the chat in the browser
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            resp = self.client.post(f"{self.url}?chat={original.id}",
                                    json.dumps({"action": "branch", "index": 3, **body}),
                                    content_type="application/json").json()
        self.assertTrue(resp["success"], resp)
        from mainapp.models import Chat
        return Chat.objects.get(id=resp["go_to"])

    def test_branch_transfer(self):
        self.build_story()
        original = self.character.chats.get()
        branch = self.branch(summary_mode="transfer")
        self.assertEqual((branch.parent, branch.branch_point), (original, 4))
        self.assertEqual(branch.title, "Chat 1 ⑂ 1")
        data = self.chat_file(branch)
        self.assertEqual([m[2] for m in data["messages"]][1:], ["One", "A reply.", "Two"])
        self.assertEqual(data["summary"], "Summary 1.")
        self.assertEqual(data["trackers"]["values"]["world"]["location"], "Alchemy lab")
        # The original is untouched
        self.assertEqual(len(self.chat_file(original)["messages"]), 5)
        self.assertEqual(self.chat_file(original)["summary_upto"], 5)

    def test_branch_transfer_edited_rerun_and_clear(self):
        self.build_story()
        data = self.chat_file(self.branch(summary_mode="transfer", summary_text="My own words."))
        self.assertEqual(data["summary_parts"], [{"text": "My own words.", "from": 0, "to": 3}])
        calls = len(self.all_calls)
        data = self.chat_file(self.branch(summary_mode="rerun"))
        self.assertEqual(data["summary_parts"], [{"text": "Summary 3.", "from": 0, "to": 4}])
        self.assertEqual(len(self.all_calls), calls + 1)
        data = self.chat_file(self.branch(summary_mode="clear", trackers_mode="clear"))
        self.assertEqual((data["summary"], data["summary_parts"], data["trackers"]), ("", [], {}))
        self.assertEqual(self.character.chats.get(title="Chat 1").branches.count(), 3)

    def test_branch_keeps_swipes_and_page_shows_it(self):
        self.build_story()
        branch = self.branch(summary_mode="clear")
        page = self.client.get(f"{self.url}?chat={branch.id}")
        self.assertContains(page, "at message 4")
        self.assertEqual(page.context["chat"].id, branch.id)


class SummaryPanelTests(SummaryPartsAndBranchTests):
    def pieces(self):
        return [(p["from"], p["to"], p["text"]) for p in self.chat_file()["summary_parts"]]

    def test_range_edit_rerun_delete_and_gap(self):
        self.post({"action": "chat", "message": "One"})
        self.post({"action": "chat", "message": "Two"})   # 5 messages
        d = self.post({"action": "summarize", "to": 3}).json()
        self.assertEqual((d["first_uncovered"], d["total"]), (3, 5))
        self.post({"action": "summarize"})                 # the rest: 3-5
        self.assertEqual(self.pieces(), [(0, 3, "Summary 1."), (3, 5, "Summary 2.")])

        d = self.post({"action": "summary_edit", "piece": 0, "text": " Rose agreed. "}).json()
        self.assertEqual(d["summary"], "Rose agreed.\n\nSummary 2.")
        self.assertFalse(self.post({"action": "summary_edit", "piece": 0, "text": "  "}).json()["success"])

        self.post({"action": "summary_rerun", "piece": 1})
        self.assertEqual(self.pieces()[1], (3, 5, "Summary 3."))
        call = [c for c in self.all_calls if c["messages"][0]["content"].startswith("Existing summary")][-1]
        self.assertIn("Rose agreed.", call["messages"][0]["content"])  # earlier pieces as context

        # Deleting the first piece leaves a gap; the next run fills exactly the gap
        d = self.post({"action": "summary_delete", "piece": 0}).json()
        self.assertEqual((d["first_uncovered"], d["summary_upto"]), (0, 5))
        self.post({"action": "summarize"})
        self.assertEqual(self.pieces(), [(0, 3, "Summary 4."), (3, 5, "Summary 3.")])

    def test_bad_ranges(self):
        self.post({"action": "chat", "message": "One"})
        self.post({"action": "summarize"})
        self.assertEqual(self.post({"action": "summarize"}).json()["error"], "Nothing new to summarize yet.")
        self.assertFalse(self.post({"action": "summarize", "from": 1, "to": 3}).json()["success"])  # overlaps
        self.assertFalse(self.post({"action": "summarize", "from": 2, "to": 99}).json()["success"])
        self.assertFalse(self.post({"action": "summary_delete", "piece": 7}).json()["success"])

    def test_pause_stops_automatic_summaries(self):
        from users.models import TaskSetting
        TaskSetting.objects.create(user=self.user, task="summary", mode=TaskSetting.MODE_AUTO, interval=2)
        self.assertTrue(self.post({"action": "chat", "message": "One"}).json()["summary_due"])
        d = self.post({"action": "summary_pause", "paused": True}).json()
        self.assertTrue(d["paused"] and d["auto"])
        self.assertFalse(self.post({"action": "chat", "message": "Two"}).json()["summary_due"])
        # Manual runs still work while paused
        self.assertTrue(self.post({"action": "summarize"}).json()["success"])
        page = self.client.get(self.url)
        self.assertTrue(page.context["summary_data"]["paused"])


class ModelProfileTests(SimpleTestCase):
    """Per-model sampler rules (mainapp/data/models/*.json)."""

    def values(self, **on):
        from mainapp.samplers import normalize
        return normalize({k: {"on": True, "value": v} for k, v in on.items()})

    def test_every_profile_loads_and_names_only_real_samplers(self):
        from mainapp.model_profiles import all_profiles
        from mainapp.samplers import SAMPLERS_BY_KEY
        profiles = all_profiles()
        self.assertGreaterEqual(len(profiles), 2)
        for p in profiles:
            self.assertTrue(p["name"] and p["verified"] and p["sources"], p["id"])
            self.assertLessEqual(set(p["samplers"]), set(SAMPLERS_BY_KEY), p["id"])
            for rule in p["samplers"].values():
                self.assertIn(rule["status"], ("supported", "unverified", "fixed", "unused"))

    def test_profiles_match_openrouter_and_direct_ids(self):
        from mainapp.model_profiles import for_model
        self.assertEqual(for_model("anthropic/claude-opus-5-5")["id"], "claude-opus-5-5")
        self.assertEqual(for_model("anthropic/claude-opus-5.5")["id"], "claude-opus-5-5")
        self.assertEqual(for_model("xiaomi/mimo-v2.6-pro")["id"], "mimo-v2-6-pro")
        self.assertIsNone(for_model("anthropic/claude-sonnet-4.6"))
        self.assertIsNone(for_model(""))

    def test_opus_sends_only_what_it_uses(self):
        from mainapp.samplers import to_api_params
        params, skipped = to_api_params(self.values(
            temperature=0.7, max_tokens=900, frequency_penalty=0.3, seed=7, reasoning_effort="high"),
            "anthropic/claude-opus-5-5")
        self.assertEqual(params, {"max_tokens": 900, "reasoning": {"effort": "high"}})
        self.assertEqual(sorted(skipped), ["frequency_penalty", "seed", "temperature"])
        # an effort level the model doesn't have is not sent
        params, skipped = to_api_params(self.values(reasoning_effort="minimal"), "anthropic/claude-opus-5-5")
        self.assertEqual((params, skipped), ({}, ["reasoning_effort"]))

    def test_mimo_temperature_depends_on_thinking(self):
        from mainapp.samplers import to_api_params
        # thinking on by default: temperature and top-p are fixed by the model
        params, skipped = to_api_params(self.values(temperature=0.8, top_p=0.9), "xiaomi/mimo-v2.6-pro")
        self.assertEqual((params, sorted(skipped)), ({}, ["temperature", "top_p"]))
        # thinking off: both are sent, temperature capped at the model's 1.5
        params, skipped = to_api_params(self.values(temperature=1.9, top_p=0.9, reasoning_effort="off"),
                                        "xiaomi/mimo-v2.6-pro")
        self.assertEqual(params, {"temperature": 1.5, "top_p": 0.9, "reasoning": {"enabled": False}})
        self.assertEqual(skipped, [])

    def test_unknown_models_keep_the_old_behaviour(self):
        from mainapp.samplers import to_api_params
        params, skipped = to_api_params(self.values(temperature=0.7, min_p=0.1), "mistralai/mistral-large")
        self.assertEqual((params, skipped), ({"temperature": 0.7, "min_p": 0.1}, []))
        params, skipped = to_api_params(self.values(temperature=0.7), "anthropic/claude-fable-5.1")
        self.assertEqual((params, skipped), ({}, ["temperature"]))


class SamplerPageProfileTests(ChatPromptTests):
    def test_page_carries_the_profile(self):
        from users.models import ConnectionProfile
        ConnectionProfile.objects.filter(user=self.user).update(model="xiaomi/mimo-v2.6-pro")
        data = self.client.get(reverse("samplers")).context["sampler_data"]
        self.assertEqual(data["profile"]["name"], "MiMo v2.6 Pro")
        self.assertEqual(data["status"]["temperature"]["status"], "fixed")  # thinking on by default
        self.assertIn("Claude Opus 5.5", data["known_models"])


class StarterTests(ChatPromptTests):
    """Ready-made presets per model (mainapp/data/starters/*.json)."""

    def test_every_starter_is_a_sound_preset_for_its_model(self):
        from mainapp import model_profiles, presets, samplers, starters
        all_s = starters.all_starters()
        self.assertEqual(len(all_s), 30)  # three experiences for each of the ten models
        for s in all_s:
            profile = next(p for p in model_profiles.all_profiles() if p["id"] == s["model"])
            self.assertEqual(profile["starters"][s["experience"]], s["id"])
            preset = presets.normalize(s["preset"])
            markers = [b["marker"] for b in preset["blocks"] if b["kind"] == "marker"]
            self.assertIn("chat_history", markers, s["id"])
            # it sends nothing the model fixes or doesn't have
            model = profile["ids"]["openrouter"]
            params, skipped = samplers.to_api_params(preset["samplers"], model)
            self.assertEqual(skipped, [], s["id"])
            # every macro is known and the request assembles
            built = presets.assemble(preset, {"chat_history": True}, [{"role": "user", "content": "Hi"}],
                                     {"char": "Rose", "user": "Anya"}, model)
            self.assertFalse([n for n in built["notes"] if "nknown macro" in n], s["id"])
            text = "\n".join(m["content"] for m in built["messages"])
            self.assertIn("Rose", text)
            self.assertNotIn("{{", text, s["id"])
            # explicit content is opt-in
            mature = [b for b in preset["blocks"] if b["name"].startswith("Mature")]
            self.assertTrue(mature and not mature[0]["enabled"], s["id"])

    def test_using_a_starter_makes_an_active_copy_with_credit(self):
        from mainapp.models import Preset
        resp = self.client.post(reverse("presets"), json.dumps({"action": "use_starter", "starter": "mimo-rich-scene"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        obj = Preset.objects.get(id=resp.json()["selected"])
        self.assertTrue(obj.is_active)
        self.assertEqual(obj.name, "Rich scene · MiMo v2.6 Pro")
        self.assertEqual(obj.data["extras"]["starter"]["id"], "mimo-rich-scene")
        self.assertIn("rentry.org", obj.data["extras"]["starter"]["based_on"][0]["url"])
        # used twice: a second copy, not an overwrite
        resp = self.client.post(reverse("presets"), json.dumps({"action": "use_starter", "starter": "mimo-rich-scene"}),
                                content_type="application/json")
        self.assertEqual(Preset.objects.get(id=resp.json()["selected"]).name, "Rich scene · MiMo v2.6 Pro (2)")
        bad = self.client.post(reverse("presets"), json.dumps({"action": "use_starter", "starter": "nope"}),
                               content_type="application/json")
        self.assertEqual(bad.status_code, 400)

    def test_page_lists_the_users_model_first(self):
        from users.models import ConnectionProfile
        ConnectionProfile.objects.filter(user=self.user).update(model="anthropic/claude-opus-5-5")
        groups = self.client.get(reverse("presets")).context["preset_page"]["starters"]
        self.assertTrue(groups[0]["yours"])
        self.assertEqual(groups[0]["model_name"], "Claude Opus 5.5")
        self.assertEqual([s["title"] for s in groups[0]["starters"]], ["Back-and-forth", "Rich scene", "Director seat"])


class WelcomeTests(TestCase):
    """First run: an OpenRouter key and a chat model, nothing else."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="newbie", password="pw12345!")
        self.client.force_login(self.user)
        self.url = reverse("users:welcome")

    def post(self, data, ok=True):
        from unittest import mock
        with mock.patch("mainapp.ai_client.test_connection", return_value=(ok, "Key works." if ok else "OpenRouter rejected this key.")):
            return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def test_home_sends_new_users_here(self):
        self.assertRedirects(self.client.get(reverse("home")), self.url, fetch_redirect_response=False)

    def test_lists_ten_models_recommended_first(self):
        models = self.client.get(self.url).context["welcome_data"]["models"]
        self.assertEqual(len(models), 10)
        self.assertEqual([m["name"] for m in models[:2]], ["Claude Opus 5.5", "MiMo v2.6 Pro"])
        self.assertTrue(all(m["best_for"] and m["openrouter"] and m["price"] for m in models))

    def test_saving_sets_up_the_main_connection(self):
        from mainapp import ai_client
        resp = self.post({"api_key": "sk-or-test", "model": "mimo-v2-6-pro"})
        self.assertEqual(resp.json(), {"status": "ok", "model": "MiMo v2.6 Pro"})
        self.assertTrue(ai_client.has_connection(self.user))
        profile, model = ai_client.resolve(self.user, "chat")
        self.assertEqual((profile.api_key, model), ("sk-or-test", "xiaomi/mimo-v2.6-pro"))
        # changing the model later keeps the saved key
        self.post({"api_key": "", "model": "claude-opus-5-5"})
        profile, model = ai_client.resolve(self.user, "chat")
        self.assertEqual((profile.api_key, model), ("sk-or-test", "anthropic/claude-opus-5.5"))
        self.assertEqual(self.user.connection_profiles.count(), 1)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_bad_key_can_be_saved_anyway(self):
        resp = self.post({"api_key": "nope", "model": "kimi-k3"}, ok=False)
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.json()["can_skip"])
        self.assertFalse(self.user.connection_profiles.exists())
        resp = self.post({"api_key": "nope", "model": "kimi-k3", "skip_check": True}, ok=False)
        self.assertEqual(resp.status_code, 200)

    def test_needs_a_known_model_and_a_key(self):
        self.assertEqual(self.post({"api_key": "k", "model": "gpt-9"}).status_code, 400)
        self.assertEqual(self.post({"api_key": "", "model": "kimi-k3"}).status_code, 400)


class ExtrasTests(TestCase):
    """The plain-words feature switches."""

    def setUp(self):
        from users.models import ConnectionProfile
        self.user = get_user_model().objects.create_user(username="extra", password="pw12345!")
        self.main = ConnectionProfile.objects.create(user=self.user, name="Main", api_key="sk-or-x",
                                                     model="anthropic/claude-opus-5.5")
        self.client.force_login(self.user)
        self.url = reverse("users:extras")

    def post(self, data):
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def test_page_shows_current_settings(self):
        state = self.client.get(self.url).context["extras_data"]
        self.assertEqual(state["chat_model"], "Claude Opus 5.5")
        self.assertEqual(state["background"], "chat")
        self.assertEqual(state["trackers"]["mode"], "auto")  # the default
        self.assertTrue(all(m["price"] == "$" for m in state["cheap_models"]))

    def test_switches_save(self):
        from mainapp.ai_client import get_task_setting
        from users.models import ApiConfig
        state = self.post({"summary": {"mode": "auto", "interval": 12}, "trackers": {"mode": "manual", "interval": 3},
                           "sprites": False, "eleven_key": "el-key"}).json()["state"]
        self.assertEqual((state["summary"], state["trackers"]["mode"], state["sprites"], state["has_eleven_key"]),
                         ({"mode": "auto", "interval": 12}, "manual", False, True))
        self.assertFalse(get_task_setting(self.user, "emotion").enabled)
        self.post({"remove_eleven_key": True})
        self.assertEqual(ApiConfig.objects.get(user=self.user).eleven_key, "")

    def test_cheaper_background_model(self):
        from mainapp import ai_client
        state = self.post({"background": "mimo-v2-6-pro"}).json()["state"]
        self.assertEqual(state["background"], "mimo-v2-6-pro")
        for task in ("summary", "trackers", "emotion", "voice_split"):
            profile, model = ai_client.resolve(self.user, task)
            self.assertEqual((profile.name, profile.api_key, model), ("Background (cheaper)", "sk-or-x", "xiaomi/mimo-v2.6-pro"))
        self.assertEqual(ai_client.resolve(self.user, "chat")[1], "anthropic/claude-opus-5.5")  # chat untouched
        state = self.post({"background": "chat"}).json()["state"]
        self.assertEqual(state["background"], "chat")
        self.assertEqual(ai_client.resolve(self.user, "summary")[1], "anthropic/claude-opus-5.5")
        self.assertEqual(self.post({"background": "claude-opus-5-5"}).status_code, 400)  # not a cheap model


class BulbaTests(TestCase):
    """The setup assistant, with a scripted fake model (no network)."""

    def setUp(self):
        from users.models import ConnectionProfile
        self.user = get_user_model().objects.create_user(username="potato", password="pw12345!")
        self.main = ConnectionProfile.objects.create(user=self.user, name="Main", api_key="sk-or-secret",
                                                     model="anthropic/claude-opus-5.5")
        self.client.force_login(self.user)
        self.script = []      # replies Bulba's model gives, in order
        self.bulba_calls, self.sample_calls = [], []

    # -- fake AI ----------------------------------------------------------------
    @staticmethod
    def call(tool, **args):
        return {"id": f"call_{tool}_{len(json.dumps(args))}", "type": "function",
                "function": {"name": tool, "arguments": json.dumps(args)}}

    def fake_post(self, url, headers=None, json=None, timeout=None, **kwargs):
        from unittest import mock
        resp = mock.Mock(status_code=200)
        if "tools" in json:
            self.bulba_calls.append(json)
            content, calls = self.script.pop(0) if self.script else ("Okay.", [])
            message = {"role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})}
        else:
            self.sample_calls.append(json)
            message = {"role": "assistant", "content": f"Sample number {len(self.sample_calls)}."}
        resp.json.return_value = {"choices": [{"message": message}], "usage": {"cost": 0.01}}
        return resp

    def api(self, **body):
        from unittest import mock
        with mock.patch("mainapp.ai_client.requests.post", side_effect=self.fake_post):
            return self.client.post(reverse("bulba_api"), json.dumps(body), content_type="application/json")

    # -- tests ------------------------------------------------------------------
    def test_page_starts_a_session_with_a_free_opening(self):
        page = self.client.get(reverse("bulba"))
        data = page.context["bulba_data"]
        self.assertEqual(data["state"]["model"], "Claude Opus 5.5")
        self.assertEqual(data["state"]["stage"], "extras")
        self.assertIn("potato", data["events"][0]["text"])
        self.assertTrue(data["events"][0]["choices"])
        self.assertEqual(self.bulba_calls, [])  # starting costs nothing

    def test_unknown_model_gets_a_friendly_page(self):
        self.main.model = "some/other-model"
        self.main.save()
        self.assertIsNone(self.client.get(reverse("bulba")).context["bulba_data"])

    def test_bulba_runs_on_its_own_model_and_never_sees_keys(self):
        self.script = [("", [self.call("get_current_setup")]), ("You're on Opus. Voices?", [])]
        data = self.api(action="say", text="Hi").json()
        self.assertEqual(self.bulba_calls[0]["model"], "xiaomi/mimo-v2.6-pro")
        self.assertIn("tools", self.bulba_calls[0])
        self.assertNotIn("sk-or-secret", json.dumps(self.bulba_calls))
        self.assertEqual(self.bulba_calls[1]["messages"][-1]["role"], "tool")
        self.assertEqual([e["type"] for e in data["events"]], ["user", "bulba"])
        self.assertAlmostEqual(data["state"]["spent"], 0.02)

    def test_choices_and_preferences(self):
        self.script = [("Quiet or dramatic?", [
            self.call("offer_choices", choices=[{"label": "Quiet"}, {"label": "Dramatic"}]),
            self.call("record_preference", wording="short replies please", interpretation="Prefers short replies",
                      scope="general", status="confirmed")]), ("", [])]
        data = self.api(action="say", text="short replies please").json()
        bulba = [e for e in data["events"] if e["type"] == "bulba"][0]
        self.assertEqual([c["label"] for c in bulba["choices"]], ["Quiet", "Dramatic"])
        self.assertEqual(data["state"]["preferences"][0]["interpretation"], "Prefers short replies")
        pid = data["state"]["preferences"][0]["id"]
        data = self.api(action="forget", id=pid).json()
        self.assertEqual(data["state"]["preferences"], [])

    def test_samples_come_from_the_users_chat_model(self):
        self.script = [("Which reads better?", [self.call(
            "write_samples", starter="opus-rich-scene", scenario="A rainy museum after closing.",
            user_turn="Can you fix it?",
            variants=[{"label": "terse", "instructions": "Very terse."}, {"label": "lush", "instructions": "Lush detail."}])]),
            ("", [])]
        data = self.api(action="say", text="show me").json()
        samples = next(e for e in data["events"] if e["type"] == "samples")
        self.assertEqual([s["label"] for s in samples["samples"]], ["A", "B"])
        self.assertEqual(len(self.sample_calls), 2)
        for call in self.sample_calls:
            self.assertEqual(call["model"], "anthropic/claude-opus-5.5")  # the user's chat model
            system = "\n".join(m["content"] for m in call["messages"])
            self.assertIn("under 250 words", system)
            self.assertIn("Mara Voss", system)  # the neutral test character
        self.assertTrue(all(c["messages"][-1]["content"].startswith("Can you fix it?") for c in self.sample_calls))
        # The turn ends with the samples (the user picks next); Bulba sees which letter was which
        # variant in its history, while the page only shows letters
        self.assertEqual(len(self.bulba_calls), 1)
        from mainapp.models import BulbaSession
        history = BulbaSession.objects.get(user=self.user, active=True).messages
        tool_result = json.loads(history[-1]["content"])
        self.assertEqual({v["variant"] for v in tool_result["shown_to_user_as"].values()}, {"terse", "lush"})
        self.assertAlmostEqual(data["state"]["spent"], 0.03)

    def test_preset_proposal_apply_and_undo(self):
        from mainapp import presets as presets_mod
        before = presets_mod.get_active(self.user)
        self.script = [("Here's your preset.", [self.call(
            "propose_preset", starter="opus-back-and-forth", name="Banter setup",
            taste="Keep the teasing light.", reply_length="short", why="you like quick exchanges")])]
        data = self.api(action="say", text="build it").json()
        proposal = data["state"]["proposals"][0]
        self.assertEqual((proposal["kind"], proposal["status"]), ("preset", "pending"))
        self.assertEqual(presets_mod.get_active(self.user).id, before.id)  # nothing changes before Apply

        self.script = [("Applied. Now, who are you in the story?", [])]
        data = self.api(action="apply", id=proposal["id"]).json()
        self.assertEqual(data["state"]["proposals"][0]["status"], "applied")
        self.assertEqual(data["events"][0]["type"], "note")
        self.assertIn("[Applied: Preset: Banter setup]", json.dumps(self.bulba_calls[-1]["messages"]))
        active = presets_mod.get_active(self.user)
        self.assertEqual(active.name, "Banter setup")
        taste = next(b for b in active.data["blocks"] if b["name"] == "Your taste")
        self.assertIn("Keep the teasing light.", taste["content"])
        # Their length replaces the starter's own length rule: one rule, not two
        style = next(b for b in active.data["blocks"] if b["name"] == "Style")["content"]
        self.assertIn("Keep replies short: one to three paragraphs.", style)
        self.assertNotIn("Usually one to three short paragraphs", style)
        self.assertNotIn("paragraphs", taste["content"])

        self.script = [("Undone.", [])]
        self.api(action="undo", id=proposal["id"])
        self.assertEqual(presets_mod.get_active(self.user).id, before.id)
        from mainapp.models import Preset
        self.assertFalse(Preset.objects.filter(user=self.user, name="Banter setup").exists())

    def test_character_persona_and_extras_proposals(self):
        from mainapp.models import Character
        from mainapp.ai_client import get_task_setting
        self.script = [("", [
            self.call("propose_extras", summary="auto", summary_every=12, sprites=False, background="mimo-v2-6-pro", why="cheaper"),
            self.call("propose_persona", name="Anya", description="A tired courier."),
            self.call("propose_character", name="Dottore", description="A scholar first.", scenario="A lab.",
                      greeting="Hello there.")]), ("Three things to look at.", [])]
        data = self.api(action="say", text="go").json()
        extras, persona, character = data["state"]["proposals"]
        for p in (extras, persona, character):
            self.script = [("Done.", [])]
            self.api(action="apply", id=p["id"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.persona_name, "Anya")
        made = Character.objects.get(author=self.user, name="Dottore")
        self.assertEqual(made.initial_message, "Hello there.")
        self.assertEqual(get_task_setting(self.user, "summary").interval, 12)
        self.assertFalse(get_task_setting(self.user, "emotion").enabled)
        state = self.api(action="say", text="ok").json()["state"]
        self.assertEqual(next(p for p in state["proposals"] if p["kind"] == "character")["result"]["slug"], made.slug)
        # undo the character and the extras
        self.api(action="undo", id=character["id"])
        self.api(action="undo", id=extras["id"])
        self.assertFalse(Character.objects.filter(id=made.id).exists())
        self.assertTrue(get_task_setting(self.user, "emotion").enabled)
        self.assertEqual(get_task_setting(self.user, "summary").profile_id, None)
        # a handled proposal can't be applied again
        self.assertEqual(self.api(action="apply", id=character["id"]).status_code, 400)

    def test_budget_stops_bulba(self):
        self.client.get(reverse("bulba"))
        from mainapp.models import BulbaSession
        BulbaSession.objects.filter(user=self.user).update(spent=5.0)
        data = self.api(action="say", text="hello?").json()
        self.assertEqual(self.bulba_calls, [])
        self.assertIn("limit", data["events"][-1]["text"])
        data = self.api(action="budget", value=8).json()
        self.assertEqual(data["state"]["budget"], 8.0)

    def test_changing_model_starts_a_new_session(self):
        first = self.client.get(reverse("bulba")).context["bulba_data"]["state"]["id"]
        self.main.model = "xiaomi/mimo-v2.6-pro"
        self.main.save()
        state = self.client.get(reverse("bulba")).context["bulba_data"]["state"]
        self.assertNotEqual(state["id"], first)
        self.assertEqual(state["model"], "MiMo v2.6 Pro")


class BulbaGuideTests(BulbaTests):
    """Stage guides, starter rewrites, testing a proposal, transcripts."""

    def system_of(self, n=-1):
        return self.bulba_calls[n]["messages"][0]["content"]

    def test_guides_follow_the_stage(self):
        self.script = [("", [self.call("set_stage", stage="taste")]), ("What do you want to play?", [])]
        self.api(action="say", text="no voices")
        self.assertNotIn("Guide: finding out what they like", self.system_of(0))  # extras stage
        self.assertIn("Guide: finding out what they like", self.system_of(1))     # taste stage
        self.assertIn("Guide: writing their preset", self.system_of(1))
        self.assertNotIn("Guide: writing characters", self.system_of(1))
        self.assertIn("Model knowledge: Claude Opus 5.5", self.system_of(1))
        self.assertNotIn("{target_model}", self.system_of(1))

    def test_get_starter_and_rewrite(self):
        from mainapp import starters
        original = next(b["content"] for b in starters.get("opus-back-and-forth")["preset"]["blocks"] if b["name"] == "Roleplay")
        calmer = original.replace("Let the exchange spar", "Keep the exchange gentle")
        self.script = [("", [self.call("get_starter", starter="opus-back-and-forth")]),
                       ("", [self.call("propose_preset", starter="opus-back-and-forth", taste="Gentle.",
                                       rewrite={"Roleplay": "No placeholders here."})]),
                       ("", [self.call("propose_preset", starter="opus-back-and-forth", taste="Gentle.",
                                       rewrite={"Roleplay": calmer})]), ("Look it over.", [])]
        data = self.api(action="say", text="no banter please").json()
        got = json.loads(self.bulba_calls[1]["messages"][-1]["content"])
        self.assertIn("Let the exchange spar", got["sections"]["Roleplay"])
        rejected = json.loads(self.bulba_calls[2]["messages"][-1]["content"])
        self.assertIn("dropped", rejected["error"])
        proposal = data["state"]["proposals"][0]
        self.assertIn("Adjusted from the starter: Roleplay section", proposal["summary"])
        self.script = [("Done.", [])]
        self.api(action="apply", id=proposal["id"])
        from mainapp import presets as presets_mod
        active = presets_mod.get_active(self.user)
        roleplay = next(b["content"] for b in active.data["blocks"] if b["name"] == "Roleplay")
        self.assertIn("Keep the exchange gentle", roleplay)
        self.assertEqual(active.data["extras"]["starter"]["id"], "opus-back-and-forth")  # credit kept

    def test_sample_from_a_proposal_uses_exactly_that_preset(self):
        self.script = [("", [self.call("propose_preset", starter="opus-rich-scene", taste="Feelings stay unspoken.")])]
        pid = self.api(action="say", text="build it").json()["state"]["proposals"][0]["id"]
        self.script = [("", [self.call("write_samples", from_proposal=pid, scenario="A lab.", user_turn="Hi.",
                                       variants=[{"label": "final", "instructions": ""}])]), ("How's that?", [])]
        data = self.api(action="say", text="show me").json()
        system = "\n".join(m["content"] for m in self.sample_calls[0]["messages"] if m["role"] == "system")
        self.assertIn("Feelings stay unspoken.", system)
        self.assertEqual(len(next(e for e in data["events"] if e["type"] == "samples")["samples"]), 1)

    def test_transcript_download_has_no_keys(self):
        self.script = [("Hello.", [])]
        self.api(action="say", text="hi")
        resp = self.client.get(reverse("bulba_transcript"))
        self.assertEqual(resp["Content-Type"], "application/json")
        body = resp.content.decode()
        self.assertNotIn("sk-or-secret", body)
        data = json.loads(body)
        self.assertEqual(data["target_model"], "claude-opus-5-5")
        self.assertIn("Bulba", data["system_prompt"])
        self.assertEqual(data["events"][-1]["text"], "Hello.")


def _png(color=(200, 120, 90)):
    import io
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(out, "PNG")
    return out.getvalue()


def _card_png(card, keys=("chara",)):
    import base64
    from mainapp import cards
    text = base64.b64encode(json.dumps(card).encode("utf-8")).decode("ascii")
    return cards.embed_png(_png(), {k: text for k in keys})


V2_CARD = {
    "spec": "chara_card_v2", "spec_version": "2.0",
    "data": {
        "name": "Viktor", "description": "{{char}} is a stationmaster.", "personality": "Dry, careful.",
        "scenario": "The last train has gone.", "first_mes": "Excellent planning.",
        "mes_example": "<START>\n{{user}}: Worried?\n{{char}}: Checking the exits.\n<START>\n{{user}}: Hi.\n{{char}}: Hm.",
        "creator_notes": "Made for my friends. Don't send this to the model.",
        "system_prompt": "", "post_history_instructions": "",
        "alternate_greetings": ["You again.", "  "], "tags": ["Original", "Slow burn"],
        "creator": "Mari", "character_version": "1.2",
        "extensions": {"talkativeness": "0.5", "depth_prompt": {"prompt": "x", "depth": 4}},
        "character_book": {"name": "Station lore", "entries": [
            {"keys": ["platform"], "content": "Platform 9 is closed.", "enabled": True, "insertion_order": 10}]},
    },
}


class CardReadTests(SimpleTestCase):
    def test_v2_json(self):
        from mainapp import cards
        card, image = cards.read(json.dumps(V2_CARD).encode())
        self.assertIsNone(image)
        self.assertEqual(card["name"], "Viktor")
        self.assertEqual(card["first_mes"], "Excellent planning.")
        self.assertEqual(card["alternate_greetings"], ["You again."])
        self.assertEqual(card["tags"], ["Original", "Slow burn"])
        self.assertEqual(card["extra"]["extensions"]["talkativeness"], "0.5")
        self.assertEqual(card["character_book"]["name"], "Station lore")

    def test_v1_flat_json(self):
        from mainapp import cards
        card, _ = cards.read(json.dumps({"name": "Old", "description": "d", "first_mes": "hi",
                                         "personality": "p", "creatorcomment": "notes"}).encode())
        self.assertEqual((card["name"], card["personality"], card["creator_notes"]), ("Old", "p", "notes"))

    def test_png_prefers_ccv3(self):
        import base64
        from mainapp import cards
        v3 = {"spec": "chara_card_v3", "data": {**V2_CARD["data"], "name": "Viktor V3"}}
        png = cards.embed_png(_png(), {
            "chara": base64.b64encode(json.dumps(V2_CARD).encode()).decode(),
            "ccv3": base64.b64encode(json.dumps(v3).encode()).decode()})
        card, image = cards.read(png)
        self.assertEqual(card["name"], "Viktor V3")
        self.assertEqual(image, png)

    def test_pictures_without_a_card_explain_why(self):
        from mainapp import cards
        with self.assertRaisesMessage(cards.CardError, "no character card inside"):
            cards.read(_png())
        with self.assertRaisesMessage(cards.CardError, "WEBP/JPEG"):
            cards.read(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        with self.assertRaises(cards.CardError):
            cards.read(b'{"hello": "world"}')

    def test_examples_format(self):
        from mainapp import cards
        text = cards.format_examples(V2_CARD["data"]["mes_example"])
        self.assertEqual(text.count("[Example chat]"), 2)
        self.assertNotIn("<START>", text)
        self.assertEqual(cards.format_examples("  "), "")

    def test_card_prompts_replace_main_and_post_history(self):
        import random
        from mainapp.presets import assemble, from_any
        slots = {"card_system_prompt": "Card rules. {{original}}", "card_post_history": "Card ending."}
        r = assemble(from_any(ST_PRESET)[0], slots, HISTORY, NAMES, "some/model", random.Random(1))
        contents = [m["content"] for m in r["messages"]]
        self.assertEqual(contents[0], "Card rules. You are Rose. Be grim.")
        self.assertIn("Card ending.", contents)
        self.assertNotIn("Reply as Rose only.", contents)
        self.assertEqual(len([n for n in r["notes"] if "replaced" in n]), 2)

    def test_card_prompts_without_matching_blocks(self):
        import random
        from mainapp.presets import assemble, from_any
        preset = from_any(ST_PRESET)[0]
        preset["blocks"] = [b for b in preset["blocks"] if b["id"] not in ("main", "jailbreak")]
        r = assemble(preset, {"card_system_prompt": "Card rules. {{original}}", "card_post_history": "Card ending."},
                     HISTORY, NAMES, "some/model", random.Random(1))
        self.assertEqual(r["messages"][0]["content"], "Card rules.")
        self.assertEqual(r["messages"][-1]["content"], "Card ending.")


class CardImportTests(ChatPromptTests):
    def upload(self, raw, name="card.png"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(reverse("character_import"), {"card": SimpleUploadedFile(name, raw)})

    def test_png_import_creates_everything(self):
        from mainapp import chats
        from mainapp.models import Character
        response = self.upload(_card_png(V2_CARD))
        self.assertEqual(response.status_code, 200, response.content)
        viktor = Character.objects.get(name="Viktor", author=self.user)
        self.assertEqual(response.json()["url"], reverse("chat", args=[viktor.slug]))
        self.assertTrue(viktor.photo_neutral.name.endswith(".png"))
        self.assertEqual(viktor.personality, "Dry, careful.")
        self.assertEqual(viktor.card_creator, "Mari")
        self.assertEqual(sorted(t.tag for t in viktor.tags.all()), ["Original", "Slow burn"])
        self.assertEqual(viktor.worldbook.title, "Station lore")
        self.assertEqual(viktor.worldbook.author, self.user)
        self.assertEqual(len(response.json()["notes"]), 2)

        greeting = chats.greeting(viktor)[0]
        self.assertEqual(greeting[2], "Excellent planning.")
        self.assertEqual([v["text"] for v in greeting[5]["swipes"]], ["Excellent planning.", "You again."])

    def test_names_filled_in_greetings_and_pages(self):
        from mainapp import chats
        from mainapp.models import Character
        card = json.loads(json.dumps(V2_CARD))
        card["data"]["first_mes"] = "{{char}} nods at {{User}}. <USER> nods back."
        self.upload(_card_png(card))
        viktor = Character.objects.get(name="Viktor")
        self.assertEqual(chats.greeting(viktor)[0][2], "Viktor nods at chatter. chatter nods back.")
        page = self.client.get(reverse("characters_list"))
        self.assertContains(page, "Viktor is a stationmaster.")

    def test_bad_files_get_a_plain_error(self):
        response = self.upload(_png())
        self.assertEqual(response.status_code, 400)
        self.assertIn("no character card", response.json()["error"])
        self.assertEqual(self.client.post(reverse("character_import")).status_code, 400)

    def test_personality_and_examples_are_sent_but_not_creator_notes(self):
        from mainapp.models import Character
        self.upload(_card_png(V2_CARD))
        viktor = Character.objects.get(name="Viktor")
        self.url = reverse("chat", args=[viktor.slug])
        self.post({"action": "chat", "message": "Hello?"})
        joined = "\n".join(m["content"] for m in self.sent[-1]["messages"])
        self.assertIn("Dry, careful.", joined)
        self.assertNotIn("Don't send this to the model", joined)
        self.assertIn("Checking the exits.", joined)

    def test_export_round_trip(self):
        from mainapp import cards
        from mainapp.models import Character
        self.upload(_card_png(V2_CARD))
        viktor = Character.objects.get(name="Viktor")
        png = self.client.get(reverse("character_export", args=[viktor.slug])).content
        texts = cards.png_text(png)
        self.assertEqual(set(texts), {"chara", "ccv3"})
        card, _ = cards.read(png)
        for key in ("name", "description", "personality", "scenario", "first_mes", "mes_example",
                    "creator_notes", "creator", "character_version", "alternate_greetings"):
            self.assertEqual(card[key], cards.normalize(V2_CARD)[key], key)
        self.assertEqual(card["character_book"]["entries"][0]["content"], "Platform 9 is closed.")
        self.assertEqual(card["extra"]["extensions"]["talkativeness"], "0.5")

        as_json = self.client.get(reverse("character_export", args=[viktor.slug]) + "?format=json").json()
        self.assertEqual(as_json["spec"], "chara_card_v3")

        # A second import of the same card doesn't clash on slugs
        self.assertEqual(self.upload(png).status_code, 200)
        self.assertEqual(Character.objects.filter(name="Viktor").count(), 2)

    def test_export_without_picture_and_other_users(self):
        from mainapp import cards
        self.assertTrue(cards.png_text(self.client.get(reverse("character_export", args=[self.character.slug])).content))
        other = get_user_model().objects.create_user(username="other", password="pw12345!")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("character_export", args=[self.character.slug])).status_code, 404)

    def test_form_alternate_greetings(self):
        from mainapp.forms import AddCharacterForm
        form = AddCharacterForm(data={"name": "A", "alternate_greetings": "One\n<NEXT>\nTwo\r\n<NEXT>\n"},
                                user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["alternate_greetings"], ["One", "Two"])
        page = self.client.get(reverse("character", args=[self.character.slug]))
        self.assertContains(page, "Card details")
        self.assertContains(page, "download as .png card")


class SignUpFlowTests(TestCase):
    def test_sign_up_logs_in_and_goes_to_welcome(self):
        response = self.client.post(reverse("users:register"), {
            "username": "wren", "email": "wren@example.com",
            "password1": "Lantern-Quay-81", "password2": "Lantern-Quay-81"})
        self.assertRedirects(response, reverse("users:welcome"))
        self.assertEqual(self.client.get(reverse("users:welcome")).status_code, 200)  # signed in already


class BulbaOnboardingRunTests(BulbaTests):
    """Fixes from the first full onboarding run (5 October 2026)."""

    def session(self):
        from mainapp.models import BulbaSession
        return BulbaSession.objects.get(user=self.user, active=True)

    def test_choices_end_the_turn_without_another_call(self):
        self.script = [("Summaries: automatic, or only when you ask?",
                        [self.call("offer_choices", choices=[{"label": "Automatically"}, {"label": "When I ask"}])])]
        data = self.api(action="say", text="no voices").json()
        self.assertEqual(len(self.bulba_calls), 1)
        bubble = next(e for e in data["events"] if e["type"] == "bulba")
        self.assertEqual([c["label"] for c in bubble["choices"]], ["Automatically", "When I ask"])

    def test_extras_guide_in_the_extras_stage(self):
        self.script = [("Okay.", [])]
        self.api(action="say", text="no voices")
        self.assertIn("Guide: the extras", self.bulba_calls[0]["messages"][0]["content"])

    def test_empty_reply_is_not_stored(self):
        self.script = [("", [])]
        self.api(action="say", text="hello")
        self.assertFalse(any(m["role"] == "assistant" and not m.get("content") and not m.get("tool_calls")
                             for m in self.session().messages))

    def test_newer_proposal_replaces_the_pending_one(self):
        from mainapp.bulba import actions
        self.script = [("v1", [self.call("propose_persona", name="Wren", description="A farm kid.")])]
        self.api(action="say", text="call me Wren")
        self.script = [("v2", [self.call("propose_persona", name="Wren", description="A farm kid. She/her.")])]
        data = self.api(action="say", text="she/her").json()
        self.assertEqual([p["status"] for p in data["state"]["proposals"]], ["replaced", "pending"])
        old = data["state"]["proposals"][0]["id"]
        self.assertEqual(self.api(action="apply", id=old).status_code, 400)
        with self.assertRaises(actions.ProposalError):
            actions.apply(self.session(), old)

    def test_ids_let_bulba_confirm_a_guess(self):
        self.script = [("Noted.", [self.call("record_preference", wording="too nice", interpretation="Wants friction.",
                                             scope="general", status="tentative")])]
        self.api(action="say", text="everyone was too nice")
        first = self.session().preferences[0]["id"]
        self.script = [("Settled.", [self.call("record_preference", wording="B", interpretation="Wants friction.",
                                               scope="general", status="confirmed", replaces=first)])]
        data = self.api(action="say", text="B, he argues back").json()
        system = self.bulba_calls[-2]["messages"][0]["content"]
        self.assertIn(f"- {first} [tentative, general] Wants friction.", system)
        self.assertEqual([(p["status"]) for p in data["state"]["preferences"]], ["confirmed"])

    def test_length_rule_keeps_the_starters_ending(self):
        from mainapp.bulba.agent import build_preset
        preset = build_preset({"starter": "opus-rich-scene", "taste": "Push back.", "reply_length": "medium"})
        style = next(b for b in preset["blocks"] if b["name"] == "Style")["content"]
        self.assertIn("- Keep replies to about three to five paragraphs. End where {{user}} has something to answer.", style)
        self.assertNotIn("three to six", style)
        # A starter without a length line gets it in the taste section instead
        preset = build_preset({"starter": "mimo-rich-scene", "taste": "Push back.", "reply_length": "short"})
        taste = next(b for b in preset["blocks"] if b["name"] == "Your taste")["content"]
        self.assertIn("one to three paragraphs", taste)

    def test_names_filled_on_cards_the_user_reads(self):
        self.script = [("Look.", [self.call(
            "write_samples", starter="opus-rich-scene", scenario="{{user}}'s spell fizzles.", user_turn="Hm.",
            character={"name": "Corvin", "description": "A wizard."},
            variants=[{"label": "a", "instructions": ""}])])]
        data = self.api(action="say", text="show me").json()
        samples = next(e for e in data["events"] if e["type"] == "samples")
        self.assertEqual(samples["scenario"], "potato's spell fizzles.")
        self.script = [("Here.", [self.call("propose_character", name="Corvin", description="{{char}} teaches {{user}}.",
                                            greeting="Hi.")])]
        data = self.api(action="say", text="make him").json()
        self.assertIn("Corvin teaches potato.", data["state"]["proposals"][-1]["summary"])
        self.assertEqual(self.session().proposals[-1]["payload"]["description"], "{{char}} teaches {{user}}.")


class TaglineFilterTests(SimpleTestCase):
    def test_labels_are_dropped(self):
        from mainapp.templatetags.custom_filters import tagline
        self.assertEqual(tagline("Identity:\nCorvin is a wizard.\n\nAppearance:\nTall."), "Corvin is a wizard. Tall.")
        self.assertEqual(tagline("Identity: A wizard."), "A wizard.")
        self.assertEqual(tagline("Plain text: with a colon inside."), "Plain text: with a colon inside.")


ST_RULE = {"id": "r1", "scriptName": "Hide thinking", "findRegex": "/<think>[\\s\\S]*?<\\/think>\\s*/gi",
           "replaceString": "", "trimStrings": [], "placement": [2], "disabled": False,
           "markdownOnly": False, "promptOnly": True, "runOnEdit": False, "substituteRegex": 0,
           "minDepth": None, "maxDepth": None}


class RegexRuleTests(SimpleTestCase):
    names = {"char": "Rose", "user": "Ann"}

    def rule(self, **kw):
        from mainapp import regex_rules
        return regex_rules.normalize_rule({**ST_RULE, **kw})

    def run_one(self, rule, text, mode=None, role="assistant", depth=None):
        from mainapp import regex_rules
        return regex_rules.run([rule], mode or rule["mode"], text, role, self.names, depth)

    def test_sillytavern_format_round_trip(self):
        from mainapp import regex_rules
        r = self.rule()
        self.assertEqual((r["name"], r["mode"], r["placement"]), ("Hide thinking", "prompt", [2]))
        self.assertEqual(regex_rules.to_sillytavern(r), ST_RULE)
        self.assertEqual(self.rule(markdownOnly=True, promptOnly=False)["mode"], "display")
        self.assertEqual(self.rule(promptOnly=False)["mode"], "saved")

    def test_replacement_like_sillytavern(self):
        r = self.rule(findRegex="/(?<who>\\w+) waves/", replaceString="[$<who>|$1|{{match}}|{{user}}]", promptOnly=False)
        # No g flag: only the first match
        self.assertEqual(self.run_one(r, "Bob waves. Cy waves."), "[Bob|Bob|Bob waves|Ann]. Cy waves.")
        r = self.rule(findRegex="/(\\w+) waves/g", replaceString="$1!$2", promptOnly=False, trimStrings=["o"])
        self.assertEqual(self.run_one(r, "Bob waves. Cy waves."), "Bb!. Cy!.")

    def test_javascript_syntax_translated(self):
        r = self.rule(findRegex="/(?<a>q)[^]x\\k<a>\\e/", replaceString="-", promptOnly=False)
        from mainapp import regex_rules
        self.assertIsNone(regex_rules.check(r))
        r = self.rule(findRegex="/\\d+/g", replaceString="#", promptOnly=False)
        self.assertEqual(self.run_one(r, "a1 b٣ c22"), "a# b٣ c#")  # JavaScript's \d is ASCII only

    def test_macros_in_find(self):
        r = self.rule(findRegex="/{{char}}:/g", replaceString="", substituteRegex=1, promptOnly=False)
        self.assertEqual(self.run_one(r, "Rose: hi"), " hi")

    def test_where_and_when(self):
        r = self.rule()
        self.assertEqual(self.run_one(r, "<think>x</think>Hi"), "Hi")
        self.assertEqual(self.run_one(r, "<think>x</think>Hi", role="user"), "<think>x</think>Hi")
        self.assertEqual(self.run_one(r, "<think>x</think>Hi", mode="saved"), "<think>x</think>Hi")
        deep = self.rule(minDepth=2)
        self.assertEqual(self.run_one(deep, "<think>x</think>Hi", depth=1), "<think>x</think>Hi")
        self.assertEqual(self.run_one(deep, "<think>x</think>Hi", depth=2), "Hi")
        off = self.rule(disabled=True)
        self.assertEqual(self.run_one(off, "<think>x</think>Hi"), "<think>x</think>Hi")

    def test_history_depth(self):
        from mainapp import regex_rules
        rule = self.rule(findRegex="/\\[STATE\\][\\s\\S]*?\\[\\/STATE\\]/g", minDepth=1)
        history = [{"role": "assistant", "content": "A [STATE]old[/STATE]"},
                   {"role": "user", "content": "B"},
                   {"role": "assistant", "content": "C [STATE]new[/STATE]"}]
        out = regex_rules.run_on_history([rule], history, self.names)
        self.assertEqual([m["content"] for m in out], ["A ", "B", "C [STATE]new[/STATE]"])

    def test_preset_import_export_keeps_rules(self):
        from mainapp.presets import from_any, normalize, to_sillytavern
        st = json.loads(json.dumps(ST_PRESET))
        st["extensions"] = {"regex_scripts": [ST_RULE], "other": 1}
        preset = from_any(st)[0]
        self.assertEqual([r["name"] for r in preset["regex"]], ["Hide thinking"])
        self.assertEqual(preset["extras"]["extensions"], {"other": 1})
        out = to_sillytavern(preset)
        self.assertEqual(out["extensions"]["regex_scripts"], [ST_RULE])
        self.assertEqual(out["extensions"]["other"], 1)
        # Presets imported before rules existed: lifted out of extras
        old = normalize({"blocks": [], "extras": {"extensions": {"regex_scripts": [ST_RULE]}}})
        self.assertEqual(len(old["regex"]), 1)
        self.assertNotIn("regex_scripts", old["extras"]["extensions"])


class RegexChatTests(ChatPromptTests):
    def setUp(self):
        super().setUp()
        from mainapp import presets as presets_mod
        obj = presets_mod.get_active(self.user)
        data = presets_mod.normalize(obj.data)
        data["regex"] = [
            {**ST_RULE},  # prompt: drop <think> from what's sent back
            {**ST_RULE, "id": "r2", "scriptName": "Shout", "findRegex": "/quiet/g", "replaceString": "LOUD",
             "promptOnly": False},  # saved, AI replies
            {**ST_RULE, "id": "r3", "scriptName": "Card", "findRegex": "/\\[HP:(\\d+)\\]/g",
             "replaceString": "<div class=\"hp\">$1</div>", "promptOnly": False, "markdownOnly": True},
            {**ST_RULE, "id": "r4", "scriptName": "Typos", "findRegex": "/teh/g", "replaceString": "the",
             "promptOnly": False, "placement": [1]},
        ]
        obj.data = presets_mod.normalize(data)
        obj.save()
        self.reply_text = "<think>plan</think>A quiet reply. [HP:5]"

    def fake_post(self, url, headers=None, json=None, timeout=None, **kwargs):
        resp = super().fake_post(url, headers=headers, json=json, timeout=timeout, **kwargs)
        if self.reply_status < 400 and not (json and "response_format" in json):
            resp.json.return_value = {"choices": [{"message": {"content": self.reply_text}}]}
        return resp

    def test_rules_in_a_chat(self):
        self.post({"action": "chat", "message": "teh tower?"})
        saved = self.saved_messages()
        self.assertEqual(saved[-2][2], "the tower?")                              # saved rule, your messages
        self.assertEqual(saved[-1][2], "<think>plan</think>A LOUD reply. [HP:5]")  # saved rule, AI replies
        self.post({"action": "chat", "message": "go on"})
        sent = "\n".join(m["content"] for m in self.sent[-1]["messages"])
        self.assertNotIn("<think>", sent)                                         # prompt rule
        self.assertIn("A LOUD reply. [HP:5]", sent)                                # display rule isn't sent
        page = self.client.get(self.url)
        rules = page.context["display_rules"]["rules"]
        self.assertEqual([r["name"] for r in rules], ["Card"])

    def test_card_rules_join_the_preset_rules(self):
        from mainapp import presets as presets_mod, regex_rules
        self.character.card_data = {"extensions": {"regex_scripts": [{**ST_RULE, "id": "c1", "scriptName": "Card rule"}]}}
        self.character.save()
        rules = regex_rules.for_chat(presets_mod.normalize(presets_mod.get_active(self.user).data), self.character)
        self.assertEqual(rules[-1]["name"], "Card rule")

    def test_presets_page_actions(self):
        from mainapp import presets as presets_mod
        obj = presets_mod.get_active(self.user)
        url = reverse("presets")
        post = lambda body: self.client.post(url, json.dumps(body), content_type="application/json")
        data = post({"action": "test_rule", "id": obj.id, "rule": ST_RULE, "text": "<think>a</think>Hi"}).json()
        self.assertEqual((data["result"], data["problem"]), ("Hi", None))
        bad = post({"action": "test_rule", "id": obj.id, "rule": {**ST_RULE, "findRegex": "/(unclosed/"}, "text": "x"}).json()
        self.assertIn("Can't run", bad["problem"])
        imported = post({"action": "import_rules", "id": obj.id, "data": ST_RULE}).json()
        self.assertEqual(len(imported["rules"]), 1)
        current = presets_mod.normalize(obj.data)
        post({"action": "save_full", "id": obj.id, "blocks": current["blocks"], "regex": [ST_RULE]})
        obj.refresh_from_db()
        self.assertEqual([r["name"] for r in presets_mod.normalize(obj.data)["regex"]], ["Hide thinking"])
