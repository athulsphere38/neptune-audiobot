import asyncio
import logging
import httpx
import json
from typing import AsyncGenerator
import edge_tts
from app.core.config import settings

logger = logging.getLogger("audiobot.tts")

class BaseTTSService:
    async def stream_tts(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError

class EdgeTTSService(BaseTTSService):
    """
    Zero-cost high quality streaming TTS provider using edge-tts.
    Buffers incoming text tokens into short clauses and streams MP3 audio chunks.
    """
    def __init__(self, voice: str = "en-US-AvaNeural"):
        self.voice = voice

    async def stream_tts(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        sentence_buffer = ""

        async for token in text_stream:
            sentence_buffer += token
            # Yield TTS chunk as soon as punctuation boundary or length is reached
            if any(p in token for p in [".", "!", "?", "\n", ";", ","]) and len(sentence_buffer.strip()) > 15:
                clause = sentence_buffer.strip()
                sentence_buffer = ""
                async for audio_chunk in self._synthesize_clause(clause):
                    yield audio_chunk

        if sentence_buffer.strip():
            async for audio_chunk in self._synthesize_clause(sentence_buffer.strip()):
                yield audio_chunk

    async def _synthesize_clause(self, text: str) -> AsyncGenerator[bytes, None]:
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as e:
            logger.error(f"EdgeTTS synthesis exception: {e}")

class CartesiaTTSService(BaseTTSService):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def stream_tts(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        if not self.api_key:
            logger.warning("Cartesia API key missing, falling back to Edge-TTS.")
            async for chunk in EdgeTTSService().stream_tts(text_stream):
                yield chunk
            return

        url = "https://api.cartesia.ai/tts/bytes"
        headers = {
            "X-API-Key": self.api_key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json"
        }

        sentence_buffer = ""
        async for token in text_stream:
            sentence_buffer += token
            if any(p in token for p in [".", "!", "?", "\n"]) and len(sentence_buffer.strip()) > 10:
                clause = sentence_buffer.strip()
                sentence_buffer = ""
                payload = {
                    "model_id": "sonic-english",
                    "transcript": clause,
                    "voice": {"mode": "id", "id": "a0e88bae-5940-4160-a3d6-ea0e6d707a01"},
                    "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 16000}
                }
                async with httpx.AsyncClient() as client:
                    try:
                        async with client.stream("POST", url, headers=headers, json=payload, timeout=10.0) as resp:
                            if resp.status_code == 200:
                                async for chunk in resp.aiter_bytes():
                                    yield chunk
                            else:
                                logger.error(f"Cartesia error {resp.status_code}")
                    except Exception as e:
                        logger.error(f"Cartesia TTS Exception: {e}")

class ElevenLabsTTSService(BaseTTSService):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def stream_tts(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        if not self.api_key:
            async for chunk in EdgeTTSService().stream_tts(text_stream):
                yield chunk
            return

        voice_id = "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        sentence_buffer = ""
        async for token in text_stream:
            sentence_buffer += token
            if any(p in token for p in [".", "!", "?", "\n"]) and len(sentence_buffer.strip()) > 10:
                clause = sentence_buffer.strip()
                sentence_buffer = ""
                payload = {
                    "text": clause,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                }
                async with httpx.AsyncClient() as client:
                    try:
                        async with client.stream("POST", url, headers=headers, json=payload, timeout=10.0) as resp:
                            if resp.status_code == 200:
                                async for chunk in resp.aiter_bytes():
                                    yield chunk
                    except Exception as e:
                        logger.error(f"ElevenLabs TTS Exception: {e}")

def get_tts_service() -> BaseTTSService:
    provider = settings.TTS_PROVIDER.lower()
    if provider == "cartesia" and settings.CARTESIA_API_KEY:
        return CartesiaTTSService(settings.CARTESIA_API_KEY)
    elif provider == "elevenlabs" and settings.ELEVENLABS_API_KEY:
        return ElevenLabsTTSService(settings.ELEVENLABS_API_KEY)
    return EdgeTTSService(voice=settings.TTS_VOICE)
