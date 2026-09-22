import queue
import logging
import numpy as np

logger = logging.getLogger("audiobot.desktop_pipe")

class AudioPipeManager:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, chunk_size: int = 512):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        
        self.input_stream = None
        self.output_stream = None
        self.is_capturing = False
        self.sd_available = False

        try:
            import sounddevice as sd
            self.sd = sd
            self.sd_available = True
            logger.info("SoundDevice library initialized for desktop audio hardware capture.")
        except Exception as e:
            logger.warning(f"SoundDevice not loaded ({e}). Virtual/mock audio hardware pipe active.")

    def start_capture(self, callback_func):
        if not self.sd_available:
            self.is_capturing = True
            return

        def in_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Audio input status: {status}")
            # Convert float32 [-1, 1] to 16-bit PCM bytes
            audio_int16 = (indata * 32767).astype(np.int16)
            pcm_bytes = audio_int16.tobytes()
            callback_func(pcm_bytes)

        try:
            self.input_stream = self.sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='float32',
                blocksize=self.chunk_size,
                callback=in_callback
            )
            self.input_stream.start()
            self.is_capturing = True
            logger.info("Hardware microphone stream started.")
        except Exception as e:
            logger.error(f"Failed to start input stream: {e}")

    def stop_capture(self):
        if self.input_stream:
            try:
                self.input_stream.stop()
                self.input_stream.close()
            except Exception:
                pass
            self.input_stream = None
        self.is_capturing = False
        logger.info("Microphone capture stopped.")

    def play_chunk(self, audio_bytes: bytes):
        if not self.sd_available:
            return

        try:
            # Check if bytes are raw 16-bit PCM
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float = audio_int16.astype(np.float32) / 32768.0
            self.sd.play(audio_float, samplerate=self.sample_rate)
        except Exception as e:
            logger.error(f"Desktop playback exception: {e}")

    def flush_output(self):
        if self.sd_available:
            try:
                self.sd.stop()
            except Exception:
                pass
