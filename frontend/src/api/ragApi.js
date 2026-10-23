import { request } from './client';

export const ragApi = {
  query({ prompt, source, topK = 5 }) {
    return request('/rag-api/rag-query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, source, top_k: topK }),
    });
  },

  uploadPaper(file) {
    const body = new FormData();
    body.append('file', file);
    return request('/rag-api/upload-paper', { method: 'POST', body });
  },

  collectTopic(topic) {
    const query = new URLSearchParams({ topic });
    return request(`/rag-api/upload-topic?${query}`, { method: 'POST' });
  },
};
