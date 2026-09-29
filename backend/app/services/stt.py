import asyncio
import json
import logging
import httpx
import numpy as np
from typing import AsyncGenerator, Optional
from app.core.config import settings

logger = logging.getLogger("audiobot.stt")

class BaseSTTService:
    async def transcribe_audio_chunk(self, pcm_bytes: bytes) -> str:
        raise NotImplementedError

class FasterWhisperSTTService(BaseSTTService):
    """
    Local speech recognition using faster-whisper on CPU.
    Accepts 16kHz mono 16-bit PCM bytes from VAD segments.
    """
    def __init__(self, model_size: str = "tiny.en"):
        self.model_size = model_size
        self.model = None
        self._init_error = None
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Initializing local faster-whisper model '{self.model_size}' (CPU int8)...")
            self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            logger.info(f"faster-whisper model '{self.model_size}' initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to load faster-whisper model '{self.model_size}': {e}")
            self._init_error = str(e)

    async def transcribe_audio_chunk(self, pcm_bytes: bytes) -> str:
        if not pcm_bytes or len(pcm_bytes) < 1000:
            return ""

        if self.model is None:
            logger.error(f"FasterWhisper model unavailable ({self._init_error}).")
            return ""

        def _run_transcribe():
            try:
                # Convert 16-bit PCM to normalized float32 numpy array [-1.0, 1.0]
                audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
                if len(audio_int16) == 0:
                    return ""
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                segments, _ = self.model.transcribe(
                    audio_float32,
                    beam_size=1,
                    language="en",
                    vad_filter=False
                )
                text = " ".join(seg.text for seg in segments).strip()
                return text
            except Exception as e:
                logger.error(f"FasterWhisper transcription error: {e}")
                return ""

        return await asyncio.to_thread(_run_transcribe)

class MockSTTService(BaseSTTService):
    """
    Mock STT service when demo mode is active or fallback required.
    """
    def __init__(self):
        self.sample_queries = [
            "Hello ambient audio bot, what is your current system status?",
            "Can you synchronize session context with my mobile device?",
            "Tell me a short joke about artificial intelligence.",
            "What devices are currently connected to the network?",
            "Perform audio session handoff to desktop daemon."
        ]
        self.query_idx = 0

    async def transcribe_audio_chunk(self, pcm_bytes: bytes) -> str:
        await asyncio.sleep(0.1)
        if len(pcm_bytes) < 1000:
            return ""
        text = self.sample_queries[self.query_idx % len(self.sample_queries)]
        self.query_idx += 1
        return text

class DeepgramSTTService(BaseSTTService):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_formatting=true&encoding=linear16&sample_rate=16000&channels=1"

    async def transcribe_audio_chunk(self, pcm_bytes: bytes) -> str:
        if not self.api_key:
            logger.warning("Deepgram API key missing, falling back to empty transcription.")
            return ""

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/raw; encoding=linear16; rate=16000; channels=1"
        }
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(self.api_url, content=pcm_bytes, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    transcript = data['results']['channels'][0]['alternatives'][0]['transcript']
                    return transcript.strip()
                else:
                    logger.error(f"Deepgram STT API Error {resp.status_code}: {resp.text}")
                    return ""
            except Exception as e:
                logger.error(f"Deepgram STT Request exception: {e}")
                return ""

class GroqWhisperSTTService(BaseSTTService):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe_audio_chunk(self, pcm_bytes: bytes) -> str:
        if not self.api_key:
            return ""

        headers = {"Authorization": f"Bearer {self.api_key}"}
        import io, wave
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(pcm_bytes)
        wav_data = wav_buffer.getvalue()

        files = {"file": ("audio.wav", wav_data, "audio/wav")}
        data = {"model": "whisper-large-v3", "language": "en"}

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(self.api_url, headers=headers, files=files, data=data, timeout=8.0)
                if resp.status_code == 200:
                    res_json = resp.json()
                    return res_json.get("text", "").strip()
                else:
                    logger.error(f"Groq Whisper API Error {resp.status_code}: {resp.text}")
                    return ""
            except Exception as e:
                logger.error(f"Groq Whisper Exception: {e}")
                return ""

_faster_whisper_instance = None

def get_stt_service() -> BaseSTTService:
    global _faster_whisper_instance
    if settings.DEMO_MODE:
        return MockSTTService()

    provider = settings.STT_PROVIDER.lower()
    if provider in ["faster_whisper", "faster-whisper", "whisper"]:
        if _faster_whisper_instance is None:
            _faster_whisper_instance = FasterWhisperSTTService(settings.STT_MODEL)
        return _faster_whisper_instance
    elif provider == "deepgram" and settings.DEEPGRAM_API_KEY:
        return DeepgramSTTService(settings.DEEPGRAM_API_KEY)
    elif provider == "groq" and settings.GROQ_API_KEY:
        return GroqWhisperSTTService(settings.GROQ_API_KEY)
    elif provider == "mock":
        return MockSTTService()

    # Fallback to faster_whisper if installed, otherwise MockSTTService
    if _faster_whisper_instance is None:
        try:
            _faster_whisper_instance = FasterWhisperSTTService(settings.STT_MODEL)
            if _faster_whisper_instance.model is not None:
                return _faster_whisper_instance
        except Exception:
            pass
    return MockSTTService()
