import { PcmEncoder } from './speechAudio.js';

class PcmWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this.encoder = new PcmEncoder(sampleRate);
    this.port.onmessage = event => {
      if (event.data === 'flush') {
        const packet = this.encoder.flush();
        if (packet) this.port.postMessage(packet, [packet.pcm]);
        this.port.postMessage({flushed:true});
      }
    };
  }
  process(inputs) {
    const samples = inputs[0]?.[0];
    if (samples) for (const packet of this.encoder.encode(samples)) this.port.postMessage(packet, [packet.pcm]);
    // Leave outputs silent: never play the microphone back through the speakers.
    return true;
  }
}
registerProcessor('safety-pcm', PcmWorklet);
