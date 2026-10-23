import { request } from './client';

export const voiceApi = {
  synthesize(text) {
    return request('/voice-api/tts/', {
      method: 'POST',
      body: new URLSearchParams({ text }),
    });
  },

  transcribe(audio) {
    const body = new FormData();
    body.append('audio', audio);
    return request('/voice-api/stt/', { method: 'POST', body });
  },
};
