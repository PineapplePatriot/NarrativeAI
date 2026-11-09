from django.test import SimpleTestCase
from mainapp import experiences, starters, presets, writing_quality
from mainapp.bulba import agent, control


class ExperienceTests(SimpleTestCase):
    def test_catalog_has_three_original_experiences_per_model(self):
        self.assertEqual(len(starters.all_starters()), 33)
        for s in starters.all_starters():
            self.assertIn(s['experience'], experiences.EXPERIENCES)
            self.assertEqual(s['based_on'], [])
            self.assertEqual(control.mode_of(presets.normalize(s['preset'])), 'dont')
            names = {b.get('name'): b for b in s['preset']['blocks']}
            for name in ('Model foundation', 'Writing quality', 'Model pattern counters'):
                self.assertTrue(names[name]['enabled'])
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
            expected = 'narrative' if s['model'].startswith(('claude', 'gemini', 'mimo')) else 'structured'
            self.assertEqual(s['preset']['extras']['original_experience']['foundation'], expected)
            self.assertEqual(d['model_foundations'][s['model']], expected)

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
