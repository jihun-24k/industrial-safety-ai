import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { createSSRApp } from 'vue';
import { renderToString } from '@vue/server-renderer';

let server, MessageList;
before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });
  ({ default: MessageList } = await server.ssrLoadModule('/src/components/MessageList.vue'));
});
after(async () => { await server?.close(); });

const original = '## 즉시 조치\nNaOH를 만지지 마세요. (매뉴얼 p.5)\n## 보고\n담당자에게 알리세요.';
const translations = {
  en: '## Immediate action\nDo not touch NaOH. (매뉴얼 p.5)\n## Report\nNotify the supervisor. <script>alert(1)</script>',
  zh: '## 立即措施\n不要触摸 NaOH。(매뉴얼 p.5)\n## 报告\n通知负责人。',
  ja: '## 応急処置\nNaOH に触れないでください。(매뉴얼 p.5)\n## 報告\n担当者に知らせてください。',
  vi: '## Hành động khẩn cấp\nKhông chạm vào NaOH. (매뉴얼 p.5)\n## Báo cáo\nThông báo cho người phụ trách.',
};
function assistant(language = 'en') {
  return { id: 'reply', role: 'assistant', text: original, sources: ['매뉴얼 p.5'],
    contacts: [{ number: '02-760-2796', dialNumber: '027602796', name: '연구실 안전관리', dialable: true }],
    speechTranslation: { original_text: original, translated_text: translations[language], target_language: language },
  };
}
const render = (message, language = 'en', user = { role: 'user', text: 'NaOH를 쏟았어요' }) =>
  renderToString(createSSRApp(MessageList, { messages: [user, message], user: 'tester', speechLanguage: language }));

test('all translated languages share answer cards, numbered headings, citations, and original contact links', async () => {
  for (const language of Object.keys(translations)) {
    const html = await render(assistant(language), language);
    const primary = html.split('<details class="original-answer')[0];
    assert.equal((primary.match(/class="[^"]*\banswer-section glass-card/g) || []).length, 2);
    assert.match(primary, /answer-step/);
    assert.match(primary, /citation-badge/);
    assert.match(primary, /answer-section--immediate/);
    assert.ok(primary.includes(`lang="${language}"`));
    assert.ok(primary.includes(translations[language].split('\n')[0].slice(3)));
    assert.ok(!primary.includes('NaOH를 만지지 마세요.'));
    assert.match(html, /<details class="original-answer glass-card"><summary>한국어 원문 보기/);
    assert.ok(html.includes('NaOH를 만지지 마세요.'));
    assert.match(html, /href="tel:027602796"/);
    assert.match(html, /근거 문서 확인/);
    assert.ok(!html.includes('translation-card'));
  }
});

test('translated text remains escaped and language changes or stale results restore the original cards', async () => {
  const message = assistant();
  const translated = await render(message);
  assert.ok(!translated.includes('<script>alert(1)</script>'));
  assert.ok(translated.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
  for (const [value, language] of [[message, 'ko'], [message, 'vi'], [{ ...message, text: '수정된 원문' }, 'en']]) {
    const html = await render(value, language);
    assert.ok(!html.includes('class="original-answer'));
    assert.ok(!html.includes('Do not touch NaOH.'));
    assert.ok(html.includes(value.text === original ? 'NaOH를 만지지 마세요.' : value.text));
  }
});

test('normalized input preserves the existing information-only presentation for a translated answer', async () => {
  const html = await render({ ...assistant(), needsReview: true }, 'en', {
    role: 'user', text: 'Compare the NFPA values.', normalizedText: 'NFPA 위험성을 비교해줘',
  });
  assert.ok(!html.includes('class="response-contacts"'));
  assert.ok(!html.includes('추가 확인이 필요해요'));
});

test('translated contact cards keep source phone targets and show the original institution', async () => {
  const { contactTranslationInput } = await import('../src/utils/translation.js');
  const message = assistant();
  message.contacts[0].availability = '주간 / 야간';
  message.speechTranslation.original_contacts = contactTranslationInput(message.contacts);
  message.speechTranslation.translated_contacts = [{
    id: message.speechTranslation.original_contacts[0].id,
    name: 'Laboratory Safety Management', availability: 'Daytime / Nighttime',
  }];
  const html = await render(message);
  assert.match(html, /Laboratory Safety Management/);
  assert.match(html, /Daytime \/ Nighttime/);
  assert.match(html, /contact-original-name[^>]*lang="ko">연구실 안전관리/);
  assert.match(html, /☎ Call/);
  assert.match(html, /Open phone app/);
  assert.match(html, /href="tel:027602796"/);
  assert.ok(!html.includes('☎ 전화하기'));
});

test('contact button, preview, empty-state, and confirmation copy is localized for every supported language', async () => {
  const { default: ContactCards } = await server.ssrLoadModule('/src/components/ContactCards.vue');
  const { contactUi } = await import('../src/utils/contactUi.js');
  for (const language of ['ko', 'en', 'zh', 'ja', 'vi']) {
    const copy = contactUi(language);
    const contacts = [{ number: '119', dialNumber: '119', dialable: true }];
    const live = await renderToString(createSSRApp(ContactCards, { contacts, language }));
    assert.ok(live.includes(copy.call));
    assert.ok(live.includes(copy.confirm));
    assert.ok(live.includes(copy.open));
    assert.match(live, /href="tel:119"/);
    const preview = await renderToString(createSSRApp(ContactCards, { contacts, language, demo: true }));
    assert.ok(preview.includes(copy.preview));
    assert.ok(!preview.includes('href="tel:'));
    const empty = await renderToString(createSSRApp(ContactCards, { contacts: [], language }));
    assert.ok(empty.includes(copy.empty));
    assert.ok(empty.includes(copy.note));
  }
});
