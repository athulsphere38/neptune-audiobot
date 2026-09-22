/**
 * Low-latency Audio Sink & Streaming Queue Player with Instant Flush on Interruption (Barge-In).
 */
export class StreamingAudioPlayer {
  constructor() {
    this.audioCtx = null;
    this.audioQueue = [];
    this.isPlaying = false;
    this.currentSource = null;
    this.gainNode = null;
  }

  init() {
    if (!this.audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new AudioContext({ sampleRate: 16000 });
      this.gainNode = this.audioCtx.createGain();
      this.gainNode.connect(this.audioCtx.destination);
    }
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
  }

  async playChunk(arrayBuffer) {
    this.init();

    try {
      // Decode audio data (MP3 or PCM container)
      const audioBuffer = await this.audioCtx.decodeAudioData(arrayBuffer.slice(0));
      this.audioQueue.push(audioBuffer);
      if (!this.isPlaying) {
        this.processQueue();
      }
    } catch (err) {
      // Fallback: raw 16kHz PCM decoding
      try {
        const int16Array = new Int16Array(arrayBuffer);
        const float32Array = new Float32Array(int16Array.length);
        for (let i = 0; i < int16Array.length; i++) {
          float32Array[i] = int16Array[i] / 32768.0;
        }

        const audioBuffer = this.audioCtx.createBuffer(1, float32Array.length, 16000);
        audioBuffer.getChannelData(0).set(float32Array);
        this.audioQueue.push(audioBuffer);
        if (!this.isPlaying) {
          this.processQueue();
        }
      } catch (pcmErr) {
        console.error('Audio chunk decode error:', pcmErr);
      }
    }
  }

  processQueue() {
    if (this.audioQueue.length === 0) {
      this.isPlaying = false;
      this.currentSource = null;
      return;
    }

    this.isPlaying = true;
    const buffer = this.audioQueue.shift();
    const source = this.audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.gainNode);

    source.onended = () => {
      this.processQueue();
    };

    this.currentSource = source;
    source.start(0);
  }

  /**
   * Instantly stops current playing audio chunk and purges the playback queue.
   * Call on user barge-in / interruption.
   */
  flush() {
    if (this.currentSource) {
      try {
        this.currentSource.onended = null;
        this.currentSource.stop(0);
        this.currentSource.disconnect();
      } catch (e) {
        // Source already stopped
      }
      this.currentSource = null;
    }
    this.audioQueue = [];
    this.isPlaying = false;
  }
}
