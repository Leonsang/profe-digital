// Cola de reproducción PCM16 a 24 kHz. 'flush' la vacía al instante (interrupción).
class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(24000 * 120);
    this.read = 0;
    this.write = 0;
    this.speaking = false;
    this.port.onmessage = (event) => {
      const data = event.data;
      if (data === 'flush') {
        this.read = this.write = 0;
        return;
      }
      const pcm = new Int16Array(data);
      for (let i = 0; i < pcm.length; i++) {
        this.buffer[this.write] = pcm[i] / 0x8000;
        this.write = (this.write + 1) % this.buffer.length;
      }
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    let level = 0;
    for (let i = 0; i < out.length; i++) {
      if (this.read === this.write) {
        out[i] = 0;
      } else {
        out[i] = this.buffer[this.read];
        level = Math.max(level, Math.abs(out[i]));
        this.read = (this.read + 1) % this.buffer.length;
      }
    }
    const speaking = this.read !== this.write;
    if (speaking !== this.speaking || (speaking && currentFrame % 2400 < 128)) {
      this.speaking = speaking;
      this.port.postMessage({ speaking, level });
    }
    return true;
  }
}

registerProcessor('playback-processor', PlaybackProcessor);
