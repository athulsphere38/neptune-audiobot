/**
 * AudioWorkletProcessor for 16kHz PCM audio capture directly off hardware thread.
 * Downsamples Web Audio API sample rate (e.g. 44.1kHz or 48kHz) to 16kHz 16-bit linear PCM.
 */
class PCM16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
    this.buffer = new Float32Array(0);
    this.port.onmessage = (e) => {
      if (e.data.command === 'RESET') {
        this.buffer = new Float32Array(0);
      }
    };
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) {
      return true;
    }

    const inputChannel = input[0];
    
    // Accumulate input frames
    const newBuffer = new Float32Array(this.buffer.length + inputChannel.length);
    newBuffer.set(this.buffer, 0);
    newBuffer.set(inputChannel, this.buffer.length);
    this.buffer = newBuffer;

    // Resample from current sampleRate to targetSampleRate (16000)
    const ratio = sampleRate / this.targetSampleRate;
    const outputSamplesNeeded = Math.floor(this.buffer.length / ratio);

    if (outputSamplesNeeded >= 512) {
      const pcm16 = new Int16Array(outputSamplesNeeded);
      let inputIndex = 0;
      for (let i = 0; i < outputSamplesNeeded; i++) {
        inputIndex = Math.floor(i * ratio);
        let sample = Math.max(-1, Math.min(1, this.buffer[inputIndex]));
        pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
      }

      // Post raw ArrayBuffer to main thread
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);

      // Retain unconsumed buffer remainder
      const consumedInputSamples = Math.floor(outputSamplesNeeded * ratio);
      this.buffer = this.buffer.slice(consumedInputSamples);
    }

    return true;
  }
}

registerProcessor('audio-processor', PCM16Processor);
