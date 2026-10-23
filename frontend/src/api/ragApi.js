import { request } from './client.js';

export const ragApi = {
  query({ prompt, topK = 5 }) {
    return request('/rag-api/rag-query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, source: 'pdf', top_k: topK }),
    });
  },

  uploadPaper(file) {
    const body = new FormData();
    body.append('file', file);
    return request('/rag-api/upload-paper', { method: 'POST', body });
  },

};
