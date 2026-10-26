import { contactName } from './answerPresentation.js';

export const speechLanguages = [
  { code: 'ko', label: '한국어' },
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
  { code: 'vi', label: 'Tiếng Việt' },
];

export function translationFor(message, language) {
  const result = message.speechTranslation;
  return result?.target_language === language && result.original_text === message.text
    ? result : null;
}

export function contactTranslationInput(contacts = []) {
  return contacts.map(contact => ({
    id: `contact:${contact.dialNumber || contact.number}`,
    name: contactName(contact), availability: contact.availability || '',
  }));
}

export function localizedContacts(message, language, contacts = []) {
  const result = translationFor(message || {}, language);
  const originals = contactTranslationInput(contacts);
  if (language === 'ko' || !result || JSON.stringify(result.original_contacts) !== JSON.stringify(originals)) return contacts;
  const labels = Array.isArray(result.translated_contacts) ? result.translated_contacts : [];
  return contacts.map((contact, index) => {
    const label = labels.find(item => item.id === originals[index].id);
    if (!label || typeof label.name !== 'string' || !label.name.trim() || typeof label.availability !== 'string') return contact;
    return { ...contact, displayName: label.name, displayAvailability: label.availability, originalName: originals[index].name };
  });
}
