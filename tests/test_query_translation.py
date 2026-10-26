import asyncio
import json
import time
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pipeline.query_translation import (
    NormalizedQuery, QueryTranslationError, is_korean_query, normalize_query,
)
from tests.test_chat_persistence import load_functions, AsyncContext, FakeResult


class TranslationTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, data=None, error=None):
        create = AsyncMock(side_effect=error)
        create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps(data, ensure_ascii=False)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        context = AsyncContext(client)
        return SimpleNamespace(AsyncOpenAI=lambda **kwargs: context), create

    async def test_korean_and_formula_inputs_need_no_provider(self):
        with patch.dict(sys.modules, {'openai': None}):
            for prompt in ['NaOH가 눈에 튀었어요', 'NFPA 위험성을 알려줘', '5 mg을 만지지 마세요', 'NaOH', 'NaOH 5 ppm', '119']:
                result = await normalize_query(prompt)
                self.assertEqual(result.normalized_prompt, prompt)
            for prompt in ['', ' ' * 3, 'x' * 6001]:
                with self.assertRaises(QueryTranslationError):
                    await normalize_query(prompt)

    async def test_multilingual_prose_is_translated_once_and_preserves_source(self):
        examples = [
            ('NaOH splashed into my eyes.', 'en', '눈에 NaOH가 튀었어요.'),
            ('Tôi bị NaOH bắn vào mắt.', 'vi', '눈에 NaOH가 튀었어요.'),
            ('NaOHが目に入りました。', 'ja', '눈에 NaOH가 들어갔어요.'),
            ('NaOH溅入眼睛了。', 'zh', '눈에 NaOH가 튀었어요.'),
            ('눈에 NaOH splashed, help me.', 'en', '눈에 NaOH가 튀었어요. 도와주세요.'),
            ('Then what?', 'en', '그다음에는?'),
            ('Do not touch it.', 'en', '만지지 마세요.'),
        ]
        for original, language, korean in examples:
            module, create = self.provider({'source_language': language, 'normalized_prompt': korean})
            with patch.dict(sys.modules, {'openai': module}):
                result = await normalize_query(original)
            self.assertEqual(result, NormalizedQuery(original, korean, language))
            create.assert_awaited_once()
            self.assertEqual(create.call_args.kwargs['messages'][-1]['content'], original)
        self.assertFalse(is_korean_query('눈에 NaOH splashed, help me.'))

    async def test_missing_numbers_units_formulas_and_invalid_responses_are_rejected(self):
        original = 'Do not touch NaOH, CAS 1310-73-2, 5 mg. Call 119.'
        valid = 'NaOH, CAS 1310-73-2, 5 mg을 만지지 마세요. 119에 연락하세요.'
        module, _ = self.provider({'source_language': 'en', 'normalized_prompt': valid})
        with patch.dict(sys.modules, {'openai': module}):
            self.assertEqual((await normalize_query(original)).normalized_prompt, valid)
        for text in [valid.replace('NaOH', 'KOH'), valid.replace('119', '112'),
                     valid.replace('mg', 'kg'), valid + ' 119', '', 'x' * 6001, original]:
            module, _ = self.provider({'source_language': 'en', 'normalized_prompt': text})
            with patch.dict(sys.modules, {'openai': module}):
                with self.assertRaises(QueryTranslationError):
                    await normalize_query(original)
        for data in [{'source_language': 'english', 'normalized_prompt': valid}, {}, [], None]:
            module, _ = self.provider(data)
            with patch.dict(sys.modules, {'openai': module}):
                with self.assertRaises(QueryTranslationError):
                    await normalize_query(original)
        module, _ = self.provider(error=RuntimeError('PRIVATE_PROVIDER_ERROR'))
        with patch.dict(sys.modules, {'openai': module}):
            with self.assertRaises(QueryTranslationError) as raised:
                await normalize_query(original)
        self.assertNotIn('PRIVATE', str(raised.exception))


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class FakeApp:
    def post(self, *_args, **_kwargs):
        return lambda function: function


class FakeRequestModel:
    def __init__(self, prompt, conversation_id=None, **kwargs):
        self.prompt, self.conversation_id = prompt, conversation_id
        self.__dict__.update(kwargs)

    def model_copy(self, update):
        return FakeRequestModel(**{**self.__dict__, **update})


class QueryFlowTests(unittest.IsolatedAsyncioTestCase):
    def flow(self, failure=False):
        calls, saved = [], []
        original = 'NaOH splashed into my eyes.'
        korean = '눈에 NaOH가 튀었어요.'
        async def auth(request):
            calls.append('auth'); return 'alice'
        async def authorize(username, request):
            calls.append('owner')
        async def normalize(value):
            calls.append('translate')
            if failure:
                raise QueryTranslationError('번역 실패')
            return NormalizedQuery(value, korean, 'en')
        async def chat(username, request):
            calls.append(('chat', request.prompt))
            return {'conversation_id': 'c1', 'is_new': True, 'title': request.prompt,
                    'summary': None, 'turns': [], 'search_question': request.prompt}
        async def rag(request, search):
            calls.append(('retrieve', request.prompt, search))
            return {'q': request.prompt, 'context': ''}
        async def save(*args):
            saved.append(args[-1])
        async def connected(): return False
        async def log_turn(*args):
            return None
        scope = {
            'app': FakeApp(), 'Request': object, 'RAGRequest': FakeRequestModel,
            'Body': lambda *args, **kwargs: None, 'AnswerResponse': lambda **kwargs: kwargs,
            'authenticated_username': auth, 'authorize_conversation': authorize,
            'normalize_query': normalize, 'QueryTranslationError': QueryTranslationError,
            'HTTPException': HTTPError, 'prepare_chat': chat, 'prepare_rag': rag,
            'finish_rag': lambda state, raw: {'prompt': state['q'], 'answer': '안전 안내'},
            'save_turn': save, 'asyncio': asyncio, 'json': json,
            'StreamingResponse': lambda body, **kwargs: body,
            'time': time, 'record_query_log': log_turn,
        }
        query, stream, *_ = load_functions('rag_query', 'rag_query_stream', 'translate_input',
                                         'prepare_query', 'finalize_turn', 'sse_event', namespace=scope)
        request = SimpleNamespace(is_disconnected=connected)
        model = FakeRequestModel(original, top_k=5, source='pdf')
        return query, stream, request, model, calls, saved

    async def test_json_and_stream_use_korean_everywhere_and_store_original(self):
        for streaming in (False, True):
            query, stream, request, model, calls, saved = self.flow()
            if streaming:
                events = [event async for event in await stream(request, model)]
                self.assertIn('"phase": "translating"', events[0])
                self.assertIn('event: normalized', events[1])
                result = json.loads(events[-1].split('data: ')[1])
            else:
                result = await query(request, model)
            self.assertEqual(calls[:3], ['auth', 'owner', 'translate'])
            self.assertIn(('retrieve', '눈에 NaOH가 튀었어요.', '눈에 NaOH가 튀었어요.'), calls)
            self.assertEqual(result['prompt'], model.prompt)
            self.assertEqual(result['normalized_prompt'], '눈에 NaOH가 튀었어요.')
            self.assertEqual(result['source_language'], 'en')
            self.assertEqual(result['title'], model.prompt)
            self.assertEqual(saved, [result])
            self.assertEqual(model.prompt, 'NaOH splashed into my eyes.')

    async def test_translation_failure_never_retrieves_or_saves(self):
        for streaming in (False, True):
            query, stream, request, model, calls, saved = self.flow(failure=True)
            if streaming:
                events = [event async for event in await stream(request, model)]
                self.assertIn('event: error', events[-1])
                self.assertFalse(any('event: done' in event for event in events))
            else:
                with self.assertRaises(HTTPError) as raised:
                    await query(request, model)
                self.assertEqual(raised.exception.status_code, 502)
            self.assertEqual(calls, ['auth', 'owner', 'translate'])
            self.assertEqual(saved, [])

    async def test_auth_and_ownership_failure_happen_before_translation(self):
        for field in ('authenticated_username', 'authorize_conversation'):
            for streaming in (False, True):
                query, stream, request, model, calls, saved = self.flow()
                async def deny(*args): raise HTTPError(404, 'denied')
                query.__globals__[field] = deny
                with self.assertRaises(HTTPError):
                    await (stream if streaming else query)(request, model)
                self.assertNotIn('translate', calls)
                self.assertFalse(saved)

    async def test_legacy_and_normalized_history_are_korean_before_context_and_summary(self):
        rows = [
            {'id': 1, 'role': 'user', 'content': 'NaOH splashed into my eyes.', 'normalized_text': None},
            {'id': 2, 'role': 'assistant', 'content': '물로 씻으세요'},
            {'id': 3, 'role': 'user', 'content': 'Then what?', 'normalized_text': '그다음에는?'},
            {'id': 4, 'role': 'assistant', 'content': '현장 담당자에게 알리세요'},
        ]
        class Connection:
            async def execute(self, *args): return FakeResult(rows)
        engine = SimpleNamespace(connect=lambda: AsyncContext(Connection()))
        async def owned(*args):
            return {'title': '원문 제목', 'summary': None, 'summary_through_message_id': None}
        translate = AsyncMock(return_value=NormalizedQuery(rows[0]['content'], '눈에 NaOH가 튀었어요.', 'en'))
        contextual = load_functions('contextual_search_question')[0]
        summarize = AsyncMock(return_value='눈에 NaOH가 튀었어요.')
        prepare, = load_functions('prepare_chat', namespace={
            'RAGRequest': object, 'engine': engine, 'text': lambda s: s,
            '_owned_conversation': owned, 'translate_input': translate,
            '_bounded_summary': lambda s: s, '_text_tokens': lambda s: 0,
            'split_history_for_summary': lambda messages, **kwargs: ([messages[:2]], [messages[2:]]),
            '_summarize_turns': summarize, 'HTTPException': HTTPError,
            'contextual_search_question': contextual,
        })
        result = await prepare('alice', FakeRequestModel('그다음에는?', 'c1'))
        self.assertIn('눈에 NaOH가 튀었어요.', result['search_question'])
        self.assertNotIn('splashed', result['search_question'])
        self.assertEqual(result['pending_normalizations'][0]['id'], 1)
        translate.assert_awaited_once()
        self.assertEqual(summarize.call_args.args[1][0][0]['content'], '눈에 NaOH가 튀었어요.')

    async def test_storage_preserves_original_and_backfills_legacy_in_one_transaction(self):
        statements = []
        class Connection:
            async def execute(self, sql, params):
                statements.append((sql, params)); return FakeResult()
        engine = SimpleNamespace(begin=lambda: AsyncContext(Connection()))
        save, = load_functions('save_turn', namespace={'engine': engine, 'text': lambda s: s, 'json': json})
        await save('alice', {'is_new': True, 'conversation_id': 'c1', 'title': 'Original',
                            'pending_normalizations': [{'id': 1, 'normalized_text': '이전 질문', 'source_language': 'en'}]},
                   {'prompt': 'Original', 'normalized_prompt': '한국어 질문', 'source_language': 'en',
                    'answer': '답변', 'sources': [], 'needs_review': False, 'handoff': False, 'clarifying_questions': []})
        user = next(params for sql, params in statements if "'user', :content" in sql)
        self.assertEqual(user['content'], 'Original')
        self.assertEqual(user['normalized_text'], '한국어 질문')
        self.assertEqual(user['source_language'], 'en')
        update = next((sql, params) for sql, params in statements if 'normalized_text IS NULL' in sql)
        self.assertIn('conversation_id = :conversation_id', update[0])
        self.assertEqual(update[1]['id'], 1)
