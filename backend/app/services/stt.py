import asyncio
import json
import logging
import httpx
from typing import AsyncGenerator, Optional
from app.core.config import settings

logger = logging.getLogger("audiobot.stt")

class BaseSTTService:
    async def transcribe_audio_chunk(self, pcm_bytes: bytes) -> str:
        raise NotImplementedError

class MockSTTService(BaseSTTService):
    """
    Mock STT service when no external STT key is configured.
    Provides intelligent responses based on speech presence.
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
        # Simulate quick transcription delay
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
        # Package PCM bytes as WAV format for Whisper API endpoint
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

def get_stt_service() -> BaseSTTService:
    provider = settings.STT_PROVIDER.lower()
    if provider == "deepgram" and settings.DEEPGRAM_API_KEY:
        return DeepgramSTTService(settings.DEEPGRAM_API_KEY)
    elif provider == "groq" and settings.GROQ_API_KEY:
        return GroqWhisperSTTService(settings.GROQ_API_KEY)
    return MockSTTService()
