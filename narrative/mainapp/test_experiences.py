from django.test import SimpleTestCase, TestCase
from mainapp import experiences, starters, presets, writing_quality
from mainapp.bulba import agent, control


class ExperienceTests(SimpleTestCase):
    def test_catalog_has_three_original_experiences_per_model(self):
        self.assertEqual(len(starters.all_starters()), 48)  # four styles for eleven models and "Any model"
        for s in starters.all_starters():
            self.assertIn(s['experience'], experiences.EXPERIENCES)
            self.assertEqual(s['based_on'], [])
            self.assertEqual(control.mode_of(presets.normalize(s['preset'])), 'dont')
            names = {b.get('name'): b for b in s['preset']['blocks']}
            for name in ('Roleplay', 'Writing quality', 'Reply length', 'Reply reminder'):
                self.assertTrue(names[name]['enabled'])
            if s['model'] != 'any-model':
                self.assertTrue(names['Model pattern counters']['enabled'])
            for name in ('Adventure & Ensemble', 'Continuity & Simulation'):
                self.assertFalse(names[name]['enabled'])
            self.assertNotIn('Director seat', s['title'])

    def test_every_experience_supports_every_authorship_mode(self):
        for s in starters.all_starters():
            for mode in experiences.CONTRACTS:
                data = agent.build_preset({'starter': s['id'], 'control': mode,
                    'extensions': ['adventure'], 'taste': 'Use long, reflective narration.'})
                self.assertEqual(control.mode_of(data), mode)
                self.assertEqual(len([b for b in data['blocks'] if b['name'] == control.BLOCK]), 1)
                self.assertTrue(next(b for b in data['blocks'] if b['name'] == 'Adventure & Ensemble')['enabled'])
                self.assertFalse(next(b for b in data['blocks'] if b['name'] == 'Continuity & Simulation')['enabled'])
                if s['model'] != 'any-model':  # no notes, so no model counter
                    self.assertTrue(next(b for b in data['blocks'] if b.get('id') == writing_quality.COUNTER_ID)['enabled'])

    def test_mode_changes_preserve_extension_selection(self):
        s = starters.get('mimo-experience-drama')
        data = experiences.configure(presets.normalize(s['preset']), 'dont', ['continuity'])
        for mode in ('write', 'director', 'dont'):
            data = control.apply_to_preset(data, mode)
            self.assertEqual(control.mode_of(data), mode)
            self.assertTrue(next(b for b in data['blocks'] if b['name'] == 'Continuity & Simulation')['enabled'])

    def test_model_routing_is_research_default_not_experience(self):
        d = experiences.catalog()
        for s in starters.all_starters():
            expected = 'narrative' if s['model'].startswith(('claude', 'gemini', 'mimo', 'any-')) else 'structured'
            self.assertEqual(s['preset']['extras']['original_experience']['foundation'], expected)
            self.assertEqual(experiences.base_of(s['model']), expected)

    def test_invalid_options_fail_before_a_preset_is_saved(self):
        data = starters.get('mimo-experience-storytelling')['preset']
        for mode, extensions in [('oops', []), ('dont', ['unknown']), ('dont', 'adventure'), ('dont', [{}])]:
            with self.assertRaises(ValueError):
                experiences.configure(data, mode, extensions)

    def test_legacy_links_and_community_artifacts_still_resolve(self):
        for sid in ('mimo-rich-scene', 'opus-director', 'mimo-frankenstein'):
            self.assertIsNotNone(starters.get(sid))
        self.assertNotIn('mimo-frankenstein', {s['id'] for s in starters.all_starters()})


from django.contrib.auth import get_user_model
from django.test import TestCase


class ExperiencePersistenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='experience-reader')

    def test_switching_experience_preserves_explicit_mode_and_old_preset(self):
        first = starters.apply(self.user, 'mimo-experience-drama', mode='director', extensions=['continuity'])
        original = first.data.copy()
        second = starters.apply(self.user, 'mimo-experience-conversation')
        self.assertEqual(control.mode_of(second.data), 'director')
        first.refresh_from_db()
        self.assertEqual(first.data, original)
        third = starters.apply(self.user, 'mimo-experience-storytelling', mode='dont')
        self.assertEqual(control.mode_of(third.data), 'dont')

    def test_invalid_authorship_does_not_create_new_preset(self):
        from mainapp.models import Preset
        starters.apply(self.user, 'mimo-experience-conversation')
        before = Preset.objects.filter(user=self.user).count()
        with self.assertRaises(ValueError):
            starters.apply(self.user, 'mimo-experience-drama', mode='invalid')
        self.assertEqual(Preset.objects.filter(user=self.user).count(), before)

    def test_presets_api_accepts_independent_mode_and_extensions(self):
        import json
        from django.urls import reverse
        from mainapp.models import Preset
        self.client.force_login(self.user)
        response = self.client.post(reverse('presets'), json.dumps({'action':'use_starter',
            'starter':'mimo-experience-conversation', 'control':'write', 'extensions':['adventure']}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        obj = Preset.objects.get(id=response.json()['selected'])
        self.assertEqual(control.mode_of(obj.data), 'write')
        self.assertTrue(next(b for b in obj.data['blocks'] if b['name']=='Adventure & Ensemble')['enabled'])
        self.assertEqual(obj.data['extras']['original_experience']['id'], 'conversation')


class ExperienceBuildTests(SimpleTestCase):
    """The family bases, modules, 18+ rule, reminder and length in the generated presets."""

    def blocks(self, sid):
        return {b.get('name'): b for b in starters.get(sid)['preset']['blocks']}

    def test_family_bases_carry_the_never_write_list_and_the_ooc_rule(self):
        story, rules = self.blocks('opus-experience-drama')['Roleplay'], self.blocks('kimi-experience-drama')['Roleplay']
        self.assertIn('# How this story is written', story['content'])
        self.assertIn('## Knowledge', rules['content'])
        for text in (story['content'], rules['content']):
            self.assertIn('## Never write these', text)
            self.assertIn('dust motes', text)
            self.assertIn('OOC are notes to you', text)
        self.assertNotIn('Model foundation', self.blocks('opus-experience-drama'))

    def test_modules_default_on_and_off_and_argon_gets_lighter_friction(self):
        b = self.blocks('mimo-experience-conversation')
        for name in ('Friction', 'No therapy talk', 'Busy world'):
            self.assertTrue(b[name]['enabled'], name)
        for name in ('Kindness guard', 'OOC co-author', 'Explicit intimacy (18+)', 'Adventure & Ensemble'):
            self.assertFalse(b[name]['enabled'], name)
        self.assertIn('Keep it proportionate', self.blocks('argon-experience-drama')['Friction']['content'])
        self.assertNotIn('Keep it proportionate', b['Friction']['content'])

    def test_strong_mature_rule_off_until_switched_and_reminder_at_the_end(self):
        from mainapp import mature
        data = presets.normalize(starters.get('gemini-experience-storytelling')['preset'])
        block = next(b for b in data['blocks'] if b['name'].startswith('Mature content'))
        self.assertEqual((block['content'], block['enabled']), (mature.BLOCK_TEXT, False))
        reminder = next(b for b in data['blocks'] if b['name'] == 'Reply reminder')
        self.assertEqual((reminder['role'], reminder['position'], reminder['depth']), ('user', 'in_chat', 0))
        on = mature.set_on(data, True)
        text = next(b for b in on['blocks'] if b['name'] == 'Reply reminder')['content']
        self.assertIn(mature.REMINDER_LINE, text)
        # switching authorship swaps the reminder's own line and keeps the 18+ one
        directed = experiences.configure(on, 'director')
        text = next(b for b in directed['blocks'] if b['name'] == 'Reply reminder')['content']
        self.assertIn("director's latest direction", text)
        self.assertIn(mature.REMINDER_LINE, text)
        self.assertEqual(text.count('[Continue'), 1)
        built = presets.assemble(directed, {'chat_history': True}, [{'role': 'user', 'content': 'Hi'}],
                                 {'char': 'Rose', 'user': 'Anya'}, 'google/gemini-3.8-flash')
        self.assertEqual(built['messages'][-1]['role'], 'user')  # never an assistant prefill

    def test_follow_the_story_tense_and_length_options(self):
        b = self.blocks('opus-experience-conversation')
        self.assertIn('Keep the tense, point of view', b['Presentation']['content'])
        self.assertNotIn('present tense, third-person', b['Presentation']['content'])
        self.assertIn('flexible', b['Reply length']['content'])
        data = presets.normalize(starters.get('opus-experience-conversation')['preset'])
        self.assertTrue(experiences.set_length(data, 'short'))
        self.assertIn('two to four paragraphs', next(x for x in data['blocks'] if x['name'] == 'Reply length')['content'])
        preset = agent.build_preset({'starter': 'opus-experience-conversation', 'reply_length': 'long', 'taste': ''})
        self.assertIn('full sequence', next(x for x in preset['blocks'] if x['name'] == 'Reply length')['content'])
        self.assertFalse(any(x['name'] == 'Your taste' for x in preset['blocks']))  # no second length rule


class ExperienceModuleTests(SimpleTestCase):
    """The optional modules adapted from Pura, Sola and Realistic Frankenstein, and the model fixes."""

    def test_every_module_is_there_off_by_default_and_assembles_when_on(self):
        data = presets.normalize(starters.get('glm-experience-storytelling')['preset'])
        names = {m['title'] for m in experiences.catalog()['modules'].values()}
        self.assertGreaterEqual(len(names), 26)
        on_by_default = {b['name'] for b in data['blocks'] if b['name'] in names and b['enabled']}
        self.assertEqual(on_by_default, {'Friction', 'No therapy talk', 'Busy world'})
        for b in data['blocks']:
            if b['name'] in names:
                b['enabled'] = True
        built = presets.assemble(data, {'chat_history': True}, [{'role': 'user', 'content': 'Hi'}],
                                 {'char': 'Rose', 'user': 'Anya'}, 'z-ai/glm-5.3')
        text = '\n'.join(m['content'] for m in built['messages'])
        self.assertNotIn('{{', text)  # the random picks (Surprise me, names) resolve
        self.assertFalse([n for n in built['notes'] if 'nknown macro' in n])
        self.assertIn('Kael', text)  # the banned-names list
        self.assertIn('Narration voice', text)

    def test_bulba_switches_modules_on_one_voice_at_a_time(self):
        preset = agent.build_preset({'starter': 'opus-experience-drama', 'taste': '',
                                     'switch_on': ['Hard mode', 'Voice: Camus (wry)'], 'switch_off': ['Friction']})
        on = {b['name'] for b in preset['blocks'] if b['enabled']}
        self.assertTrue({'Hard mode', 'Voice: Camus (wry)'} <= on)
        self.assertNotIn('Friction', on)
        from unittest import mock
        session = type('S', (), {'user': None, 'preferences': [], 'proposals': [], 'target_model': 'claude-opus-5-5'})()
        with mock.patch.object(agent, 'target_profile', return_value=__import__('mainapp.model_profiles', fromlist=['x']).by_id('claude-opus-5-5')):
            result, _ = agent.tool_propose_preset(session, {'starter': 'opus-experience-drama', 'taste': 'x', 'why': 'y',
                                                            'switch_on': ['Voice: Camus (wry)', 'Voice: Kafka (absurd)']})
        self.assertIn('One narration voice', result['error'])

    def test_model_fixes_land_in_the_right_counters(self):
        c = writing_quality.catalog()['default_counters']
        self.assertIn('one-word filler', c['glm-5-3'])
        for m in ('glm-5-3', 'kimi-k3', 'deepseek-v4-pro', 'deepseek-v4-flash'):
            self.assertIn('Keep thinking short', c[m])
        self.assertNotIn('Keep thinking short', c['claude-opus-5-5'])
        for m in ('gemini-3-8-flash', 'gemini-4-argon'):
            self.assertIn('husky', c[m])
        for m in ('claude-opus-5-5', 'claude-fable-5-1'):
            self.assertIn('internet idioms', c[m])


class WriteForMeTests(SimpleTestCase):
    def test_write_my_message_leaves_out_the_reply_length_and_surprises(self):
        from mainapp import mature
        data = experiences.set_modules(presets.normalize(starters.get('opus-experience-drama')['preset']),
                                       {'surprise_me': True, 'dark_themes': True})
        data = mature.set_on(data, True)
        names = {b['name'] for b in control.for_impersonation(data)['blocks'] if b['enabled']}
        for gone in ('Your character', 'Reply reminder', 'Reply length', 'Surprise me'):
            self.assertNotIn(gone, names)
        for kept in ('Roleplay', 'Style', 'Dark themes (18+)', 'Mature content (optional)', 'Writing for you'):
            self.assertIn(kept, names)


class AdultModuleTests(SimpleTestCase):
    def test_18_plus_modules_go_off_with_mature_content(self):
        from mainapp import mature
        data = experiences.set_modules(presets.normalize(starters.get('opus-experience-drama')['preset']),
                                       {'dark_themes': True, 'slow_burn': True, 'chekhov': True})
        on = mature.set_on(data, True)
        self.assertTrue(next(b for b in on['blocks'] if b['name'] == 'Dark themes (18+)')['enabled'])
        off = mature.set_on(on, False)
        names = {b['name'] for b in off['blocks'] if b['enabled']}
        self.assertNotIn('Dark themes (18+)', names)
        self.assertNotIn('Slow-burn intimacy (18+)', names)
        self.assertIn("Chekhov's gun", names)



from django.test import TestCase, override_settings


@override_settings(LEGACY_FIRST_PRESET=False)
class FirstPresetTests(TestCase):
    def test_a_new_account_starts_on_heartstrings_for_its_model(self):
        from django.contrib.auth import get_user_model
        from users.models import ConnectionProfile
        user = get_user_model().objects.create_user(username="newbie", password="pw12345!")
        ConnectionProfile.objects.create(user=user, name="Main", api_key="k", model="moonshotai/kimi-k3")
        active = presets.get_active(user)
        self.assertEqual(active.name, "Heartstrings · Kimi K3")
        data = presets.normalize(active.data)
        self.assertIn("## Knowledge", next(b for b in data["blocks"] if b["name"] == "Roleplay")["content"])
        self.assertEqual(control.mode_of(data), "dont")
        self.assertNotIn("World Reality Augments", str(data))
        # no connection yet: the plain one
        other = get_user_model().objects.create_user(username="nokey", password="pw12345!")
        self.assertTrue(presets.get_active(other).name.startswith("Heartstrings · Any model"))

    def test_names_and_world_modules(self):
        titles = {s["experience"]: s["title"] for s in starters.all_starters() if s["model"] == "mimo-v2-6-pro"}
        self.assertEqual(titles, {"conversation": "Tête-à-tête", "drama": "Heartstrings", "storytelling": "Deep Water",
                                  "visual": "Storybook"})
        self.assertIn("Character Drama", starters.get("mimo-experience-drama")["description"])
        world = [m["title"] for m in experiences.catalog()["modules"].values() if m["group"] == "world"]
        for t in ("World: Aliens", "World: Vampires", "World: Prophetic visions"):
            self.assertIn(t, world)


@override_settings(LEGACY_FIRST_PRESET=False)
class PresetUpgradeTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from users.models import ConnectionProfile
        from mainapp.models import Preset
        self.user = get_user_model().objects.create_user(username="oldtimer", password="pw12345!")
        self.conn = ConnectionProfile.objects.create(user=self.user, name="Main", api_key="k", model="z-ai/glm-5.3")
        self.Preset = Preset

    def make(self, data, name):
        obj = self.Preset.objects.create(user=self.user, name=name, data=data)
        presets.activate(obj)
        return obj

    def test_the_pinned_note_has_a_slot_in_every_preset(self):
        for sid in ('opus-experience-drama', 'glm-rich-scene', 'gemini-frankenstein'):
            data = presets.normalize(starters.get(sid)['preset'])
            self.assertIn('world_context', [b.get('marker') for b in data['blocks']], sid)
            built = presets.assemble(data, {'chat_history': True, 'world_context': 'Pinned note: at the docks'},
                                     [{'role': 'user', 'content': 'Hi'}], {'char': 'Rose', 'user': 'Anya'}, '')
            self.assertIn('at the docks', str(built['messages']), sid)

    def test_an_untouched_old_starter_switches_with_its_choices_and_can_be_undone(self):
        from mainapp import mature, preset_upgrade
        from mainapp.bulba import control
        raw = preset_upgrade._raw_starter('glm-back-and-forth')
        data = mature.set_on(presets.normalize(raw['preset']), True)
        data['extras']['starter'] = {'id': 'glm-back-and-forth', 'model': 'glm-5-3'}
        data = control.apply_to_preset(data, 'write')
        data['blocks'].insert(1, presets.normalize_block({'name': 'Your taste', 'kind': 'prompt', 'content': 'Keep it wry.'}))
        old = self.make(data, 'Back-and-forth · GLM 5.3')
        hint = preset_upgrade.pending(self.user)
        self.assertEqual(hint['kind'], 'switched')
        active = presets.get_active(self.user)
        self.assertEqual(active.name, 'Tête-à-tête · GLM 5.3')
        new = presets.normalize(active.data)
        self.assertEqual(control.mode_of(new), 'write')
        self.assertTrue(mature.is_on(new))
        self.assertIn('Keep it wry.', str(new['blocks']))
        self.assertIsNone(preset_upgrade.pending(self.user))  # shown once
        self.assertTrue(preset_upgrade.undo(self.user))
        self.assertEqual(presets.get_active(self.user).id, old.id)
        self.assertIsNone(preset_upgrade.pending(self.user))  # and never again by itself

    def test_an_edited_old_preset_is_only_offered(self):
        from mainapp import preset_upgrade
        raw = preset_upgrade._raw_starter('glm-rich-scene')
        data = presets.normalize(raw['preset'])
        data['extras']['starter'] = {'id': 'glm-rich-scene', 'model': 'glm-5-3'}
        next(b for b in data['blocks'] if b['name'] == 'Style')['content'] += '\n- My own rule.'
        old = self.make(data, 'Rich scene · GLM 5.3')
        hint = preset_upgrade.pending(self.user)
        self.assertEqual((hint['kind'], hint['to']), ('offer_upgrade', 'Heartstrings · GLM 5.3'))
        self.assertEqual(presets.get_active(self.user).id, old.id)  # nothing switched by itself
        preset_upgrade.decline(self.user, 'offer_upgrade')
        self.assertIsNone(preset_upgrade.pending(self.user))

    def test_a_model_change_offers_a_rebuild_that_keeps_their_choices(self):
        from mainapp import preset_upgrade
        data = experiences.set_modules(experiences.configure(presets.normalize(starters.get('glm-experience-storytelling')['preset']), 'director'),
                                       {'hard_mode': True, 'friction': False})
        experiences.set_length(data, 'short')
        self.make(data, 'Deep Water · GLM 5.3')
        self.assertIsNone(preset_upgrade.pending(self.user))
        self.conn.model = 'anthropic/claude-opus-5-5'
        self.conn.save()
        hint = preset_upgrade.pending(self.user)
        self.assertEqual((hint['kind'], hint['from'], hint['to']), ('offer_rebuild', 'GLM 5.3', 'Claude Opus 5.5'))
        obj = preset_upgrade.rebuild(self.user)
        self.assertEqual(obj.name, 'Deep Water · Claude Opus 5.5')
        new = presets.normalize(obj.data)
        on = {b['name'] for b in new['blocks'] if b['enabled']}
        self.assertIn('Hard mode', on)
        self.assertNotIn('Friction', on)
        self.assertEqual(control.mode_of(new), 'director')
        self.assertIn('two to four', next(b for b in new['blocks'] if b['name'] == 'Reply length')['content'])
        self.assertIn('# How this story is written', next(b for b in new['blocks'] if b['name'] == 'Roleplay')['content'])
        self.assertIsNone(preset_upgrade.pending(self.user))
        self.assertTrue(preset_upgrade.undo_rebuild(self.user))
        self.assertEqual(presets.get_active(self.user).name, 'Deep Water · GLM 5.3')


class DesignedObjectTests(SimpleTestCase):
    """In-story objects the AI designs as ```html blocks (mainapp/html_objects.py)."""
    BANNER = ("Before.\n\n```html\n<div data-label=\"Scene banner: the docks, dusk\" style=\"color:red\">"
              "<b>THE DOCKS</b><script>blink()</script></div>\n```\n\nAfter.")

    def test_labels_and_shrinking(self):
        from mainapp import html_objects
        self.assertTrue(html_objects.has_objects(self.BANNER))
        self.assertEqual(html_objects.shrink(self.BANNER),
                         "Before.\n\n[Shown to the reader as a designed object: Scene banner: the docks, dusk]\n\nAfter.")
        self.assertEqual(html_objects.strip(self.BANNER), "Before.\n\nAfter.")
        # without a data-label: the visible text, scripts and styles left out
        self.assertEqual(html_objects.label("<style>b{}</style><p>WANTED: <i>the Fox</i></p><script>x()</script>"),
                         "WANTED: the Fox")
        self.assertEqual(html_objects.shrink("Plain prose, `code`."), "Plain prose, `code`.")
        unclosed = "Text\n```html\n<div>cut off"
        self.assertEqual(html_objects.shrink(unclosed), unclosed)

    def test_the_ai_rereads_only_its_latest_objects_in_full(self):
        from mainapp import views
        messages = [("assistant", "", self.BANNER, "neutral", 1), ("user", "", "Go on", "neutral", 1),
                    ("assistant", "", self.BANNER, "neutral", 1), ("user", "", "And?", "neutral", 1),
                    ("assistant", "", self.BANNER, "neutral", 1)]
        history = views._history(messages)
        self.assertNotIn("```html", history[0]["content"])
        self.assertIn("Scene banner: the docks, dusk", history[0]["content"])
        self.assertIn("```html", history[2]["content"])
        self.assertIn("```html", history[4]["content"])
        self.assertNotIn("```html", views._summary_line(messages[4]))  # summaries read the label

    def test_designed_kinds_take_over_app_drawn_extras(self):
        from mainapp import html_objects
        data = presets.normalize(starters.get('opus-experience-drama')['preset'])
        self.assertEqual(html_objects.replaced_kinds(data), set())
        data = experiences.set_modules(data, {'html_screens': True, 'html_rumours': True})
        self.assertEqual(html_objects.replaced_kinds(data), {'messages', 'news'})
        data = experiences.set_modules(data, {'html_objects': True})
        self.assertEqual(html_objects.replaced_kinds(data), {'documents', 'messages', 'news'})

    def test_every_object_module_asks_for_the_fenced_format(self):
        mods = {k: m for k, m in experiences.catalog()['modules'].items() if m.get('group') == 'objects'}
        self.assertEqual(set(mods), {'html_banner', 'html_letters', 'html_screens', 'html_rumours', 'html_objects',
                                     'html_custom'})
        for m in mods.values():
            self.assertFalse(m['default'])
            self.assertIn('```html', m['content'])
            self.assertIn('data-label', m['content'])


class StorybookTests(SimpleTestCase):
    def test_storybook_is_deep_water_with_designed_objects_on(self):
        s = starters.get('glm-experience-visual')
        self.assertEqual(s['title'], 'Storybook')
        on = {b.get('name') for b in s['preset']['blocks'] if b.get('enabled')}
        self.assertTrue({'Scene banner (AI-designed)', 'Any in-story object (AI-designed)', 'Writing quality'} <= on)
        self.assertNotIn('Scene banner (AI-designed)',
                         {b.get('name') for b in starters.get('glm-experience-storytelling')['preset']['blocks'] if b.get('enabled')})


class DesignedTrackerTests(SimpleTestCase):
    """Custom tracker fields Bulba designs: look, colour, what moves them, levels that steer the writing."""
    FIELD = {"label": "Patience", "type": "meter", "min": 0, "max": 100, "look": "ring", "color": "#f472b6",
             "icon": "⏳", "raises": ["13 answers precisely"], "lowers": ["Wasted time", "Flattery"],
             "levels": [{"from": 60, "to": 100, "name": "Indulgent", "note": "He explains at length."},
                        {"from": 0, "to": 29, "name": "Exhausted", "note": "One-word answers; he turns away."},
                        {"from": 30, "to": 59, "name": "Clipped"}]}

    def test_design_is_kept_and_cleaned(self):
        from mainapp import trackers
        f = trackers.normalize_custom_fields([{**self.FIELD, "color": "red", "look": "hologram"}])[0]
        self.assertNotIn("color", f)  # not a hex
        self.assertNotIn("look", f)
        f = trackers.normalize_custom_fields([self.FIELD])[0]
        self.assertEqual((f["look"], f["color"], f["icon"]), ("ring", "#f472b6", "⏳"))
        self.assertEqual([lv["name"] for lv in f["levels"]], ["Exhausted", "Clipped", "Indulgent"])  # sorted
        self.assertEqual(trackers.level_of(f, 45)["name"], "Clipped")

    def test_levels_steer_the_story_and_moves_guide_the_tracker(self):
        from mainapp import trackers
        config = trackers.normalize_config({"trackers": {"custom": {"on": True}}, "custom_fields": [self.FIELD]})
        state = trackers.normalize_state({"values": {"custom": {"patience": 20}}}, config)
        text = trackers.format_for_prompt(config, state)
        self.assertIn("Patience: 20/100 (Exhausted)", text)
        self.assertIn("Patience is Exhausted: One-word answers; he turns away.", text)
        system = trackers.update_messages(config, state, [("user", "Hi")], "Dottore", "13")[0]["content"]
        self.assertIn("goes up with: 13 answers precisely", system)
        self.assertIn("goes down with: Wasted time, Flattery", system)

    def test_bulba_card_shows_the_design(self):
        from unittest import mock
        from mainapp.bulba import tune
        session = type("S", (), {"proposals": []})()
        character = type("C", (), {"id": 1, "name": "Dottore"})()
        with mock.patch.object(tune, "target_character", return_value=character), \
                mock.patch.object(tune, "_propose", side_effect=lambda s, k, t, summary, payload, why: (summary, payload)):
            summary, payload = tune.tool_propose_trackers(session, {"custom_fields": [self.FIELD], "why": "x"})
        self.assertIn("custom", payload["on"])
        self.assertTrue(any("Patience levels: 0-29 Exhausted" in line for line in summary))
        self.assertTrue(any("up with 13 answers precisely" in line for line in summary))


class TrackerTriggerTests(SimpleTestCase):
    """Automatic escalation between custom fields (trackers.apply_triggers), applied after the AI's update."""
    FIELDS = [{"label": "Alarm", "type": "meter", "min": 0, "max": 100,
               "triggers": [{"if": ">=", "at": 80, "then": "Guards alerted", "change": 1}]},
              {"label": "Guards alerted", "type": "number",
               "triggers": [{"if": ">=", "at": 3, "then": "Exit time", "change": -5}]},
              {"label": "Exit time", "type": "meter", "min": 0, "max": 30},
              {"label": "Pressure", "type": "meter", "min": 0, "max": 100,
               "triggers": [{"if": ">=", "at": 90, "then": "alarm", "change": 5, "repeat": True},
                            {"if": ">=", "at": 1, "then": "Nowhere", "change": 1}]}]

    def config(self):
        from mainapp import trackers
        return trackers.normalize_config({"trackers": {"custom": {"on": True}}, "custom_fields": self.FIELDS})

    def run_update(self, config, state, update):
        from mainapp import trackers
        trackers.apply_update(config, state, {"custom": update})
        return state["values"]["custom"]

    def test_rules_resolve_targets_and_drop_bad_ones(self):
        fields = {f["key"]: f for f in self.config()["custom_fields"]}
        self.assertEqual(fields["alarm"]["triggers"][0]["then"], "guards_alerted")
        self.assertEqual(len(fields["pressure"]["triggers"]), 1)  # "Nowhere" isn't a field

    def test_fires_once_on_reaching_and_chains(self):
        from mainapp import trackers
        config = self.config()
        state = trackers.normalize_state({"values": {"custom": {"alarm": 50, "guards_alerted": 2, "exit_time": 30}}}, config)
        v = self.run_update(config, state, {"alarm": 85, "guards_alerted": 2, "exit_time": 30})
        self.assertEqual((v["guards_alerted"], v["exit_time"]), (3, 25))  # alarm → guards → exit time
        v = self.run_update(config, state, {"alarm": 88, "guards_alerted": 3, "exit_time": 25})
        self.assertEqual((v["guards_alerted"], v["exit_time"]), (3, 25))  # still above: doesn't fire again

    def test_repeat_pushes_every_update_and_locks_hold(self):
        from mainapp import trackers
        config = self.config()
        state = trackers.normalize_state({"values": {"custom": {"pressure": 95, "alarm": 10}}}, config)
        self.assertEqual(self.run_update(config, state, {"pressure": 95, "alarm": 10})["alarm"], 15)
        self.assertEqual(self.run_update(config, state, {"pressure": 96, "alarm": 15})["alarm"], 20)
        state["locks"].append("custom.alarm")
        self.assertEqual(self.run_update(config, state, {"pressure": 97})["alarm"], 20)

    def test_the_tracker_ai_is_told_not_to_double_count(self):
        from mainapp import trackers
        config = self.config()
        state = trackers.normalize_state({}, config)
        system = trackers.update_messages(config, state, [("user", "Hi")], "Guard", "Thief")[0]["content"]
        self.assertIn('the app adds 1 to "guards_alerted" when this reaches >= 80', system)
