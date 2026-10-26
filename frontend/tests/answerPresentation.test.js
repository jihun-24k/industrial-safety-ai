import test from 'node:test';
import assert from 'node:assert/strict';
import { answerSections, answerContacts, contactName, answerFragments, sectionEvidence } from '../src/utils/answerPresentation.js';

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

test('contact titles use the institution beside each number without repeating instructions', () => {
  const contacts = answerContacts('3. 보고·후속 처리: 필요 시 119에 신고합니다.\n4. 담당 부서·연락처: 연구실 책임자에게 연락합니다. 필요 시 원주세브란스 기독병원(033-741-0114)으로 연락합니다.');
  assert.deepEqual(contacts.map(contactName), ['119 소방·구급', '원주 세브란스']);
  assert.equal(contactName({number:'112'}), '112 경찰');
  assert.equal(contactName({number:'02-123-4567', context:'확인 후 02-123-4567에 전화하세요.'}), '연락처');
});

test('numbered inline headings become separate cards while body and citations remain intact', () => {
  const sections = answerSections('1. 즉시 조치: 본문 (문서 1, 2).\n다음 줄\n\n2. **물질 위험성·주의사항:** 주의 (안전관리 매뉴얼 p.13).\n3. 보고·후속 처리: 보고');
  assert.deepEqual(sections.map(s => s.heading), ['즉시 조치', '물질 위험성·주의사항', '보고·후속 처리']);
  assert.equal(sections[0].text, '본문 (문서 1, 2).\n다음 줄\n');
  assert.equal(sections[1].text, '주의 (안전관리 매뉴얼 p.13).');
  assert.equal(answerSections('1. 보호구 착용\n2. 현장 확인').length, 1);
});
test('citation styling preserves all text and does not turn conditions into sources', () => {
  const text = '조치 (문서 1, 2). 확인 (안전관리 매뉴얼 p.30). 조건 (가능한 경우). [3] <script>';
  const fragments = answerFragments(text);
  assert.equal(fragments.map(f => f.text).join(''), text);
  assert.deepEqual(fragments.filter(f => f.citation).map(f => f.text), ['(문서 1, 2)', '(안전관리 매뉴얼 p.30)', '[3]']);
});

test('hospital card uses the requested short label without introductory prose', () => {
  const [contact] = answerContacts('인근 병원은 원주세브란스 기독병원(033-741-0114)입니다.');
  assert.equal(contactName(contact), '원주 세브란스');
  assert.equal(contact.number, '033-741-0114');
  assert.equal(contactName({name:'원주 세브란스 기독병원',number:'033-741-0114'}), '원주 세브란스');
});

test('card evidence uses only its own citations and preserves document labels', () => {
  assert.deepEqual(sectionEvidence('위험 설명 (안전 매뉴얼 p.13). 추가 설명 (안전 매뉴얼 p.13).'), ['(안전 매뉴얼 p.13)']);
  assert.deepEqual(sectionEvidence('피부와 눈에 자극을 줄 수 있습니다.'), []);
  assert.deepEqual(sectionEvidence('설명 (문서 1, 2).'), ['(문서 1, 2)']);
});
