import test from 'node:test';
import assert from 'node:assert/strict';
import { formatPercent, formatLatency, dailyBars, logChips, shortDate } from '../src/utils/opsFormat.js';

test('지표 숫자를 읽기 쉬운 글자로 바꾼다', () => {
  assert.equal(formatPercent(0.1234), '12.3%');
  assert.equal(formatPercent(null), '–');
  assert.equal(formatLatency(850), '850ms');
  assert.equal(formatLatency(4200), '4.2초');
  assert.equal(shortDate('2026-10-05'), '10/5');
});

test('일별 막대는 하나의 축척을 쓴다', () => {
  const chart = dailyBars([{ date: '2026-10-25', questions: 7, handoff: 2 }, { date: '2026-10-26', questions: 3, handoff: 0 }], 100);
  assert.equal(chart.max, 10);
  assert.deepEqual(chart.ticks, [0, 5, 10]);
  assert.equal(chart.bars[0].questionHeight, 70);
  assert.equal(chart.bars[0].handoffHeight, 20);
});

test('로그 상태 칩', () => {
  const chips = logChips({ handoff: true, typo_fixes: [['염화수수', '염화수소']], verified_qa_ids: [3], feedback: -1 });
  assert.deepEqual(chips.map(c => c.kind), ['critical', 'info', 'good', 'critical']);
  assert.match(chips[1].label, /염화수수→염화수소/);
});
