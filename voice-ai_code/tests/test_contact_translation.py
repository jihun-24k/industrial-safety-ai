import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('JWT_SECRET', 'translation-test-secret')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import tts_router
from app.services import contact_translation as service

CONTACTS = [{'id': 'contact:027602796', 'name': '연구실 안전관리', 'availability': '주간 / 야간'},
            {'id': 'contact:119', 'name': '119 소방·구급', 'availability': ''}]
LABELS = [{'id': 'contact:027602796', 'name': 'Laboratory Safety Management', 'availability': 'Daytime / Nighttime'},
          {'id': 'contact:119', 'name': '119 Fire and Ambulance', 'availability': ''}]


class ContactTranslationTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(tts_router.router, prefix='/tts')
        app.dependency_overrides[tts_router.get_current_user] = lambda: {'id': 'test', 'username': 'test'}
        self.client = TestClient(app)
        self.contacts = service.parse_contacts(json.dumps(CONTACTS))

    def provider_response(self, data):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))])

    def test_contacts_translate_in_one_model_call_and_keep_original_ids_and_order(self):
        with patch.object(service, 'OpenAI') as provider:
            provider.return_value.chat.completions.create.return_value = self.provider_response({
                'translated_text': 'Call 119.', 'contacts': list(reversed(LABELS)),
            })
            answer, labels = service.translate_answer('119에 연락하세요.', 'en', self.contacts)
            self.assertEqual(answer, 'Call 119.')
            self.assertEqual(labels, LABELS)
            provider.return_value.chat.completions.create.assert_called_once()
            payload = json.loads(provider.return_value.chat.completions.create.call_args.kwargs['messages'][1]['content'])
            self.assertEqual(payload['contacts'], CONTACTS)

    def test_changed_ids_extra_fields_and_invented_or_missing_hours_are_rejected(self):
        invalid = [[], [LABELS[0], LABELS[0]], [{**LABELS[0], 'id': 'changed'}, LABELS[1]],
                   [{**LABELS[0], 'dialNumber': '911'}, LABELS[1]],
                   [LABELS[0], {**LABELS[1], 'availability': '24 hours'}],
                   [{**LABELS[0], 'availability': ''}, LABELS[1]],
                   [LABELS[0], {**LABELS[1], 'name': '112 Police'}],
                   [{**LABELS[0], 'name': ' '}, LABELS[1]]]
        with patch.object(service, 'OpenAI') as provider:
            for labels in invalid:
                provider.return_value.chat.completions.create.return_value = self.provider_response({'translated_text': 'Call 119.', 'contacts': labels})
                with self.assertRaises(ValueError):
                    service.translate_answer('119에 연락하세요.', 'en', self.contacts)

    def test_korean_labels_bypass_model(self):
        with patch.object(service, 'OpenAI') as provider:
            self.assertEqual(service.translate_answer('원문', 'ko', self.contacts), ('원문', CONTACTS))
            provider.assert_not_called()

    def test_request_validation_prevents_translation_and_speech(self):
        invalid = ['not json', 'null', json.dumps([CONTACTS[0], CONTACTS[0]]),
                   json.dumps([{**CONTACTS[0], 'dialNumber': '911'}]), json.dumps([CONTACTS[0]] * 21)]
        with patch.object(tts_router, 'translate_answer') as translate, patch.object(tts_router, 'text_to_speech') as speech:
            for value in invalid:
                response = self.client.post('/tts/', data={'text': '원문', 'target_language': 'en', 'contacts': value})
                self.assertEqual(response.status_code, 400)
            translate.assert_not_called()
            speech.assert_not_called()

    def test_api_returns_source_labels_and_translation_with_exact_synthesized_answer(self):
        with patch.object(tts_router, 'translate_answer', return_value=('Call 119.', LABELS)) as translate, patch.object(tts_router, 'text_to_speech') as speech:
            response = self.client.post('/tts/', data={'text': '119에 연락하세요.', 'target_language': 'en', 'contacts': json.dumps(CONTACTS)})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['original_contacts'], CONTACTS)
            self.assertEqual(data['translated_contacts'], LABELS)
            self.assertEqual(speech.call_args.args[0], data['translated_text'])
            translate.assert_called_once()

    def test_translation_failure_is_sanitized_and_never_synthesized(self):
        with patch.object(tts_router, 'translate_answer', side_effect=RuntimeError('PRIVATE_PROVIDER')), patch.object(tts_router, 'text_to_speech') as speech:
            response = self.client.post('/tts/', data={'text': '원문', 'target_language': 'en', 'contacts': json.dumps(CONTACTS)})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('PRIVATE', response.text)
            speech.assert_not_called()
