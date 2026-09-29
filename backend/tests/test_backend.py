import os
import sys
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure backend directory is first in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
desktop_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../desktop-client"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
import numpy as np

from main import app
from app.core.vad import VoiceActivityDetector
from app.db.memory import MemoryStore
from app.services.llm import OllamaLLMService, MockLLMService
from app.services.stt import FasterWhisperSTTService, MockSTTService, get_stt_service
from app.services.tts import EdgeTTSService, get_tts_service
from app.core.config import settings

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "sync_engine" in data

def test_list_devices():
    response = client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "devices" in data

@pytest.mark.asyncio
async def test_vad_processor():
    vad = VoiceActivityDetector(sample_rate=16000, threshold=0.5, silence_ms=500)
    
    # Generate 1 second of silence PCM (16-bit 0s)
    silence_pcm = np.zeros(16000, dtype=np.int16).tobytes()
    event, _ = vad.process_pcm_chunk(silence_pcm)
    assert event in ["silence", "speech_end"]

    # Generate 1 second of sine wave audio (speech simulation)
    t = np.linspace(0, 1, 16000, False)
    tone = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)
    tone_pcm = tone.tobytes()

    event, speech_bytes = vad.process_pcm_chunk(tone_pcm)
    assert event in ["speech_start", "speech_chunk"]
    assert len(speech_bytes) > 0

@pytest.mark.asyncio
async def test_memory_store(tmp_path):
    db_file = tmp_path / "test_memory.db"
    mem = MemoryStore(db_path=str(db_file))
    await mem.init_db()

    session_id = "test_sess_123"
    await mem.add_message(session_id, "user", "Hello Audio Agent")
    await mem.add_message(session_id, "assistant", "Hello! How can I assist you?")

    messages = await mem.get_recent_messages(session_id, limit=10)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello Audio Agent"
    assert messages[1]["role"] == "assistant"

@pytest.mark.asyncio
async def test_ollama_llm_service_streaming_mocked():
    ollama_svc = OllamaLLMService(host="http://localhost:11434", model_name="llama3.2")
    
    # Mock httpx response stream for Ollama /api/chat
    mock_lines = [
        b'{"message": {"content": "Hello"}, "done": false}\n',
        b'{"message": {"content": " world!"}, "done": true}\n'
    ]
    
    class MockStream:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        @property
        def status_code(self):
            return 200
        async def aiter_lines(self):
            for l in mock_lines:
                yield l.decode()

    class MockAsyncClient:
        def stream(self, method, url, json=None, timeout=None):
            return MockStream()
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass

    with patch("httpx.AsyncClient", return_value=MockAsyncClient()):
        tokens = []
        async for token in ollama_svc.stream_completion("Hi", []):
            tokens.append(token)
        assert "".join(tokens) == "Hello world!"

@pytest.mark.asyncio
async def test_ollama_llm_service_unavailable():
    ollama_svc = OllamaLLMService(host="http://localhost:9999", model_name="llama3.2")
    # Should yield clear error message when host unavailable
    tokens = []
    async for token in ollama_svc.stream_completion("Test prompt", []):
        tokens.append(token)
    full_resp = "".join(tokens)
    assert "Ollama service unavailable" in full_resp

@pytest.mark.asyncio
async def test_faster_whisper_stt_service():
    stt = FasterWhisperSTTService(model_size="tiny.en")
    # Empty audio should return empty string
    res = await stt.transcribe_audio_chunk(b"")
    assert res == ""

    # Short silence PCM
    silence_pcm = np.zeros(3200, dtype=np.int16).tobytes()
    res_silence = await stt.transcribe_audio_chunk(silence_pcm)
    assert isinstance(res_silence, str)

@pytest.mark.asyncio
async def test_edge_tts_service():
    tts = EdgeTTSService(voice="en-US-AvaNeural")
    
    async def dummy_text_stream():
        yield "Hello. "
        yield "This is a test of streaming TTS synthesis."

    chunks = []
    async for chunk in tts.stream_tts(dummy_text_stream()):
        chunks.append(chunk)
    
    assert len(chunks) > 0
    assert isinstance(chunks[0], bytes)

def test_websocket_audio_endpoint():
    with client.websocket_connect("/ws/audio") as websocket:
        # Register device
        websocket.send_json({
            "type": "register",
            "device_id": "test_device_1",
            "device_name": "Test Runner",
            "device_type": "pytest"
        })
        
        # Read messages until registered confirmation
        msg = websocket.receive_json()
        if msg.get("type") == "presence_update":
            msg = websocket.receive_json()

        assert msg.get("type") == "registered"

        # Interrupt signal test
        websocket.send_json({"type": "interrupt"})

def test_desktop_audio_pipe_decoding():
    if desktop_dir not in sys.path:
        sys.path.append(desktop_dir)
    try:
        from audio_pipe import AudioPipeManager
        pipe = AudioPipeManager()
        # Test play_chunk with silence PCM
        silence_pcm = np.zeros(160, dtype=np.int16).tobytes()
        pipe.play_chunk(silence_pcm)
        pipe.flush_output()
    except Exception as e:
        pytest.fail(f"Desktop audio pipe test raised exception: {e}")
