import { SilenceDetector } from './speechAudio.js';

export function createLiveVoiceInput({ openSocket, capture, onPartial, onFinal, onState, onError,
  now = () => performance.now(), silenceMs = 3000, maxDurationMs = 60000 }) {
  let state = 'idle', generation = 0, session = null;
  const setState = value => {state=value;onState(value);};
  function cleanup() {
    generation++;
    if (session) {
      for (const timer of session.timers) clearTimeout(timer);
      session.rejectReady?.(new Error('음성 입력 취소'));
      session.audio?.close();
      const socket=session.socket;
      socket.onopen=socket.onmessage=socket.onclose=socket.onerror=null;
      socket.close();
      session=null;
    }
    setState('idle');
  }
  function fail(run, message) {
    if (run !== generation) return;
    cleanup();onError(message);
  }
  async function start() {
    if (state !== 'idle') return;
    const run=++generation;
    const detector=new SilenceDetector({silenceMs});
    setState('connecting');
    try {
      const socket=openSocket();
      const active={socket,timers:[],acceptAudio:true,autoSend:false};
      session=active;
      const ready=new Promise((resolve,reject)=>{active.resolveReady=resolve;active.rejectReady=reject;});
      const readyTimer=setTimeout(()=>fail(run,'음성 서버에 연결하지 못했습니다. 서버 실행 상태를 확인해 주세요.'),10000);
      active.timers.push(readyTimer);
      socket.onopen=()=>socket.send(JSON.stringify({type:'start',sample_rate:16000,format:'pcm_s16le'}));
      socket.onclose=event=>fail(run,event.code===4401 ? '로그인이 만료되었습니다. 다시 로그인해 주세요.' : event.code===4403 ? '음성 서버에서 현재 접속 주소를 허용하지 않습니다.' : '실시간 음성 연결이 끊겼습니다. 다시 시도해 주세요.');
      socket.onerror=()=>fail(run,'음성 서버에 연결하지 못했습니다. 연결 상태를 확인해 주세요.');
      socket.onmessage=event=>{
        if (run !== generation) return;
        try {
          const data=JSON.parse(event.data);
          if (data.type==='ready') {clearTimeout(readyTimer);active.resolveReady();active.rejectReady=null;}
          else if (data.type==='partial' && typeof data.text==='string') onPartial(data.text);
          else if (data.type==='error') fail(run,data.message || '음성 인식에 실패했습니다.');
          else if (data.type==='final') {
            if (state!=='transcribing') throw new Error('음성 응답 순서가 올바르지 않습니다.');
            const text=typeof data.text==='string' ? data.text.trim() : '';
            const autoSend=active.autoSend;
            cleanup();
            if (text) Promise.resolve().then(()=>onFinal(text,{autoSend})).catch(error=>onError(error.message));
            else onError('인식된 말이 없습니다. 마이크 가까이에서 다시 말해 주세요.');
          }
        } catch (error) {fail(run,error.message || '음성 응답을 처리하지 못했습니다.');}
      };
      await ready;
      if (run!==generation) return;
      setState('requesting');
      const audio=await capture(packet=>{
        if (run!==generation || !active.acceptAudio) return;
        if (packet.error) {fail(run,packet.error);return;}
        if (socket.bufferedAmount>256*1024) {fail(run,'음성 전송이 지연되고 있습니다. 네트워크를 확인해 주세요.');return;}
        socket.send(packet.pcm);
        if (state==='recording' && detector.update(packet.rms,now())) void stop(true);
      });
      if (run!==generation) {audio.close();return;}
      active.audio=audio;
      setState('recording');
      active.timers.push(setTimeout(()=>stop(false),maxDurationMs));
    } catch (error) {fail(run,error.message || '음성 입력을 시작하지 못했습니다.');}
  }
  async function stop(autoSend=false) {
    if (state!=='recording' || !session) return;
    const run=generation, active=session;
    active.autoSend=autoSend;
    setState('transcribing');
    active.timers.forEach(clearTimeout);
    active.timers.push(setTimeout(()=>fail(run,'음성 인식 대기 시간이 초과되었습니다.'),90000));
    try {
      await Promise.race([active.audio.flush(),new Promise((_,reject)=>{
        active.timers.push(setTimeout(()=>reject(new Error('마이크 입력을 종료하지 못했습니다. 다시 시도해 주세요.')),1500));
      })]);
      if (run!==generation) return;
      active.acceptAudio=false;
      active.audio.close();active.audio=null;
      active.socket.send(JSON.stringify({type:'finish'}));
    } catch (error) {fail(run,error.message);}
  }
  return {start, stop:()=>stop(false), cancel:cleanup};
}
