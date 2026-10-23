// Browser capture and STT lifecycle are kept outside the Vue component so that
// permission cancellation and microphone cleanup can be tested without a device.
export function createVoiceRecorder({ transcribe, onText, onError, onState,
  mediaDevices = globalThis.navigator?.mediaDevices, Recorder = globalThis.MediaRecorder,
  maxDurationMs = 60000 }) {
  let state = 'idle';
  let generation = 0;
  let recorder;
  let stream;
  let timer;
  let controller;
  const setState = value => { state = value; onState(value); };
  const release = () => { clearTimeout(timer); stream?.getTracks().forEach(track => track.stop()); stream = null; };
  const report = message => { release(); setState('idle'); onError(message); };

  async function start() {
    if (state !== 'idle') return;
    if (!mediaDevices?.getUserMedia || !Recorder) {
      onError('음성 입력을 지원하지 않는 환경입니다. HTTPS 또는 localhost의 Chrome·Edge에서 이용해 주세요.'); return;
    }
    const mimeType = ['audio/webm;codecs=opus', 'audio/webm'].find(type => Recorder.isTypeSupported(type));
    if (!mimeType) { onError('WebM 녹음을 지원하지 않는 브라우저입니다. Chrome·Edge를 이용해 주세요.'); return; }
    const run = ++generation;
    setState('requesting');
    try {
      const captured = await mediaDevices.getUserMedia({ audio: true });
      if (run !== generation) { captured.getTracks().forEach(track => track.stop()); return; }
      stream = captured;
      recorder = new Recorder(stream, { mimeType });
      const chunks = [];
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => {
        if (run !== generation) return;
        generation++;
        if (recorder.state !== 'inactive') recorder.stop();
        report('녹음 중 오류가 발생했습니다. 마이크 연결을 확인해 주세요.');
      };
      recorder.onstop = async () => {
        if (run !== generation) return;
        release();
        const blob = new Blob(chunks, { type: mimeType });
        if (!blob.size) { report('녹음된 음성이 없습니다. 다시 녹음해 주세요.'); return; }
        setState('transcribing');
        controller = new AbortController();
        timer = setTimeout(() => controller.abort(), 90000);
        try {
          const audio = new File([blob], `question-${crypto.randomUUID()}.webm`, { type: mimeType });
          const data = await transcribe(audio, { signal: controller.signal });
          if (run !== generation) return;
          if (data.error) throw new Error('음성을 인식하지 못했습니다. 잠시 후 다시 시도해 주세요.');
          const text = typeof data.text === 'string' ? data.text.trim() : '';
          if (!text) throw new Error('인식된 말이 없습니다. 마이크 가까이에서 다시 말해 주세요.');
          onText(text);
        } catch (error) {
          if (run === generation) onError(error.name === 'AbortError' ? '음성 인식 대기 시간이 초과되었습니다.' : error.message);
        } finally {
          if (run === generation) { clearTimeout(timer); controller = null; setState('idle'); }
        }
      };
      recorder.start();
      setState('recording');
      timer = setTimeout(stop, maxDurationMs);
    } catch (error) {
      if (run !== generation) return;
      report(({NotAllowedError:'마이크 권한이 거부되었습니다. 브라우저 사이트 설정에서 마이크를 허용해 주세요.',
        NotFoundError:'사용할 수 있는 마이크가 없습니다.', NotReadableError:'마이크를 사용할 수 없습니다. 다른 앱에서 사용 중인지 확인해 주세요.'})[error.name] || '녹음을 시작하지 못했습니다. 마이크 설정을 확인해 주세요.');
    }
  }

  function stop() {
    if (state !== 'recording') return;
    clearTimeout(timer);
    // Disable repeated stop clicks while the last audio chunk is being delivered.
    setState('transcribing');
    recorder.stop();
    release();
  }

  function cancel() {
    generation++;
    controller?.abort();
    controller = null;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    release();
    setState('idle');
  }

  return { start, stop, cancel };
}
