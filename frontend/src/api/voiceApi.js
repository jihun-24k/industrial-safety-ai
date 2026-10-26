import { request } from './client.js';

export const voiceApi = {
  openStream() {
    const url = new URL('/voice-api/stt/stream', window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return new WebSocket(url);
  },
  translate(text, targetLanguage, contacts = []) {
    return request('/voice-api/tts/translate', { method: 'POST', body: new URLSearchParams({ text, target_language: targetLanguage, contacts: JSON.stringify(contacts) }) });
  },
  synthesize(text, targetLanguage = 'ko', contacts = []) {
    return request('/voice-api/tts/', {
      method: 'POST',
      body: new URLSearchParams({ text, target_language: targetLanguage, contacts: JSON.stringify(contacts) }),
    });
  },

  transcribe(audio, { signal } = {}) {
    const body = new FormData();
    body.append('audio', audio);
    return request('/voice-api/stt/', { method: 'POST', body, signal });
  },
};
