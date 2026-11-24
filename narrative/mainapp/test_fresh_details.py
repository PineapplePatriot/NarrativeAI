"""🔁 Details that keep coming back in replies (fresh_details.py)."""
from django.test import SimpleTestCase

from mainapp import fresh_details as F


class FreshDetailsTests(SimpleTestCase):
    LAMP = [
        "The street lamp flickers above them as Pantalone counts the coins.",
        "Under the street lamp, he folds the letter twice.",
        "Anya waits. Somewhere a dog barks.",
        "The street lamp hums. He says nothing about the debt.",
        "He steps out of the street lamp's circle and lights a cigarette.",
    ]

    def test_street_lamp_hell_is_noticed(self):
        out = F.repeated(self.LAMP, theirs=["Where are we going?"], names=["Pantalone", "Anya"])
        self.assertEqual(out[0], "street lamp")
        self.assertNotIn("street", out)  # the pair stands for its words
        self.assertIn("street lamp", F.note(out))

    def test_names_and_their_own_topic_dont_count(self):
        replies = ["Pantalone smiles at the contract.", "Pantalone reads the contract again.",
                   "Pantalone signs the contract.", "Pantalone puts the contract away."]
        self.assertEqual(F.repeated(replies, names=["Pantalone"]), ["contract"])
        # they keep talking about the contract themselves: it's the topic, not a tic
        self.assertEqual(F.repeated(replies, theirs=["Sign the contract!"], names=["Pantalone"]), [])

    def test_a_detail_gone_from_the_newest_reply_is_left_alone(self):
        replies = self.LAMP[:4] + ["They walk on in silence toward the harbour."]
        self.assertNotIn("street lamp", F.repeated(replies))

    def test_too_few_replies_and_common_words(self):
        self.assertEqual(F.repeated(self.LAMP[:2]), [])
        self.assertEqual(F.repeated(["He said that it was there.", "She said that it was there.",
                                     "They said that it was there."]), [])

    def test_ukrainian(self):
        replies = ["Ліхтар над ними блимає.", "Під ліхтарем він мовчить.", "Ліхтар гуде.", "Знову ліхтар."]
        self.assertTrue(any(d.startswith("ліхтар") for d in F.repeated(replies)), F.repeated(replies))

    def test_the_note_goes_before_a_directors_note(self):
        msgs = [{"role": "user", "content": "Hi\n\n[Director's note for this reply, x]"}]
        out = F.add_before_note(msgs, "[Fresh details: x]")[-1]["content"]
        self.assertLess(out.index("[Fresh details"), out.index("[Director's note"))
        self.assertEqual(F.add_before_note(msgs, ""), msgs)



class TextureTests(SimpleTestCase):
    """🧵 The world texture library (mainapp/texture.py)."""
    def test_what_wakes_an_entry(self):
        from mainapp import texture as T
        ids = lambda text, mature=False: [e["id"] for e in T.woken(text, mature=mature)]
        self.assertEqual(ids("The heat of the day."), [])          # a short common word alone: nothing
        self.assertEqual(ids("a fight, blood everywhere"), [])
        self.assertEqual(ids("The vampire smelled blood."), ["vampires"])
        self.assertEqual(ids("Вона замовила борщ і вареники."), ["ukrainian_food"])
        self.assertEqual(ids("an omegaverse AU"), [])             # mature only
        self.assertEqual(ids("an omegaverse AU", mature=True), ["omegaverse"])
        self.assertLessEqual(len(T.woken("vampire coffee borscht royal court king laboratory", mature=True)), T.MOST)

    def test_the_note_varies_its_specifics(self):
        import random
        from mainapp import texture as T
        found = T.woken("They drank coffee at the café.")
        a, b = T.note(found, random.Random(1)), T.note(found, random.Random(2))
        self.assertIn("card and lorebook come first", a)
        self.assertIn("The tired version", a)
        self.assertNotEqual(a, b)
        self.assertEqual(T.note([]), "")

    def test_every_entry_is_complete(self):
        from mainapp import texture as T
        for e in T.entries():
            self.assertTrue(e["keys"] and e["gist"] and e["avoid"] and len(e["pool"]) >= 6, e["id"])
