from django.test import SimpleTestCase
from mainapp import model_profiles, presets, starters, writing_quality
from mainapp.bulba import agent, library


class WritingQualityTests(SimpleTestCase):
    def test_all_authored_variants_assemble_one_quality_block(self):
        authored = [s for s in starters.all_starters() if s['experience'] in starters.READY_FEELS]
        self.assertEqual(len(authored), 33)
        for starter in authored:
            with self.subTest(starter=starter['id']):
                blocks = starter['preset']['blocks']
                quality = [b for b in blocks if b.get('id') == writing_quality.BLOCK_ID]
                self.assertEqual(len(quality), 1)
                self.assertTrue(quality[0]['enabled'])
                normalized = presets.normalize(starter['preset'])
                built = presets.assemble(normalized, {'chat_history': True},
                    [{'role': 'user', 'content': 'Hello'}], {'char': 'Rose', 'user': 'Anya'}, '')
                text = '\n'.join(m['content'] for m in built['messages'])
                self.assertIn(quality[0]['content'], text)
                self.assertNotIn('one beat', text.lower())
                self.assertNotIn('Each reply changes something', text)

    def test_customization_preserves_baseline_without_duplicate(self):
        for sid in ('mimo-back-and-forth', 'kimi-rich-scene', 'glm-director'):
            built = agent.build_preset({'starter': sid, 'taste': 'Keep dry humor.',
                'rewrite': {'Style': 'Use reflective narration.'}, 'reply_length': 'short'})
            blocks = [b for b in built['blocks'] if b.get('id') == writing_quality.BLOCK_ID]
            self.assertEqual(len(blocks), 1)
            self.assertTrue(blocks[0]['enabled'])

    def test_baseline_remains_an_explicit_user_choice(self):
        built = agent.build_preset({'starter': 'mimo-rich-scene', 'taste': '',
                                    'switch_off': [writing_quality.BLOCK_NAME]})
        self.assertFalse(next(b for b in built['blocks'] if b['id'] == writing_quality.BLOCK_ID)['enabled'])
        original = starters.get("mimo-rich-scene")["preset"]["blocks"]
        self.assertTrue(next(b for b in original if b.get("id") == writing_quality.BLOCK_ID)["enabled"])

    def test_community_artifacts_are_not_silently_rewritten(self):
        for starter in starters.all_starters():
            if starter['experience'].startswith('full_preset'):
                self.assertFalse(any(b.get('id') == writing_quality.BLOCK_ID for b in starter['preset']['blocks']))

    def test_every_model_has_research_scoped_guidance(self):
        known = {m['id'] for m in writing_quality.catalog()['modules']}
        for profile in model_profiles.all_profiles():
            ids = writing_quality.catalog()['models'][profile['id']]
            self.assertTrue(ids)
            self.assertTrue(set(ids) <= known)
            self.assertIn('diagnostic candidates', agent.model_knowledge(profile))

    def test_repair_tool_returns_exceptions_and_evaluation_not_just_a_ban(self):
        from types import SimpleNamespace
        item = writing_quality.catalog()['modules'][0]
        name = 'Writing repair: ' + item['problem']
        result, _ = library.tool_read_practice(SimpleNamespace(), {'block': name})
        self.assertEqual(result['content'], item['instruction'])
        for key in ('exception', 'test', 'provenance', 'evidence'):
            self.assertEqual(result[key], item[key])
        self.assertIn('unverified', result['evidence'])
