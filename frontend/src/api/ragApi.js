import { request } from './client.js';

export function mapStoredMessage(message) {
  const sources = Array.isArray(message.sources) ? message.sources : [];
  const handoff = message.handoff === true;
  return {
    id: message.id,
    role: message.role,
    text: message.text,
    normalizedText: message.normalized_text || '',
    sourceLanguage: message.source_language || 'und',
    sources,
    needsReview: message.needs_review === true,
    handoff,
    clarifyingQuestions: Array.isArray(message.clarifying_questions) ? message.clarifying_questions : [],
    logId: Number.isInteger(message.log_id) ? message.log_id : null,
    feedback: message.feedback === 1 || message.feedback === -1 ? message.feedback : null,
    source: handoff ? '근거 없음 · 안전관리자 확인 필요'
      : (sources.length ? `출처: ${sources.join(', ')}` : '문서 자료 기반'),
    createdAt: message.created_at,
  };
}

export function mapStoredConversation(conversation, messages = []) {
  return {
    id: conversation.id,
    title: conversation.title,
    messages: messages.map(mapStoredMessage),
    createdAt: conversation.created_at,
    updatedAt: conversation.updated_at,
  };
}

function queryPayload({ prompt, topK = 5, conversationId }) {
  const payload = { prompt, source: 'pdf', top_k: topK };
  if (conversationId) payload.conversation_id = conversationId;
  return payload;
}

function parseSseEvent(block) {
  let event = 'message';
  const data = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  return { event, data: JSON.parse(data.join('\n')) };
}

export async function consumeEventStream(stream, onEvent) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replace(/\r\n/g, '\n');

    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseSseEvent(block);
      if (parsed) onEvent(parsed);
    }
    if (done) break;
  }

  const parsed = parseSseEvent(buffer.trim());
  if (parsed) onEvent(parsed);
}

async function streamError(response) {
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : await response.text();
  if (response.status === 401) return new Error('로그인이 필요하거나 만료되었습니다. 다시 로그인해 주세요.');
  const detail = typeof data === 'object' ? (data.detail || data.error) : null;
  const message = Array.isArray(detail)
    ? detail.map(item => `${item.loc?.at(-1) || '요청'}: ${item.msg || '잘못된 값'}`).join(', ')
    : detail;
  return new Error(typeof message === 'string'
    ? message
    : `스트리밍 서비스 요청이 실패했습니다 (HTTP ${response.status}).`);
}

export const ragApi = {
  async listConversations() {
    const data = await request('/rag-api/conversations');
    return data.map(conversation => mapStoredConversation(conversation));
  },

  async getConversationMessages(conversationId) {
    const data = await request(`/rag-api/conversations/${encodeURIComponent(conversationId)}/messages`);
    return mapStoredConversation(data.conversation, data.messages);
  },

  query({ prompt, topK = 5, conversationId }, options = {}) {
    return request('/rag-api/rag-query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(queryPayload({ prompt, topK, conversationId })),
      signal: options.signal,
    });
  },

  async queryStream({ prompt, topK = 5, conversationId }, handlers = {}) {
    const timeout = AbortSignal.timeout(120000);
    const signal = handlers.signal ? AbortSignal.any([handlers.signal, timeout]) : timeout;
    const response = await fetch('/rag-api/rag-query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify(queryPayload({ prompt, topK, conversationId })),
      credentials: 'include',
      signal,
    });
    if (!response.ok) throw await streamError(response);
    if (!response.body) throw new Error('스트리밍 응답을 읽을 수 없습니다.');

    let result = null;
    await consumeEventStream(response.body, ({ event, data }) => {
      if (event === 'status') handlers.onStatus?.(data);
      else if (event === 'normalized') handlers.onNormalized?.(data);
      else if (event === 'token') handlers.onToken?.(data.text || '');
      else if (event === 'done') result = data;
      else if (event === 'error') throw new Error(data.message || '답변 생성 중 오류가 발생했습니다.');
    });
    if (!result) throw new Error('답변이 완료되기 전에 연결이 끊어졌습니다.');
    return result;
  },

  uploadPaper(file) {
    const body = new FormData();
    body.append('file', file);
    return request('/rag-api/upload-paper', { method: 'POST', body });
  },

};
