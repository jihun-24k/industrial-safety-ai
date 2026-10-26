// 운영 대시보드 표시용 순수 함수 (node --test로 검증)

export function formatPercent(value) {
  return value === null || value === undefined ? '–' : `${Math.round(value * 1000) / 10}%`;
}

export function formatLatency(ms) {
  if (ms === null || ms === undefined) return '–';
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}초`;
}

export function formatCount(value) {
  return value === null || value === undefined ? '–' : Number(value).toLocaleString('ko-KR');
}

export function formatDateTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = n => String(n).padStart(2, '0');
  return `${pad(date.getMonth() + 1)}.${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function shortDate(isoDate) {
  const [, month, day] = String(isoDate || '').split('-');
  return month && day ? `${Number(month)}/${Number(day)}` : '';
}

// 일별 막대 차트: 하나의 축척(최댓값 기준)으로 질문 수와 handoff 수를 같은 높이 체계에 그린다.
export function dailyBars(daily = [], height = 120) {
  const max = Math.max(1, ...daily.map(day => day.questions || 0));
  const niceMax = max <= 5 ? max : Math.ceil(max / 5) * 5;
  return {
    max: niceMax,
    ticks: [0, Math.round(niceMax / 2), niceMax],
    bars: daily.map(day => ({
      date: day.date,
      label: shortDate(day.date),
      questions: day.questions || 0,
      handoff: day.handoff || 0,
      questionHeight: Math.round(((day.questions || 0) / niceMax) * height),
      handoffHeight: Math.round(((day.handoff || 0) / niceMax) * height),
    })),
  };
}

// 한 로그 카드에 붙일 상태 칩 (상태를 색·글자 둘 다로 표시)
export function logChips(log) {
  const chips = [];
  if (log.handoff) chips.push({ kind: 'critical', label: '근거 없음 · 담당자 연결' });
  if (log.needs_review) chips.push({ kind: 'warning', label: '긴급 안내' });
  if (log.used_history) chips.push({ kind: 'info', label: '이전 대화 참고' });
  if (log.typo_fixes?.length) chips.push({ kind: 'info', label: `오탈자 보정 ${log.typo_fixes.map(pair => pair.join('→')).join(', ')}` });
  if (log.verified_qa_ids?.length) chips.push({ kind: 'good', label: `검증 Q&A 활용 #${log.verified_qa_ids.join(', #')}` });
  if (log.feedback === 1) chips.push({ kind: 'good', label: '▲ 도움됨' });
  if (log.feedback === -1) chips.push({ kind: 'critical', label: '▼ 아쉬움' });
  return chips;
}
