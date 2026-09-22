import numpy as np
import logging
from typing import Tuple

logger = logging.getLogger("audiobot.vad")

class VoiceActivityDetector:
    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5, silence_ms: int = 700):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.silence_ms = silence_ms
        self.silence_samples_limit = int((silence_ms / 1000.0) * sample_rate)

        self.is_speaking = False
        self.silence_counter = 0
        self.speech_buffer = bytearray()
        
        # Try initializing Silero VAD if torch is available, else fallback to RMS
        self.use_silero = False
        self.silero_model = None
        try:
            import torch
            model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            self.silero_model = model
            self.use_silero = True
            logger.info("Silero VAD initialized successfully.")
        except Exception as e:
            logger.info(f"Silero VAD not loaded ({e}). Utilizing RMS energy VAD engine.")

    def process_pcm_chunk(self, pcm_bytes: bytes) -> Tuple[str, bytes]:
        """
        Processes a raw 16-bit linear PCM chunk (16kHz mono).
        Returns event_type: ('speech_start', 'speech_chunk', 'speech_end', 'silence')
        and the relevant audio bytes.
        """
        if not pcm_bytes:
            return "silence", b""

        # Convert 16-bit int PCM to normalized float array [-1.0, 1.0]
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        if len(audio_int16) == 0:
            return "silence", b""

        audio_float = audio_int16.astype(np.float32) / 32768.0

        is_speech_frame = False
        if self.use_silero and self.silero_model is not None:
            try:
                import torch
                tensor = torch.from_numpy(audio_float)
                speech_prob = self.silero_model(tensor, self.sample_rate).item()
                is_speech_frame = speech_prob >= self.threshold
            except Exception:
                is_speech_frame = self._rms_vad(audio_float)
        else:
            is_speech_frame = self._rms_vad(audio_float)

        event = "silence"
        output_bytes = b""

        if is_speech_frame:
            self.silence_counter = 0
            self.speech_buffer.extend(pcm_bytes)
            if not self.is_speaking:
                self.is_speaking = True
                event = "speech_start"
            else:
                event = "speech_chunk"
            output_bytes = bytes(pcm_bytes)
        else:
            if self.is_speaking:
                self.silence_counter += len(audio_int16)
                self.speech_buffer.extend(pcm_bytes)
                event = "speech_chunk"
                output_bytes = bytes(pcm_bytes)

                if self.silence_counter >= self.silence_samples_limit:
                    self.is_speaking = False
                    event = "speech_end"
                    output_bytes = bytes(self.speech_buffer)
                    self.speech_buffer.clear()
                    self.silence_counter = 0

        return event, output_bytes

    def _rms_vad(self, audio_float: np.ndarray) -> bool:
        rms = np.sqrt(np.mean(audio_float ** 2))
        # RMS threshold for voice detection (~-30dB to -40dB relative)
        return float(rms) > 0.015

    def reset(self):
        self.is_speaking = False
        self.silence_counter = 0
        self.speech_buffer.clear()
