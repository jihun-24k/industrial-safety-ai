// Presentation only: preserve the answer; never infer a missing contact or area code.
export function answerSections(text = '') {
  const sections = [];
  let current = { heading: '', text: '' };
  for (const line of text.split('\n')) {
    const heading = line.match(/^#{1,4}\s+(.+)/);
    const item = line.match(/^\s*(\d+)[.)]\s+(?:\*\*)?([^:：\n]{1,120}?)(?:\*\*)?[:：](?:\*\*)?\s*(.*)$/);
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

// Display-only formatting: retain raw answers/sources for provenance.
export function compactSources(text = '') {
  const labelFor = url => {
    try {
      const host = new URL(url).hostname.toLowerCase().replace(/^www\./, '');
      if (host === 'cdc.gov' || host.endsWith('.cdc.gov')) return /\/niosh(?:\/|$)/i.test(new URL(url).pathname) ? 'CDC/NIOSH' : 'CDC';
      if (host === 'osha.gov' || host.endsWith('.osha.gov')) return 'OSHA';
      if (host === 'kosha.or.kr' || host.endsWith('.kosha.or.kr')) return '한국산업안전보건공단';
      return '외부 참고자료';
    } catch { return '외부 참고자료'; }
  };
  return text
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => /^https?:\/\//.test(label) ? `(출처: ${labelFor(url)})` : `${label} (출처: ${labelFor(url)})`)
    .replace(/\[?(https?:\/\/[^\s\]<>)]*[^\s\]<>).,;])\]?/g, (_, url) => `(출처: ${labelFor(url)})`)
    // Collapse only citation wrappers, including parenthesized English document titles.
    .replace(/\((CDC\/NIOSH|CDC|OSHA|한국산업안전보건공단)\s+(?:[^()\n]|\((?!출처:)[^()\n]*\)){0,200}?\s*\(출처: \1\)\s*\)/g, (_, source) => `(출처: ${source})`);
}

// Keep citations beside the claim they support; only their visual treatment changes.
export function answerFragments(text = '') {
  text = compactSources(text);
  const pattern = /\((?:출처: [^()\n]+|문서\s*\d+(?:\s*[,·]\s*\d+)*|[^()\n]{1,100}\s+p\.\s*\d+(?:\s*[-–,]\s*\d+)*|[^()\n]{1,100}\s+\d+쪽)\)|\[(?:문서\s*)?\d+(?:\s*[,·]\s*\d+)*\]/g;
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
  const organization = /대학\s*본부/.test(label) ? '대학본부 / ' : '';
  if (/폐시약\s*[/·ㆍ및]+\s*폐기물\s*관리/.test(label)) return `${organization}폐시약·폐기물관리`;
  if (/연구실\s*안전관리/.test(label)) return `${organization}연구실 안전관리`;
  if (/소방\s*안전관리/.test(label)) return `${organization}소방 안전관리`;
  if (/폐기물\s*관리/.test(label)) return `${organization}폐기물관리`;
  if (/폐시약\s*관리/.test(label)) return `${organization}폐시약관리`;
  const cleaned = label.replace(/^[\s·•#*—–-]+/, '')
    .replace(/^(?:(?:담당\s*)?연락처(?:는|은)?|담당\s*부서(?:는|은)?|문의처(?:는|은)?)\s*[:：]?\s*/, '')
    .replace(/^(?:주간|야간)에만\s*연락\s*가능한\s*/, '')
    .replace(/(?:의\s*)?(?:연락처|전화번호)(?:는|은)?\s*[:：]?\s*$/, '').trim();
  return cleaned || '연락처';
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
      let label = prefix.split(/[。.!?]|(?:합니다|하세요|입니다)[.]?|[,;]/).at(-1).replace(/^[\s#*\-\d.)]+/, '').replace(/^담당\s*부서\s*[:：]\s*/, '').replace(/\s*[—–:：(（-]\s*$/, '').trim();
      if (/^(?:전화번호|연락처)(?:는|은)?$/.test(label)) {
        const previous = prefix.match(/(?:대학\s*본부[^.\n]{0,60}|연구실\s*안전관리[^.\n]{0,40}|원주\s*세브란스[^.\n]{0,40})/);
        if (previous) label = previous[0];
      }
      const department = /대학본부|연구실\s*안전관리|담당\s*부서|당직실|시설(?:팀|부|과)|폐시약|폐기물관리|소방\s*안전관리/.test(label) && !/병원|의료원|소방서|경찰서|지구대/.test(label);
      if (local && !department) continue;
      const normalized = (local ? '02' : '') + rawNumber.replace(/[ -]/g, '');
      if (seen.has(normalized)) continue;
      if (normalized.length === 3 && !/(전화|신고|연락|구조|소방|경찰|119|112)/.test(line.replace(match[0], ''))) continue;
      seen.add(normalized);
      contacts.push({ sources: sectionEvidence(line), availability: line.match(/\((주간\s*\/\s*야간|주간|야간)\)/)?.[1] || '', number: local ? `02-${rawNumber}` : rawNumber, rawNumber, name: department ? cleanContactLabel(label) : undefined, dialNumber: normalized, areaCodeSource: local ? 'user_confirmed_department_rule' : undefined, context: line.replace(/^[\s#*-]+/, '').trim(), dialable: true });
    }
  }
  return contacts;
}

// Section evidence comes only from citations actually present in that section.
// The response-wide sources list is not a numbered document lookup table.
export function sectionEvidence(text = '') {
  return [...new Set(answerFragments(text).filter(part => part.citation).map(part => part.text))];
}

// Presentation guard for current and stored responses; explicit incident/contact requests win.
export function isInformationOnly(question = '') {
  if (/연락|전화|신고|담당|병원|구조|쏟|튀었|튄|묻었|접촉했|누출됐|누출된|누출 중|새고|다쳤|쓰러|기침|어지러|불이 났|불이 나|화재가|발생했|발생한|대응|대처|응급/.test(question)) return false;
  return /비교|차이|뜻|의미|정의|NFPA|GHS|위험성|등급|특성|분류|기준/i.test(question);
}
export function questionForReply(messages, reply) {
  const index = messages.indexOf(reply);
  const question = messages.slice(0, index).reverse().find(message => message.role === 'user');
  return question?.normalizedText || question?.text || '';
}

// Hide only generated directory rows already represented by a contact card.
// Keep procedural instructions and unresolved contacts in the original answer.
export function contactCondensedText(text = '', contacts = []) {
  const lines = text.split('\n');
  let directory = false;
  const result = [];
  const movedSources = new Set();
  for (const line of lines) {
    if (/^\s*(?:#{1,4}\s*)?연락 안내\s*$/.test(line)) {
      directory = true;
      result.push(line);
      continue;
    }
    if (directory && /^\s*#{1,4}\s/.test(line)) directory = false;
    const directoryRow = directory && /^\s*[-•]\s*(?:병원|담당 부서):/.test(line) && /문서에 수록된 기관 연락처/.test(line);
    const numbers = line.match(/(?<![\d-])(?:0\d{1,2}-)?\d{3,4}-\d{4}(?![\d-])/g) || [];
    const represented = numbers.length && numbers.every(number => contacts.some(contact => (contact.rawNumber || contact.number) === number || contact.number === number));
    if (!directoryRow || !represented) result.push(line);
    else sectionEvidence(line).forEach(source => movedSources.add(source));
  }
  const body = result.join('\n').replace(/(?:^|\n)\s*(?:#{1,4}\s*)?연락 안내\s*(?=\n\s*#|$)/g, '').trim();
  const sources = [...movedSources].filter(source => !body.includes(source));
  return body + (sources.length ? `\n\n${sources.join(' ')}` : '');
}

// Combine dedicated contact sections; preserve procedural sections unchanged.
export function displayAnswerSections(text = '') {
  const sections = answerSections(text);
  const result = [];
  let combined;
  const sources = new Set();
  const summaries = new Set();
  for (const section of sections) {
    const heading = section.heading.replace(/\*\*/g, '').trim();
    if (!/^(담당 부서|병원|담당 연락처|담당 부서[·/\s]*연락처|연락 안내)$/.test(heading)) {
      result.push(section);
      continue;
    }
    if (!combined) {
      combined = { heading: '담당 연락처', number: section.number, text: '' };
      result.push(combined);
    }
    sectionEvidence(section.text).forEach(source => sources.add(source));
    const contacts = answerContacts(section.text);
    // Preserve the original action and conditions, rather than replacing prose with labels.
    let explanation = answerFragments(section.text).filter(part => !part.citation).map(part => part.text).join('');
    if (contacts.length) {
      explanation = explanation.replace(/전화번호는\s*(?:0\d{1,2}-)?\d{3,4}-\d{4}(?:이며|이고|입니다)[,，]?\s*/g, '');
    }
    explanation = explanation.replace(/\s+\./g, '.').replace(/\.{2,}/g, '.').replace(/[ \t]+/g, ' ').trim();
    if (explanation) summaries.add(explanation);

  }
  if (combined) combined.text = [...summaries, ...sources].join('\n');
  return result;
}
