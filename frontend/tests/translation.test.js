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

test('restored foreign questions retain original text and Korean processing metadata', async () => {
  const { mapStoredMessage } = await import('../src/api/ragApi.js');
  const message = mapStoredMessage({
    id: 1, role: 'user', text: 'Then what?', normalized_text: '그다음에는?', source_language: 'en',
  });
  assert.equal(message.text, 'Then what?');
  assert.equal(message.normalizedText, '그다음에는?');
  assert.equal(message.sourceLanguage, 'en');
  const legacy = mapStoredMessage({ id: 2, role: 'user', text: '기존 질문' });
  assert.equal(legacy.normalizedText, '');
  assert.equal(legacy.sourceLanguage, 'und');
});

test('stream delivers Korean interpretation before answer tokens and propagates translation errors', async () => {
  const { ragApi } = await import('../src/api/ragApi.js');
  const original = globalThis.fetch;
  const events = [];
  const stream = parts => new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(parts.join('')));
      controller.close();
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } });
  try {
    globalThis.fetch = async (_url, options) => {
      assert.equal(JSON.parse(options.body).prompt, 'Then what?');
      return stream([
        'event: status\ndata: {"phase":"translating","message":"번역 중"}\n\n',
        'event: normalized\ndata: {"normalized_prompt":"그다음에는?","source_language":"en"}\n\n',
        'event: token\ndata: {"text":"답변"}\n\n',
        'event: done\ndata: {"prompt":"Then what?","normalized_prompt":"그다음에는?","source_language":"en","answer":"답변"}\n\n',
      ]);
    };
    const result = await ragApi.queryStream({ prompt: 'Then what?' }, {
      onStatus: value => events.push(value.phase),
      onNormalized: value => events.push(value.normalized_prompt),
      onToken: value => events.push(value),
    });
    assert.deepEqual(events, ['translating', '그다음에는?', '답변']);
    assert.equal(result.prompt, 'Then what?');
    globalThis.fetch = async () => stream(['event: error\ndata: {"message":"번역 실패"}\n\n']);
    await assert.rejects(ragApi.queryStream({ prompt: 'Then what?' }), /번역 실패/);
  } finally { globalThis.fetch = original; }
});

test('contact translation only replaces display labels and invalidates changed source metadata', async () => {
  const { contactTranslationInput, localizedContacts } = await import('../src/utils/translation.js');
  const contacts = [{ number: '02-760-2796', dialNumber: '027602796', name: '연구실 안전관리', availability: '주간 / 야간', dialable: true }];
  const input = contactTranslationInput(contacts);
  const message = { text: '원문', speechTranslation: { original_text: '원문', target_language: 'en', original_contacts: input,
    translated_contacts: [{ id: input[0].id, name: 'Laboratory Safety Management', availability: 'Daytime / Nighttime', number: '911', dialNumber: '911' }] } };
  const result = localizedContacts(message, 'en', contacts);
  assert.equal(result[0].displayName, 'Laboratory Safety Management');
  assert.equal(result[0].displayAvailability, 'Daytime / Nighttime');
  assert.equal(result[0].number, contacts[0].number);
  assert.equal(result[0].dialNumber, contacts[0].dialNumber);
  assert.equal(result[0].originalName, contacts[0].name);
  assert.equal(localizedContacts(message, 'ko', contacts), contacts);
  assert.equal(localizedContacts(message, 'vi', contacts), contacts);
  assert.equal(localizedContacts({ ...message, text: '변경된 원문' }, 'en', contacts), contacts);
  const changed = [{ ...contacts[0], availability: '주간' }];
  assert.equal(localizedContacts(message, 'en', changed), changed);
  assert.equal(contacts[0].displayName, undefined);
});

test('speech API includes only contact IDs and translatable labels in the request', async () => {
  const { contactTranslationInput } = await import('../src/utils/translation.js');
  const original = globalThis.fetch;
  try {
    const input = contactTranslationInput([{ number: '119', dialNumber: '119' }]);
    globalThis.fetch = async (_url, options) => {
      assert.deepEqual(JSON.parse(options.body.get('contacts')), input);
      assert.deepEqual(Object.keys(input[0]), ['id', 'name', 'availability']);
      return Response.json({ file_path: '/uploads/test.mp3' });
    };
    await voiceApi.synthesize('신고하세요', 'en', input);
  } finally { globalThis.fetch = original; }
});
