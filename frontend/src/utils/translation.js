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
