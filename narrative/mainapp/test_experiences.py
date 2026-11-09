from django.test import SimpleTestCase, TestCase
from mainapp import experiences, starters, presets, writing_quality
from mainapp.bulba import agent, control


class ExperienceTests(SimpleTestCase):
    def test_catalog_has_three_original_experiences_per_model(self):
        self.assertEqual(len(starters.all_starters()), 36)  # eleven models and "Any model"
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
