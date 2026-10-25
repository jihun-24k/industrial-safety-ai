import test from 'node:test';
import assert from 'node:assert/strict';
import { authApi } from '../src/api/authApi.js';
import { mapStoredMessage, ragApi } from '../src/api/ragApi.js';
import { voiceApi } from '../src/api/voiceApi.js';
import { createVoiceRecorder } from '../src/utils/voiceRecorder.js';

test('signup accepts existing HTML redirect response and explains duplicate IDs', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/auth-api/signup');
      assert.equal(options.method, 'POST');
      assert.equal(options.credentials, 'include');
      assert.equal(options.body.get('username'), 'test-user');
      assert.equal(options.body.get('password'), 'test-password');
      return new Response('<html>Login</html>', {headers:{'Content-Type':'text/html'}});
    };
    await authApi.signup('test-user', 'test-password');
    globalThis.fetch = async () => new Response('username already exists', {status:400});
    await assert.rejects(authApi.signup('test-user', 'test-password'), /이미 사용 중/);
  } finally { globalThis.fetch = original; }
});

test('questions always use the existing document source even if a caller passes web', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/rag-api/rag-query');
      assert.deepEqual(JSON.parse(options.body), {prompt:'질문',source:'pdf',top_k:5});
      return Response.json({answer:'답변'});
    };
    const result = await ragApi.query({prompt:'질문',source:'web'});
    assert.equal(result.answer, '답변');
  } finally { globalThis.fetch = original; }
});

test('conversation APIs restore the newest list and map stored message metadata', async () => {
  const original = globalThis.fetch;
  try {
    const requests = [];
    globalThis.fetch = async (url, options) => {
      requests.push([url, options]);
      if (url === '/rag-api/conversations') {
        return Response.json([
          {id:'newest',title:'최신 대화',created_at:'2026-10-25T10:00:00',updated_at:'2026-10-25T11:00:00'},
          {id:'older',title:'이전 대화',created_at:'2026-10-24T10:00:00',updated_at:'2026-10-24T11:00:00'},
        ]);
      }
      assert.equal(url, '/rag-api/conversations/newest/messages');
      return Response.json({
        conversation:{id:'newest',title:'최신 대화',created_at:'2026-10-25T10:00:00',updated_at:'2026-10-25T11:00:00'},
        messages:[
          {id:1,role:'user',text:'질문',sources:[],needs_review:false,handoff:false,clarifying_questions:[]},
          {id:2,role:'assistant',text:'답변',sources:['매뉴얼 p.1'],needs_review:true,handoff:false,clarifying_questions:['현장은?']},
        ],
      });
    };
    const conversations = await ragApi.listConversations();
    assert.deepEqual(conversations.map(chat => chat.id), ['newest','older']);
    assert.deepEqual(conversations[0].messages, []);
    const restored = await ragApi.getConversationMessages('newest');
    assert.equal(restored.messages[1].needsReview, true);
    assert.deepEqual(restored.messages[1].clarifyingQuestions, ['현장은?']);
    assert.equal(restored.messages[1].source, '출처: 매뉴얼 p.1');
    assert.equal(requests[0][1].credentials, 'include');
    assert.equal(requests[1][1].credentials, 'include');
  } finally { globalThis.fetch = original; }
});

test('stored handoff messages keep the safety review presentation', () => {
  const message = mapStoredMessage({
    id:3,role:'assistant',text:'확인 필요',sources:[],needs_review:false,handoff:true,clarifying_questions:null,
  });
  assert.equal(message.handoff, true);
  assert.equal(message.source, '근거 없음 · 안전관리자 확인 필요');
  assert.deepEqual(message.clarifyingQuestions, []);
});

test('JSON questions include the active conversation ID', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (_url, options) => {
      assert.deepEqual(JSON.parse(options.body), {
        prompt:'후속 질문',source:'pdf',top_k:5,conversation_id:'conversation-1',
      });
      return Response.json({answer:'답변',conversation_id:'conversation-1',title:'제목'});
    };
    await ragApi.query({prompt:'후속 질문',conversationId:'conversation-1'});
  } finally { globalThis.fetch = original; }
});

function streamingResponse(parts) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      for (const part of parts) controller.enqueue(encoder.encode(part));
      controller.close();
    },
  }), {headers:{'Content-Type':'text/event-stream'}});
}

test('streaming questions append tokens in order and return final sources', async () => {
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async (url,options)=>{
      assert.equal(url,'/rag-api/rag-query/stream');
      assert.equal(options.method,'POST');
      assert.equal(options.credentials,'include');
      assert.deepEqual(JSON.parse(options.body),{prompt:'질문',source:'pdf',top_k:5,conversation_id:'conversation-1'});
      return streamingResponse([
        'event: status\ndata: {"phase":"retrieving","message":"검색 중"}\n\nevent: token\nda',
        'ta: {"text":"안전"}\n\nevent: token\ndata: {"text":" 수칙"}\n\n',
        'event: done\ndata: {"answer":"안전 수칙","sources":["매뉴얼 p.1"],"handoff":false}\n\n',
      ]);
    };
    const statuses=[],tokens=[];
    const result=await ragApi.queryStream({prompt:'질문',conversationId:'conversation-1'},{
      onStatus:data=>statuses.push(data.message),onToken:text=>tokens.push(text),
    });
    assert.deepEqual(statuses,['검색 중']);
    assert.deepEqual(tokens,['안전',' 수칙']);
    assert.equal(result.answer,'안전 수칙');
    assert.deepEqual(result.sources,['매뉴얼 p.1']);
  } finally {globalThis.fetch=original;}
});

test('streaming API error events reject instead of accepting a partial answer', async () => {
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>streamingResponse([
      'event: token\ndata: {"text":"부분 답변"}\n\n',
      'event: error\ndata: {"message":"모델 오류"}\n\n',
    ]);
    await assert.rejects(ragApi.queryStream({prompt:'질문'}),/모델 오류/);
  } finally {globalThis.fetch=original;}
});

test('streaming HTTP validation errors expose the rejected field', async () => {
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>Response.json({detail:[
      {loc:['body','prompt'],msg:'String should have at least 2 characters'},
    ]},{status:422});
    await assert.rejects(ragApi.queryStream({prompt:'x'}),/prompt: String should have at least 2 characters/);
  } finally {globalThis.fetch=original;}
});

class Recorder {
  static isTypeSupported(type) { return type.startsWith('audio/webm'); }
  constructor(_stream, options) { this.mimeType=options.mimeType;this.state='inactive'; }
  start() { this.state='recording'; }
  stop() {
    this.state='inactive';
    queueMicrotask(() => {
      this.ondataavailable({data:new Blob(['recorded-audio'],{type:this.mimeType})});
      this.onstop();
    });
  }
}

function harness(options={}) {
  const states=[],texts=[],errors=[];
  let stops=0;
  const stream={getTracks:()=>[{stop:()=>stops++}]};
  const recorder=createVoiceRecorder({Recorder,mediaDevices:{getUserMedia:async()=>stream},
    transcribe:async()=>({text:'인식한 질문'}),onText:text=>texts.push(text),
    onError:message=>errors.push(message),onState:state=>states.push(state),...options});
  return {recorder,states,texts,errors,stream,get stops(){return stops;}};
}

async function flush() { await new Promise(resolve=>setImmediate(resolve)); }

test('recording stops tracks, posts a unique WebM audio field, and fills text only after stop', async () => {
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async (url, options)=>{
      assert.equal(url,'/voice-api/stt/');
      const audio=options.body.get('audio');
      assert.match(audio.name,/^question-.+\.webm$/);
      assert.match(audio.type,/audio\/webm/);
      assert.equal(options.signal.aborted,false);
      return Response.json({text:'  작업 전 점검을 알려줘  '});
    };
    const h=harness({transcribe:voiceApi.transcribe});
    await h.recorder.start();
    assert.equal(h.states.at(-1),'recording');assert.deepEqual(h.texts,[]);
    h.recorder.stop();await flush();
    assert.deepEqual(h.texts,['작업 전 점검을 알려줘']);assert.equal(h.states.at(-1),'idle');assert.equal(h.stops,1);
  } finally {globalThis.fetch=original;}
});

test('permission denial leaves no pending recorder and explains microphone access', async () => {
  const h=harness({mediaDevices:{getUserMedia:async()=>{throw Object.assign(new Error(),{name:'NotAllowedError'});}}});
  await h.recorder.start();
  assert.equal(h.states.at(-1),'idle');assert.match(h.errors[0],/권한이 거부/);assert.deepEqual(h.texts,[]);
});

test('late microphone permission after leaving the page releases tracks without uploading', async () => {
  let resolvePermission;
  const h=harness({mediaDevices:{getUserMedia:()=>new Promise(resolve=>{resolvePermission=resolve;})}});
  const pending=h.recorder.start();h.recorder.cancel();resolvePermission(h.stream);await pending;
  assert.equal(h.stops,1);assert.equal(h.states.at(-1),'idle');assert.deepEqual(h.texts,[]);
});

test('STT failures return to idle and never replace the input with an empty result', async () => {
  for (const result of [{error:'provider error'},{text:'   '}]) {
    const h=harness({transcribe:async()=>result});
    await h.recorder.start();h.recorder.stop();await flush();
    assert.equal(h.states.at(-1),'idle');assert.equal(h.errors.length,1);assert.deepEqual(h.texts,[]);assert.equal(h.stops,1);
  }
});

test('leaving during transcription aborts the request and ignores late text', async () => {
  let resolveTranscript,signal;
  const h=harness({transcribe:(_file,options)=>{signal=options.signal;return new Promise(resolve=>{resolveTranscript=resolve;});}});
  await h.recorder.start();h.recorder.stop();await flush();
  h.recorder.cancel();assert.equal(signal.aborted,true);
  resolveTranscript({text:'늦은 결과'});await flush();assert.deepEqual(h.texts,[]);
});

test('unsupported recording formats never ask for microphone permission', async () => {
  const h=harness({Recorder:class {static isTypeSupported(){return false;}}});
  await h.recorder.start();assert.match(h.errors[0],/WebM/);assert.equal(h.states.length,0);
});
