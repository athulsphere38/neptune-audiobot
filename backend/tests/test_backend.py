import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
import numpy as np

from main import app

from app.core.vad import VoiceActivityDetector
from app.db.memory import MemoryStore

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
