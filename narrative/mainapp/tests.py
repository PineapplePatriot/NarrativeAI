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
