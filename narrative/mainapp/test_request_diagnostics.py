import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from mainapp import ai_client
from users.models import ConnectionProfile


class RequestDiagnosticsTests(SimpleTestCase):
    def profile(self):
        return SimpleNamespace(pk=123, provider=ConnectionProfile.PROVIDER_OPENROUTER,
                               name='Test connection', model='google/gemini-3.8-flash',
                               api_url='https://openrouter.ai/api/v1', api_key='DO-NOT-LOG-KEY')

    def response(self, data, status=200):
        return Mock(status_code=status, json=Mock(return_value=data))

    def test_diagnostic_does_not_include_messages_headers_or_raw_error(self):
        payload={'model':'google/gemini-3.8-flash','messages':[{'role':'user','content':'PRIVATE-STORY'}],
                 'safety_settings':ai_client.GEMINI_SAFETY}
        with self.assertLogs('mainapp.ai_client', level='WARNING') as logs:
            ai_client._diagnostic(self.profile(),payload,'translation','translation','http_error',
                self.response({},400),{'error':{'message':'PRIVATE-STORY','metadata':
                    {'provider_name':'Google AI Studio','raw':'DO-NOT-LOG-KEY'}}})
        text='\n'.join(logs.output)
        self.assertNotIn('PRIVATE-STORY',text)
        self.assertNotIn('DO-NOT-LOG-KEY',text)
        self.assertIn('Google AI Studio',text)
        self.assertIn('request_hash',text)
        self.assertIn('translation',text)

    def test_unrelated_400_does_not_strip_safety_settings(self):
        response=self.response({'error':{'message':'Invalid max_tokens'}},400)
        payload={'model':'google/gemini-3.8-flash','safety_settings':ai_client.GEMINI_SAFETY,'messages':[]}
        with patch.object(ai_client.requests,'post',return_value=response) as post:
            self.assertIs(ai_client._post(self.profile(),payload),response)
        self.assertEqual(post.call_count,1)
        self.assertIn('safety_settings',post.call_args.kwargs['json'])

    def test_prohibited_content_is_not_retried_as_a_schema_error(self):
        response=self.response({'error':{'message':'PROHIBITED_CONTENT; safety_settings present'}},400)
        with patch.object(ai_client.requests,'post',return_value=response) as post:
            ai_client._post(self.profile(),{'model':'google/gemini-3.8-flash',
                            'messages':[],'safety_settings':ai_client.GEMINI_SAFETY})
        self.assertEqual(post.call_count,1)

    def test_synchronous_tasks_keep_a_block_reason_instead_of_empty_text(self):
        response=self.response({'id':'request-1','provider':'Google AI Studio','choices':[
            {'message':{'content':''},'finish_reason':'content_filter','native_finish_reason':'PROHIBITED_CONTENT'}]})
        for task in ('chat','translation','polish'):
            with self.subTest(task=task), patch.object(ai_client,'resolve',return_value=(self.profile(),'google/gemini-3.8-flash')), \
                 patch.object(ai_client,'check_limit'), patch.object(ai_client,'record_cost'), \
                 patch.object(ai_client,'_light_reasoning'), patch.object(ai_client,'_post',return_value=response):
                with self.assertRaisesRegex(ai_client.AIError,'PROHIBITED_CONTENT'):
                    ai_client.complete(None,task,[{'role':'user','content':'Hello'}])

    def test_rewrite_diagnostic_tag_never_reaches_provider(self):
        response=self.response({'choices':[{'message':{'content':'Hello'},'finish_reason':'stop'}]})
        with patch.object(ai_client,'resolve',return_value=(self.profile(),'google/gemini-3.8-flash')), \
             patch.object(ai_client,'check_limit'), patch.object(ai_client,'record_cost'), \
             patch.object(ai_client,'_light_reasoning'), patch.object(ai_client,'_post',return_value=response) as post:
            self.assertEqual(ai_client.complete(None,'chat',[],_diagnostic_operation='rewrite'),'Hello')
        self.assertEqual(post.call_args.kwargs['diagnostic_operation'],'rewrite')
        self.assertNotIn('_diagnostic_operation',post.call_args.args[1])
        self.assertEqual(post.call_args.args[1]['safety_settings'],ai_client.GEMINI_SAFETY)

    def test_block_explanation_does_not_invent_ages_or_exclude_preset(self):
        text=ai_client.block_explanation('PROHIBITED_CONTENT')
        self.assertIn('does not identify the trigger',text)
        self.assertNotIn('most often',text)
        self.assertNotIn('minors',text)

    def test_translation_prompt_does_not_inherit_account_generation_rules(self):
        from mainapp import translation
        for base in (translation.INSTRUCTIONS, translation.LIST_PROMPT):
            self.assertEqual(translation._instructions(self.profile(), base), base)
            self.assertEqual(translation._instructions(None, base), base)

    def test_normalized_block_is_not_hidden_by_an_unrecognized_native_reason(self):
        response = self.response({'choices': [{'message': {'content': ''},
            'finish_reason': 'content_filter', 'native_finish_reason': 'OTHER'}]})
        with patch.object(ai_client, 'resolve', return_value=(self.profile(), 'google/gemini-3.8-flash')), \
             patch.object(ai_client, 'check_limit'), patch.object(ai_client, 'record_cost'), \
             patch.object(ai_client, '_light_reasoning'), patch.object(ai_client, '_post', return_value=response):
            with self.assertRaisesRegex(ai_client.AIError, 'content_filter'):
                ai_client.complete(None, 'translation', [])


from mainapp import tests as chat_tests


class RewriteRequestParityTests(chat_tests.ChatPromptTests):
    def test_rewrite_keeps_translation_language_instruction(self):
        from mainapp.views import build_chat_request
        from mainapp import translation
        self.post({"action": "chat", "message": "Hello."})
        self.user.display_language = "uk"
        built = build_chat_request(self.user, self.character.chats.first())
        self.assertEqual(built["messages"][-1], translation.english_note(self.user))

    def test_rewrite_restores_old_per_reply_director_note(self):
        from mainapp.views import build_chat_request
        from mainapp import chats
        self.post({"action": "chat", "message": "Hello."})
        chat = self.character.chats.first()
        data = chats.read(chat)
        data["messages"][-1] = list(chats.with_directed(tuple(data["messages"][-1]), "Keep the conversation gentle."))
        chats.write(chat, data)
        built = build_chat_request(self.user, chat)
        text = json.dumps(built["messages"])
        self.assertIn("Director's note for this reply: Keep the conversation gentle.", text)
        self.assertEqual(text.count("Keep the conversation gentle."), 1)

    def test_rewrite_uses_new_note_once_in_the_director_slot(self):
        from mainapp.views import build_chat_request
        self.post({"action": "chat", "message": "Hello.", "guidance": "Keep the conversation gentle."})
        built = build_chat_request(self.user, self.character.chats.first())
        text = json.dumps(built["messages"])
        self.assertIn("Director's note for this reply: Keep the conversation gentle.", text)
        self.assertEqual(text.count("Keep the conversation gentle."), 1)
