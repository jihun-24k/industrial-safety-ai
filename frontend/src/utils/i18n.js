import { ref, reactive } from 'vue';
import catalog from './uiCatalog.json' with { type: 'json' };
const codes = new Set(['ko','en','zh','ja','vi']);
const saved = globalThis.localStorage?.getItem('safeops-language');
export const appLanguage = ref(codes.has(saved) ? saved : 'ko');
export function setLanguage(code) {
  if (!codes.has(code)) return;
  appLanguage.value = code;
  globalThis.localStorage?.setItem('safeops-language', code);
  if (typeof document !== 'undefined') document.documentElement.lang = code;
}
const dynamic = reactive({});
const pending = new Set();
const waiting = {en:'Translating…',zh:'翻译中…',ja:'翻訳中…',vi:'Đang dịch…'};
function translateDynamic(key, code) {
  const id = code + ':' + key;
  if (pending.has(id) || dynamic[id]) return;
  pending.add(id);
  fetch('/voice-api/tts/translate', {method:'POST', credentials:'include', body:new URLSearchParams({text:key,target_language:code})})
    .then(r => { if (!r.ok) throw new Error('translation'); return r.json(); })
    .then(data => { dynamic[id] = data.translated_text; })
    .catch(() => { dynamic[id] = {en:'Translation unavailable',zh:'暂时无法翻译',ja:'翻訳できません',vi:'Không thể dịch'}[code]; })
    .finally(() => pending.delete(id));
}
export function t(value) {
  if (typeof value !== 'string' || appLanguage.value === 'ko') return value;
  const key = value.trim();
  const translated = catalog[appLanguage.value]?.[key];
  if (translated) return value.replace(key, translated);
  if (!/[가-힣]/.test(key)) return value;
  const id = appLanguage.value + ':' + key;
  translateDynamic(key, appLanguage.value);
  return dynamic[id] || waiting[appLanguage.value];
}

if (typeof document !== 'undefined') document.documentElement.lang = appLanguage.value;
