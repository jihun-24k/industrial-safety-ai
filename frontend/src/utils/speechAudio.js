export class SilenceDetector {
  constructor({ silenceMs = 3000, threshold = 0.012, minSpeechMs = 200 } = {}) {
    Object.assign(this, { silenceMs, threshold, minSpeechMs });
    this.speechStart = null;
    this.lastVoice = null;
    this.heardSpeech = false;
    this.fired = false;
  }

  update(rms, now) {
    if (this.fired) return false;
    if (rms >= this.threshold) {
      if (this.speechStart === null) this.speechStart = now;
      if (now - this.speechStart >= this.minSpeechMs) this.heardSpeech = true;
      this.lastVoice = now;
    } else {
      this.speechStart = null;
      if (this.heardSpeech && now - this.lastVoice >= this.silenceMs) {
        this.fired = true;
        return true;
      }
    }
    return false;
  }
}

export class PcmEncoder {
  constructor(sourceRate, packetSize = 1600) {
    if (sourceRate < 16000) throw new Error('지원하지 않는 샘플레이트입니다.');
    this.rate = sourceRate; this.packetSize = packetSize;
    this.phase = 0; this.sum = 0; this.count = 0;
    this.pending = []; this.energy = 0; this.energyCount = 0;
  }
  encode(input) {
    const packets = [];
    for (const sample of input) {
      this.sum += sample; this.count++;
      this.energy += sample * sample; this.energyCount++;
      this.phase += 16000;
      if (this.phase >= this.rate) {
        const value = Math.max(-1, Math.min(1, this.sum / this.count));
        this.pending.push(Math.round(value * (value < 0 ? 32768 : 32767)));
        this.phase -= this.rate; this.sum = 0; this.count = 0;
        if (this.pending.length === this.packetSize) packets.push(this.flush());
      }
    }
    return packets;
  }
  flush() {
    if (!this.pending.length) return null;
    const pcm = new ArrayBuffer(this.pending.length * 2);
    const view = new DataView(pcm);
    this.pending.forEach((value, i) => view.setInt16(i * 2, value, true));
    const packet = {pcm, rms: Math.sqrt(this.energy / Math.max(1, this.energyCount))};
    this.pending = []; this.energy = 0; this.energyCount = 0;
    return packet;
  }
}
