export interface AudioCapture {
  stop: () => void
}

export type CaptureErrorCode = 'NO_MIC_PERMISSION' | 'WORKLET_UNSUPPORTED' | 'CAPTURE_FAILED'

export async function startAudioCapture(onFrame: (frame: ArrayBuffer) => void): Promise<AudioCapture> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('NO_MIC_PERMISSION')
  }

  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
  } catch {
    throw new Error('NO_MIC_PERMISSION')
  }

  const AudioContextClass = window.AudioContext || (window as typeof window & {
    webkitAudioContext?: typeof AudioContext
  }).webkitAudioContext
  if (!AudioContextClass) {
    stream.getTracks().forEach((track) => track.stop())
    throw new Error('CAPTURE_FAILED')
  }

  const audioContext = new AudioContextClass({ sampleRate: 48000 })
  let workletNode: AudioWorkletNode
  try {
    await audioContext.audioWorklet.addModule('/audio-worklet-processor.js')
    workletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor')
  } catch {
    stream.getTracks().forEach((track) => track.stop())
    void audioContext.close()
    throw new Error('WORKLET_UNSUPPORTED')
  }

  workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    onFrame(event.data)
  }
  const source = audioContext.createMediaStreamSource(stream)
  source.connect(workletNode)

  return {
    stop: () => {
      try {
        workletNode.port.onmessage = null
        source.disconnect()
        workletNode.disconnect()
      } catch {
        // 停止时的重复断开不应阻塞语音会话清理。
      }
      stream.getTracks().forEach((track) => track.stop())
      void audioContext.close()
    },
  }
}
