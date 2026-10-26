import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('JWT_SECRET', 'translation-test-secret')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import tts_router as module
from app.services import processor_service, tts_service


class TranslationTtsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.upload = patch.object(module, 'UPLOAD_DIR', self.directory.name)
        self.upload.start()
        self.addCleanup(self.upload.stop)
        app = FastAPI()
        app.include_router(module.router, prefix='/tts')
        self.client = TestClient(app)
        self.app = app

    def authenticate(self):
        self.app.dependency_overrides[module.get_current_user] = lambda: {'id': 'test', 'username': 'test'}

    def test_auth_and_validation_prevent_provider_calls(self):
        with patch.object(module, 'text_to_speech') as speech, patch.object(module, 'get_llm_response') as translate:
            self.assertEqual(self.client.post('/tts/', data={'text': '안전'}).status_code, 401)
            self.authenticate()
            for data, status in [({'text': '안전', 'target_language': 'xx'}, 400),
                                 ({'text': '   '}, 400), ({'text': 'x' * 4097}, 422)]:
                self.assertEqual(self.client.post('/tts/', data=data).status_code, status)
            speech.assert_not_called()
            translate.assert_not_called()

    def test_korean_bypasses_translation_and_concurrent_files_are_unique(self):
        self.authenticate()
        def write(text, output):
            Path(output).write_bytes(text.encode())
        with patch.object(module, 'text_to_speech', side_effect=write), patch.object(module, 'get_llm_response') as translate:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: self.client.post('/tts/', data={'text': '119에 연락하세요'}), range(4)))
            self.assertTrue(all(r.status_code == 200 for r in results))
            paths = [r.json()['file_path'] for r in results]
            self.assertEqual(len(set(paths)), 4)
            translate.assert_not_called()
            for result in results:
                self.assertEqual(result.json()['translated_text'], '119에 연락하세요')

    def test_every_foreign_language_returns_exact_text_used_for_speech(self):
        self.authenticate()
        for language in ('en', 'zh', 'ja', 'vi'):
            with patch.object(module, 'get_llm_response', return_value='Call 119. Do not touch NaOH.') as translate, patch.object(module, 'text_to_speech') as speech:
                response = self.client.post('/tts/', data={'text': 'NaOH를 만지지 마세요. 119에 연락하세요.', 'target_language': language})
                self.assertEqual(response.status_code, 200)
                data = response.json()
                translate.assert_called_once_with(data['original_text'], language)
                self.assertEqual(speech.call_args.args[0], data['translated_text'])
                self.assertEqual(data['target_language'], language)

    def test_translation_failures_never_synthesize_an_error_message(self):
        self.authenticate()
        with patch.object(module, 'get_llm_response', side_effect=RuntimeError('PRIVATE_PROVIDER_BODY')), patch.object(module, 'text_to_speech') as speech:
            response = self.client.post('/tts/', data={'text': '안전', 'target_language': 'en'})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('PRIVATE', response.text)
            speech.assert_not_called()
        with patch.object(module, 'get_llm_response', return_value='x' * 4097), patch.object(module, 'text_to_speech') as speech:
            self.assertEqual(self.client.post('/tts/', data={'text': '안전', 'target_language': 'en'}).status_code, 400)
            speech.assert_not_called()

    def test_speech_failure_removes_partial_file_and_sanitizes_error(self):
        self.authenticate()
        def fail(text, output):
            Path(output).write_bytes(b'partial')
            raise RuntimeError('PRIVATE_PROVIDER_BODY')
        with patch.object(module, 'text_to_speech', side_effect=fail):
            response = self.client.post('/tts/', data={'text': '안전'})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('PRIVATE', response.text)
            self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_translation_service_rejects_empty_output_and_propagates_failure(self):
        with patch.object(processor_service, 'OpenAI') as factory:
            factory.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=' '))])
            with self.assertRaises(RuntimeError):
                processor_service.get_llm_response('NaOH 119', 'en')
            factory.return_value.chat.completions.create.side_effect = RuntimeError('failure')
            with self.assertRaises(RuntimeError):
                processor_service.get_llm_response('안전', 'en')

    def test_speech_settings_timeout_and_provider_errors(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture', 'TTS_MODEL': 'tts-1', 'TTS_VOICE': 'nova'}), patch.object(tts_service.requests, 'post') as post:
            post.return_value = SimpleNamespace(status_code=200, content=b'mp3')
            output = str(Path(self.directory.name) / 'speech.mp3')
            tts_service.text_to_speech('Call 119', output)
            self.assertEqual(Path(output).read_bytes(), b'mp3')
            self.assertEqual(post.call_args.kwargs['json']['input'], 'Call 119')
            self.assertEqual(post.call_args.kwargs['json']['response_format'], 'mp3')
            self.assertEqual(post.call_args.kwargs['timeout'], (10, 40))
            post.return_value = SimpleNamespace(status_code=429, content=b'PRIVATE')
            with self.assertRaisesRegex(RuntimeError, '^Speech provider failed$'):
                tts_service.text_to_speech('안전', output)


if __name__ == '__main__':
    unittest.main()
