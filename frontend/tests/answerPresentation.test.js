import test from 'node:test';
import assert from 'node:assert/strict';
import { answerSections, answerContacts } from '../src/utils/answerPresentation.js';

test('answer sections retain every paragraph, repeated heading and literal HTML', () => {
  const text='서문\n\n## 상황 확인\n첫 내용\n\n## 상황 확인\n<script>alert(1)</script>\n끝';
  const sections=answerSections(text);
  assert.equal(sections.length,3);
  assert.equal(sections[1].heading,sections[2].heading);
  assert.equal(sections.map(s => s.heading ? `## ${s.heading}\n${s.text}` : s.text).join('\n'),text);
});
test('phone cards keep complete numbers and deduplicate without guessing local area codes', () => {
  const contacts=answerContacts('병원: 033-741-0114\n병원 재확인 033 741 0114\n구내: 760-2796\nCAS: 1310-73-2\n신고: 119\n매뉴얼 112쪽');
  assert.deepEqual(contacts.map(c=>c.dialNumber),['0337410114','119']);
  assert.equal(contacts[0].number,'033-741-0114');
});
test('long numbers and page references cannot become emergency phone links', () => {
  assert.deepEqual(answerContacts('119\n119쪽\n번호 1119\n123033-741-0114\n112페이지'),[]);
});
