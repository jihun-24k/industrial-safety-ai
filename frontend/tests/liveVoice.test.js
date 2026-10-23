import test from 'node:test';
import assert from 'node:assert/strict';
import { SilenceDetector, PcmEncoder } from '../src/utils/speechAudio.js';
import { createLiveVoiceInput } from '../src/utils/liveVoiceInput.js';

test('silence requires actual speech, waits 3000ms and only fires once', () => {
  const detector=new SilenceDetector();
  assert.equal(detector.update(0,10000),false);
  for (const time of [11000,11100,11200]) detector.update(.1,time);
  assert.equal(detector.update(0,14199),false);
  assert.equal(detector.update(0,14200),true);
  assert.equal(detector.update(0,20000),false);
});

test('speech resuming during a pause resets silence; a short click is not speech', () => {
  const detector=new SilenceDetector();
  detector.update(.1,0);detector.update(0,100);
  assert.equal(detector.update(0,5000),false);
  for (const time of [5100,5200,5300]) detector.update(.1,time);
  detector.update(0,6000);detector.update(.1,7900);
  assert.equal(detector.update(0,10000),false);
  assert.equal(detector.update(0,10900),true);
});

test('44.1 and 48kHz blocks produce 16kHz PCM without losing packet boundaries', () => {
  for (const rate of [44100,48000]) {
    const encoder=new PcmEncoder(rate);
    const input=new Float32Array(rate).fill(.5);
    const packets=[];
    for (let i=0;i<input.length;i+=128) packets.push(...encoder.encode(input.slice(i,i+128)));
    const tail=encoder.flush();if(tail)packets.push(tail);
    assert.equal(packets.reduce((n,p)=>n+p.pcm.byteLength,0),32000);
    assert.ok(packets.every(p=>new DataView(p.pcm).getInt16(0,true)===16384));
    assert.ok(packets.every(p=>Math.abs(p.rms-.5)<.0001));
  }
});

test('audio worklet emits PCM and flushes the final tail without speaker output', async () => {
  const saved={Processor:globalThis.AudioWorkletProcessor,rate:globalThis.sampleRate,register:globalThis.registerProcessor};
  let Processor;
  const packets=[];
  try {
    globalThis.sampleRate=48000;
    globalThis.AudioWorkletProcessor=class {constructor(){this.port={postMessage:packet=>packets.push(packet)};}};
    globalThis.registerProcessor=(name,processor)=>{assert.equal(name,'safety-pcm');Processor=processor;};
    await import('../src/utils/pcmWorklet.js');
    const processor=new Processor();
    const output=new Float32Array(128);
    assert.equal(processor.process([[new Float32Array(128).fill(.5)]],[[output]]),true);
    processor.port.onmessage({data:'flush'});
    assert.ok(packets[0].pcm.byteLength>0);
    assert.deepEqual(packets.at(-1),{flushed:true});
    assert.ok(output.every(value=>value===0));
  } finally {
    globalThis.AudioWorkletProcessor=saved.Processor;globalThis.sampleRate=saved.rate;globalThis.registerProcessor=saved.register;
  }
});

const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness(options={}) {
  let frame, clock=0, closes=0, socketClosed=false;
  const states=[],partials=[],finals=[],errors=[],sent=[];
  const socket={bufferedAmount:0,
    send:data=>sent.push(data),close:()=>{socketClosed=true;}};
  const audio={close:()=>closes++,flush:async()=>{}};
  const input=createLiveVoiceInput({
    openSocket:()=>socket,capture:async callback=>{frame=callback;return audio;},now:()=>clock,
    onState:s=>states.push(s),onPartial:text=>partials.push(text),onFinal:(text,meta)=>finals.push({text,...meta}),
    onError:e=>errors.push(e),...options,
  });
  const message=data=>socket.onmessage?.({data:JSON.stringify(data)});
  async function start() {
    const pending=input.start();socket.onopen();message({type:'ready'});await pending;
  }
  function feed(time,rms) {clock=time;frame({pcm:new ArrayBuffer(3200),rms});}
  return {input,start,feed,message,socket,states,partials,finals,errors,sent,
    get closes(){return closes;},get socketClosed(){return socketClosed;}};
}

test('partial hypotheses revise text; silence finishes and submits only the final text once', async () => {
  const h=harness();
  try {
    await h.start();
    h.message({type:'partial',text:'안전'});h.message({type:'partial',text:'안전 점검'});
    assert.deepEqual(h.partials,['안전','안전 점검']);assert.deepEqual(h.finals,[]);
    h.feed(0,.1);h.feed(100,.1);h.feed(200,.1);h.feed(3199,0);
    assert.equal(h.states.at(-1),'recording');
    h.feed(3200,0);await flush();
    assert.equal(h.states.at(-1),'transcribing');
    assert.equal(h.sent.filter(x=>x==='{"type":"finish"}').length,1);
    h.message({type:'final',text:'안전 점검을 알려줘'});await flush();
    h.message({type:'final',text:'중복'});await flush();
    assert.deepEqual(h.finals,[{text:'안전 점검을 알려줘',autoSend:true}]);
    assert.equal(h.states.at(-1),'idle');assert.equal(h.closes,1);
  } finally {h.input.cancel();}
});

test('manual stop never auto-submits, and empty final text never searches', async () => {
  for (const text of ['직접 입력','']) {
    const h=harness();
    try {
      await h.start();await h.input.stop();h.message({type:'final',text});await flush();
      if(text)assert.deepEqual(h.finals,[{text,autoSend:false}]);
      else {assert.deepEqual(h.finals,[]);assert.equal(h.errors.length,1);}
    } finally {h.input.cancel();}
  }
});

test('cancellation prevents late recognition from triggering a query and releases microphone', async () => {
  const h=harness();await h.start();
  const late=h.socket.onmessage;
  h.input.cancel();late({data:JSON.stringify({type:'final',text:'늦은 답'})});await flush();
  assert.deepEqual(h.finals,[]);assert.equal(h.closes,1);assert.equal(h.socketClosed,true);
});

test('login rejection exits connecting state without opening microphone', async () => {
  let captureCount=0;
  const h=harness({capture:async()=>{captureCount++;}});
  const pending=h.input.start();h.socket.onclose({code:4401});await pending;
  assert.equal(captureCount,0);assert.match(h.errors[0],/로그인이 만료/);
  assert.equal(h.states.at(-1),'idle');
});
