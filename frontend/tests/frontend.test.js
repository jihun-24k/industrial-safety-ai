import test from 'node:test';
import assert from 'node:assert/strict';
import { authApi } from '../src/api/authApi.js';
import { ragApi } from '../src/api/ragApi.js';
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
