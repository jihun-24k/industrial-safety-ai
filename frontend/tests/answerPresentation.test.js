import test from 'node:test';
import assert from 'node:assert/strict';
import { answerSections, displayAnswerSections, answerContacts, contactName, answerFragments, compactSources, contactCondensedText, isInformationOnly, questionForReply, sectionEvidence } from '../src/utils/answerPresentation.js';

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
  assert.deepEqual(contacts.map(contactName), ['119 소방·구급', '원주세브란스 기독병원']);
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

test('hospital card uses the full institution name without introductory prose', () => {
  const [contact] = answerContacts('인근 병원은 원주세브란스 기독병원(033-741-0114)입니다.');
  assert.equal(contactName(contact), '원주세브란스 기독병원');
  assert.equal(contact.number, '033-741-0114');
  assert.equal(contactName({name:'원주 세브란스 기독병원',number:'033-741-0114'}), '원주세브란스 기독병원');
});

test('card evidence uses only its own citations and preserves document labels', () => {
  assert.deepEqual(sectionEvidence('위험 설명 (안전 매뉴얼 p.13). 추가 설명 (안전 매뉴얼 p.13).'), ['(안전 매뉴얼 p.13)']);
  assert.deepEqual(sectionEvidence('피부와 눈에 자극을 줄 수 있습니다.'), []);
  assert.deepEqual(sectionEvidence('설명 (문서 1, 2).'), ['(문서 1, 2)']);
});

test('confirmed 02 rule applies to local department numbers only', () => {
  const contacts = answerContacts('- 담당 부서: 대학본부 / 연구실 안전관리 — 760-2796 (주간).\n원주세브란스 기독병원(033-741-0114)\n병원: 741-0114\n소방서: 765-2119\n시설팀: 760-2609\n신고: 119');
  assert.deepEqual(contacts.map(c => c.number), ['02-760-2796', '033-741-0114', '02-760-2609', '119']);
  assert.equal(contactName(contacts[0]), '대학본부 / 연구실 안전관리');
  assert.equal(contacts[0].dialNumber, '027602796');
  assert.equal(contacts[0].rawNumber, '760-2796');
  assert.equal(contacts[0].areaCodeSource, 'user_confirmed_department_rule');
  assert.equal(answerContacts('대학본부 / 연구실 안전관리: 033-760-2796')[0].number, '033-760-2796');
});

test('department card titles omit contact introductory wording', () => {
  const [contact] = answerContacts('연락처는 대학본부 연구실 안전관리 부서: 760-2796');
  assert.equal(contactName(contact), '대학본부 / 연구실 안전관리');
  assert.equal(contactName({name:'연락처는 대학본부 연구실 안전관리 부서',number:'02-760-2796'}), '대학본부 / 연구실 안전관리');
});

test('URLs become short source labels without exposing link syntax', () => {
  assert.equal(compactSources('설명 [https://www.cdc.gov/niosh/npg/npgd0565.html].'), '설명 (출처: CDC/NIOSH).');
  assert.equal(compactSources('[가성소다](https://www.cdc.gov/niosh/npg/npgd0565.html)'), '가성소다 (출처: CDC/NIOSH)');
  assert.equal(compactSources('매뉴얼 p.32'), '매뉴얼 p.32');
  assert.equal(compactSources('https://example.org/doc?q=1'), '(출처: 외부 참고자료)');
  assert.equal(answerFragments('설명 [https://www.cdc.gov/niosh/npg/npgd0565.html].')[1].citation, true);
});

test('duplicate source wrapper becomes a single badge without removing safety prose', () => {
  const text = '주의해야 하며, 노출 시 즉시 세척해야 합니다 (CDC/NIOSH 가성소다(Sodium hydroxide) [https://www.cdc.gov/niosh/npg/npgd0565.html]).';
  assert.equal(compactSources(text), '주의해야 하며, 노출 시 즉시 세척해야 합니다 (출처: CDC/NIOSH).');
  assert.equal(compactSources('CDC/NIOSH에 따르면 위험합니다.'), 'CDC/NIOSH에 따르면 위험합니다.');
});

test('waste department headings exclude narrative for local and full numbers', () => {
  for (const number of ['760-2611', '02-760-2611']) {
    const [contact] = answerContacts(`· 연락처: 주간에만 연락 가능한 대학본부 폐시약/폐기물관리 부서의 연락처는 ${number}입니다.`);
    assert.equal(contactName(contact), '대학본부 / 폐시약·폐기물관리');
    assert.equal(contact.dialNumber, '027602611');
  }
  assert.equal(contactName({name:'주간에만 연락 가능한 대학본부 소방 안전관리 부서의 연락처는'}), '대학본부 / 소방 안전관리');
});

test('information comparisons hide contacts but actual incidents and contact requests do not', () => {
  assert.equal(isInformationOnly('가성소다와 암모니아의 NFPA 값을 건강·화재·반응 위험성별로 비교해줘'), true);
  for (const q of ['염산을 쏟았어 위험성도 알려줘', '암모니아 누출됐어', '위험성 비교와 담당 연락처 알려줘']) assert.equal(isInformationOnly(q), false);
  const messages = [{role:'user',text:'염산을 쏟았어'}, {role:'assistant'}, {role:'user',text:'NFPA 비교해줘'}, {role:'assistant'}];
  assert.equal(questionForReply(messages,messages[3]), 'NFPA 비교해줘');
});

test('directory rows move to cards with evidence and hours, unresolved rows remain', () => {
  const row = '- 담당 부서: 대학본부 / 연구실 안전관리 — 760-2796 (주간). 문서에 수록된 기관 연락처. (안전 매뉴얼 p.32)';
  const text = `즉시 보고하세요.\n\n연락 안내\n${row}`;
  const contacts = answerContacts(text);
  assert.equal(contactCondensedText(text, contacts), '즉시 보고하세요.\n\n(안전 매뉴얼 p.32)');
  assert.equal(contacts[0].availability, '주간');
  assert.deepEqual(contacts[0].sources, ['(안전 매뉴얼 p.32)']);
  assert.equal(contactCondensedText(text, []), text);
  const hospital = '- 병원: 병원 — 741-0114 (주간/야간). 문서에 수록된 기관 연락처.';
  assert.ok(contactCondensedText(text+'\n'+hospital, contacts).includes(hospital));
});

test('department and hospital sections combine with concise names and one source', () => {
  const text = '1. 즉시 조치: 원문 유지\n4. 담당 부서: 대학본부 연구실 안전관리 부서에 연락합니다. 전화번호는 760-2796이며, 주간에 연락 가능합니다 (안전 매뉴얼 p.32).\n5. 병원: 원주세브란스 기독병원에 연락합니다. 전화번호는 033-741-0114이며, 주간 및 야간에 연락 가능합니다 (안전 매뉴얼 p.32).';
  const sections = displayAnswerSections(text);
  assert.equal(sections.length, 2);
  assert.equal(sections[1].heading, '담당 연락처');
  assert.equal(sections[1].text.split('(안전 매뉴얼 p.32)').length, 2);
  assert.ok(sections[1].text.includes('원주세브란스 기독병원'));
  assert.equal(sections[0].text, '원문 유지');
});

test('combined contacts retain purpose and availability in sentences', () => {
  const text = '4. 담당 부서: 연구실 안전관리 담당 부서에 연락합니다. 전화번호는 760-2796이며, 주간에 연락 가능합니다 (안전 매뉴얼 p.32).\n5. 병원: 원주세브란스 기독병원에 연락하여 응급조치를 받습니다. 전화번호는 033-741-0114이며, 주간 및 야간에 연락 가능합니다 (안전 매뉴얼 p.32).';
  const [section] = displayAnswerSections(text);
  assert.equal(section.heading, '담당 연락처');
  assert.ok(section.text.includes('연구실 안전관리 담당 부서에 연락합니다.'));
  assert.ok(section.text.includes('원주세브란스 기독병원에 연락하여 응급조치를 받습니다.'));
  assert.ok(section.text.includes('주간 및 야간에 연락 가능합니다'));
  assert.ok(!section.text.includes('전화번호는'));
});
