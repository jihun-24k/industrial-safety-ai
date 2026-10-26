import { request } from './client.js';

function jsonRequest(method, body) {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

// 운영 대시보드 · 답변 평가 · 검증 Q&A API (RAG 서버 /ops, /rag-logs)
export const opsApi = {
  metrics(days = 7) {
    return request(`/rag-api/ops/metrics?days=${encodeURIComponent(days)}`);
  },

  listVerified() {
    return request('/rag-api/ops/verified-qa');
  },

  createVerified({ logId, question, answer }) {
    return request('/rag-api/ops/verified-qa', jsonRequest('POST', { log_id: logId, question, answer }));
  },

  retireVerified(id) {
    return request(`/rag-api/ops/verified-qa/${encodeURIComponent(id)}`, { method: 'DELETE' });
  },

  rate(logId, rating, note = '') {
    return request(`/rag-api/rag-logs/${encodeURIComponent(logId)}/feedback`,
      jsonRequest('POST', { rating, note: note || null }));
  },
};
