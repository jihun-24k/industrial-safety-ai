// Presentation only: preserve the answer; never infer a missing contact or area code.
export function answerSections(text = '') {
  const sections = [];
  let current = { heading: '', text: '' };
  for (const line of text.split('\n')) {
    const heading = line.match(/^#{1,4}\s+(.+)/);
    const item = line.match(/^\s*(\d+)[.)]\s+(?:\*\*)?([^:：\n]{1,40}?)(?:\*\*)?[:：](?:\*\*)?\s*(.*)$/);
    if (heading) {
      if (current.heading || current.text.trim()) sections.push(current);
      current = { heading: heading[1], text: '' };
    } else if (item) {
      if (current.heading || current.text.trim()) sections.push(current);
      current = { heading: item[2].trim(), number: item[1], text: item[3] };
    } else current.text += (current.text ? '\n' : '') + line;
  }
  if (current.heading || current.text.trim()) sections.push(current);
  return sections;
}

// Keep citations beside the claim they support; only their visual treatment changes.
export function answerFragments(text = '') {
  const pattern = /\((?:문서\s*\d+(?:\s*[,·]\s*\d+)*|[^()\n]{1,100}\s+p\.\s*\d+(?:\s*[-–,]\s*\d+)*|[^()\n]{1,100}\s+\d+쪽)\)|\[(?:문서\s*)?\d+(?:\s*[,·]\s*\d+)*\]/g;
  const fragments = [];
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > offset) fragments.push({ text: text.slice(offset, match.index), citation: false });
    fragments.push({ text: match[0], citation: true });
    offset = match.index + match[0].length;
  }
  if (offset < text.length) fragments.push({ text: text.slice(offset), citation: false });
  return fragments;
}

function cleanContactLabel(label = '') {
  if (/대학본부/.test(label) && /연구실\s*안전관리/.test(label)) return '대학본부 / 연구실 안전관리';
  return label.replace(/^(?:(?:담당\s*)?연락처(?:는|은)?|담당\s*부서(?:는|은)?|문의처(?:는|은)?)\s*[:：]?\s*/, '').trim();
}

// Use the institution immediately attached to this number, not the whole paragraph.
export function contactName(contact = {}) {
  const number = (contact.dialNumber || contact.number || '').replace(/[ -]/g, '');
  if (number === '119') return '119 소방·구급';
  if (number === '112') return '112 경찰';
  // Display alias only when the supplied label names this institution.
  if (/원주\s*세브란스/.test(contact.name || contact.context || '')) return '원주세브란스 기독병원';
  if (contact.name) return cleanContactLabel(contact.name);
  const context = (contact.context || '').replace(/\*\*/g, '');
  const offset = context.indexOf(contact.number || '');
  const prefix = offset >= 0 ? context.slice(0, offset) : context;
  const match = prefix.match(/([가-힣A-Za-z0-9·]+(?:[ \t]+[가-힣A-Za-z0-9·]+){0,3}(?:병원|의료원|소방서|경찰서|지구대|센터|관리자|관리팀|담당부서|부서|안전관리|당직실))\s*[:：(（·-]?\s*$/);
  return match ? match[1].replace(/^(?:필요 시|또는|및|인근 병원은|인근 병원|담당 부서는)\s+/, '').trim() : '연락처';
}

export function answerContacts(text = '') {
  const contacts = [];
  const seen = new Set();
  // User-confirmed operating rule: department local numbers use Seoul (02).
  // External institutions and already complete numbers retain their original numbers.
  const pattern = /(?<![\d+\-])(0(?:2|\d{2})[ -]?\d{3,4}[ -]?\d{4}|1(?:19|12)|[1-9]\d{2,3}-\d{4})(?![\d\-])/g;
  for (const line of text.split('\n')) {
    for (const match of line.matchAll(pattern)) {
      const rawNumber = match[0];
      const local = /^[1-9]\d{2,3}-\d{4}$/.test(rawNumber);
      const prefix = line.slice(0, match.index).replace(/\*\*/g, '');
      const label = prefix.split(/[。.!?]|(?:합니다|하세요|입니다)[.]?|[,;]/).at(-1).replace(/^[\s#*\-\d.)]+/, '').replace(/^담당\s*부서\s*[:：]\s*/, '').replace(/\s*[—–:：(（-]\s*$/, '').trim();
      const department = /대학본부|연구실\s*안전관리|담당\s*부서|당직실|시설(?:팀|부|과)|폐시약|폐기물관리|소방\s*안전관리/.test(label) && !/병원|의료원|소방서|경찰서|지구대/.test(label);
      if (local && !department) continue;
      const normalized = (local ? '02' : '') + rawNumber.replace(/[ -]/g, '');
      if (seen.has(normalized)) continue;
      if (normalized.length === 3 && !/(전화|신고|연락|구조|소방|경찰|119|112)/.test(line.replace(match[0], ''))) continue;
      seen.add(normalized);
      contacts.push({ number: local ? `02-${rawNumber}` : rawNumber, rawNumber, name: local ? cleanContactLabel(label) : undefined, dialNumber: normalized, areaCodeSource: local ? 'user_confirmed_department_rule' : undefined, context: line.replace(/^[\s#*-]+/, '').trim(), dialable: true });
    }
  }
  return contacts;
}

// Section evidence comes only from citations actually present in that section.
// The response-wide sources list is not a numbered document lookup table.
export function sectionEvidence(text = '') {
  return [...new Set(answerFragments(text).filter(part => part.citation).map(part => part.text))];
}
