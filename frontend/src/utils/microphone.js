import workletUrl from './pcmWorklet.js?worker&url';

export async function captureMicrophone(onFrame) {
  if (!navigator.mediaDevices?.getUserMedia || !globalThis.AudioContext || !globalThis.AudioWorkletNode) {
    throw new Error('실시간 음성 입력은 HTTPS 또는 localhost의 최신 Chrome·Edge에서 이용해 주세요.');
  }
  let stream, context, source, node, flushDone;
  const close = () => {
    flushDone?.(); flushDone = null;
    node?.disconnect(); source?.disconnect();
    stream?.getTracks().forEach(track => track.stop());
    if (context && context.state !== 'closed') context.close().catch(() => {});
  };
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
    context = new AudioContext();
    await context.audioWorklet.addModule(workletUrl);
    await context.resume();
    source = context.createMediaStreamSource(stream);
    node = new AudioWorkletNode(context, 'safety-pcm', {channelCount:1,channelCountMode:'explicit'});
    node.onprocessorerror = () => onFrame({error:'마이크 오디오 처리에 실패했습니다. 다시 시도해 주세요.'});
    stream.getTracks().forEach(track => track.addEventListener('ended', () => onFrame({error:'마이크 연결이 종료되었습니다.'})));
    node.port.onmessage = event => {
      if (event.data.flushed) { flushDone?.(); flushDone = null; }
      else onFrame(event.data);
    };
    source.connect(node); node.connect(context.destination);
    return {close, flush: () => new Promise(resolve => {flushDone=resolve;node.port.postMessage('flush');})};
  } catch (error) {
    close();
    if (error.name === 'NotAllowedError') throw new Error('마이크 권한이 거부되었습니다. 사이트 설정에서 마이크를 허용해 주세요.');
    if (error.name === 'NotFoundError') throw new Error('연결된 마이크가 없습니다.');
    throw error;
  }
}
