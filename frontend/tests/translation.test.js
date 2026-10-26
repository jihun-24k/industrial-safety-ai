import test from 'node:test';
import assert from 'node:assert/strict';
import { voiceApi } from '../src/api/voiceApi.js';
import { translationFor } from '../src/utils/translation.js';

test('speech API sends selected language, preserves Korean default, and includes cookies', async () => {
  const original = globalThis.fetch;
  try {
    const languages = [];
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/voice-api/tts/');
      assert.equal(options.credentials, 'include');
      assert.equal(options.body.get('text'), 'NaOH를 만지지 마세요. 119');
      languages.push(options.body.get('target_language'));
      return Response.json({ file_path: '/uploads/fixture.mp3' });
    };
    await voiceApi.synthesize('NaOH를 만지지 마세요. 119');
    for (const lang of ['en', 'zh', 'ja', 'vi']) await voiceApi.synthesize('NaOH를 만지지 마세요. 119', lang);
    assert.deepEqual(languages, ['ko', 'en', 'zh', 'ja', 'vi']);
  } finally { globalThis.fetch = original; }
});

test('language changes and edited answers hide translations for a different source or language', () => {
  const result = { original_text: '원문', translated_text: 'Translation', target_language: 'en' };
  const message = { text: '원문', speechTranslation: result };
  assert.equal(translationFor(message, 'en'), result);
  assert.equal(translationFor(message, 'vi'), null);
  assert.equal(translationFor({ ...message, text: '다른 원문' }, 'en'), null);
  assert.equal(translationFor({ text: '원문' }, 'en'), null);
});
