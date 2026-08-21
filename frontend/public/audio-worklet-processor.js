class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.targetRate = 16000
    this.buffer = new Int16Array(0)
    this.ratio = sampleRate / this.targetRate
    this.frameSize = Math.round(this.targetRate * 0.1)
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || input.length === 0 || !input[0]) return true

    const channel = input[0]
    const outputLength = Math.floor(channel.length / this.ratio)
    const downsampled = new Float32Array(outputLength)
    for (let index = 0; index < outputLength; index += 1) {
      const sourceIndex = index * this.ratio
      const lower = Math.floor(sourceIndex)
      const upper = Math.min(lower + 1, channel.length - 1)
      const fraction = sourceIndex - lower
      downsampled[index] = channel[lower] * (1 - fraction) + channel[upper] * fraction
    }

    const pcm = new Int16Array(downsampled.length)
    for (let index = 0; index < downsampled.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, downsampled[index]))
      pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    }

    const merged = new Int16Array(this.buffer.length + pcm.length)
    merged.set(this.buffer)
    merged.set(pcm, this.buffer.length)
    this.buffer = merged

    while (this.buffer.length >= this.frameSize) {
      const frame = this.buffer.slice(0, this.frameSize)
      this.buffer = this.buffer.slice(this.frameSize)
      this.port.postMessage(frame.buffer, [frame.buffer])
    }
    return true
  }
}

registerProcessor('audio-capture-processor', AudioCaptureProcessor)
