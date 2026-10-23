// Presentation only: preserve the answer; never infer a missing contact or area code.
export function answerSections(text = '') {
  const sections = [];
  let current = { heading: '', text: '' };
  for (const line of text.split('\n')) {
    const heading = line.match(/^#{1,4}\s+(.+)/);
    if (heading) {
      if (current.heading || current.text.trim()) sections.push(current);
      current = { heading: heading[1], text: '' };
    } else current.text += (current.text ? '\n' : '') + line;
  }
  if (current.heading || current.text.trim()) sections.push(current);
  return sections;
}

export function answerContacts(text = '') {
  const contacts = [];
  const seen = new Set();
  // Complete Korean phone numbers or explicit emergency service numbers only.
  // A local number such as 760-2796 is retained in the answer but never auto-completed.
  const pattern = /(?<![\d+\-])(0(?:2|\d{2})[ -]?\d{3,4}[ -]?\d{4}|1(?:19|12))(?![\d\-])/g;
  for (const line of text.split('\n')) {
    for (const match of line.matchAll(pattern)) {
      const normalized = match[0].replace(/[ -]/g, '');
      if (seen.has(normalized)) continue;
      if (normalized.length === 3 && !/(전화|신고|연락|구조|소방|경찰|119|112)/.test(line.replace(match[0], ''))) continue;
      seen.add(normalized);
      contacts.push({ number: match[0], dialNumber: normalized, context: line.replace(/^[\s#*-]+/, '').trim(), dialable: true });
    }
  }
  return contacts;
}
