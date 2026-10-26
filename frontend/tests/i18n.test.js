import test from 'node:test';
import assert from 'node:assert/strict';
const saved = new Map();
globalThis.localStorage = { getItem: key => saved.get(key), setItem: (key,value) => saved.set(key,value) };
const { appLanguage, setLanguage, t } = await import('../src/utils/i18n.js');
test('one persisted language controls login, chat, and operations copy in all supported languages', () => {
  for (const language of ['en','zh','ja','vi']) {
    setLanguage(language);
    for (const copy of ['로그인', '상담 기록', '운영 현황', '한국어 원문 보기']) {
      assert.notEqual(t(copy), copy);
    }
    assert.equal(saved.get('safeops-language'), language);
  }
  setLanguage('ko');
  assert.equal(t('상담 기록'), '상담 기록');
  assert.equal(t(42),42);
  setLanguage('invalid');
  assert.equal(appLanguage.value,'ko');
});
