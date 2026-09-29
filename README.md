# AURA — Cross-Device Ambient Audio Agent (Phase 2 Real Voice Conversation)

An end-to-end, low-latency, cross-platform **Ambient Audio/Voice Bot** engineered to operate seamlessly across Web PWAs, Desktop Tray Daemons, and Mobile devices with real-time synchronized context, presence registry, local AI pipeline (FasterWhisper STT + Ollama LLM + Edge-TTS), and audio session handoff.

---

## 🏗 Core Pipeline Architecture

```
[Microphone Audio In]
       │ (16kHz 16-bit Linear PCM Stream / Web Audio Worklet / WebSocket)
       ▼
[Voice Activity Detection (Silero VAD / Dynamic RMS Threshold)]
       │ (speech_start / speech_chunk / speech_end)
       ▼
[Local / Cloud STT (FasterWhisper CPU int8 / Deepgram Nova-2 / Groq Whisper)]
       │ (Transcribed User Speech Segment)
       ▼
[Local / Cloud LLM (Ollama / OpenAI / Groq / Gemini)]
       │ (Streaming Token Yield via SQLite Session Memory)
       ▼
[Low-Latency TTS (Edge-TTS AvaNeural / Cartesia / ElevenLabs)]
       │ (Streaming MP3 / PCM Audio Chunks)
       ▼
[Audio Sink / Speaker Out on Active Device (Web Audio Queue / PyAV SoundDevice)]
```

---

## 🌟 Verified Features (Phase 2 Production Milestone)

1. **Free Local Speech-to-Text (`faster-whisper`)**:
   - Uses `faster-whisper` on CPU with `int8` quantization for zero-cost, high-speed, local 16kHz PCM transcription.
   - VAD speech boundary detection with silence filtering.
2. **Local Ollama LLM Integration**:
   - Direct connection to local Ollama server at `http://localhost:11434` with model `llama3.2` (or configured via `OLLAMA_MODEL`).
   - Real-time token streaming over WebSocket (`llm_delta`).
   - Clear error diagnostics if Ollama service is offline (no silent fake mocks).
3. **Text-to-Speech (`edge-tts`) & Format Adapter**:
   - Zero-cost streaming speech synthesis via `edge-tts` (`en-US-AvaNeural`).
   - Web PWA decodes audio via Web Audio API `decodeAudioData`.
   - Desktop client auto-decodes MP3 stream to 16kHz PCM via PyAV resampler before playing through `sounddevice`.
4. **Instant Interruption & Barge-In**:
   - Server-side active generation/streaming task cancellation on user speech or manual interruption (`{"type": "interrupt"}`).
   - Web PWA `StreamingAudioPlayer.flush()` instantly stops playing audio and clears queue.
   - Desktop client `audio_pipe.flush_output()` stops hardware speaker output.
5. **Multi-Device Synchronization & Session Handoff**:
   - Real-time device registration, active microphone tracking, and cross-device session handoff.
6. **SQLite Conversation Memory**:
   - Stores session history and device audit logs via `aiosqlite`.

---

## 📂 Codebase Directory Layout

```
audiobot--/
├── backend/
├── app/
│   ├── core/         # Config, VAD engine, settings
│   ├── services/     # FasterWhisper STT, Ollama LLM, Edge-TTS providers
│   ├── api/          # WebSocket routes (/ws/audio, /ws/sync), REST API (/health, /api/devices)
│   ├── state/        # Session manager, device sync registry
│   └── db/           # SQLite conversation memory store
├── tests/            # Automated pytest test suite
├── main.py           # FastAPI entrypoint
├── requirements.txt  # Python backend dependencies
└── .env.example      # Environment configuration
├── web-client/           # PWA web client
│   ├── src/
│   │   ├── app.js        # Main UI orchestrator & Canvas visualizer
│   │   ├── audio-processor.worklet.js # 16kHz PCM AudioWorklet
│   │   ├── audio-player.js            # Audio player with flush()
│   │   └── sync-client.js             # Device sync WS client
│   ├── index.html        # Modern HTML shell
│   ├── style.css         # Dark glassmorphic styling
│   └── manifest.json
├── desktop-client/       # Desktop background tray daemon
│   ├── main.py           # Tray daemon with hotkey Ctrl+Shift+Space
│   ├── audio_pipe.py     # Hardware sound capture & PyAV playback decoder
│   └── requirements.txt
└── README.md
```

---

## 🚀 Step-by-Step Windows Installation & Quick Start

### 1. Prerequisites
- **Python**: 3.10+ (Tested on Python 3.14)
- **Ollama**: Download and install from [ollama.com](https://ollama.com)

### 2. Ollama Setup
Pull a laptop-friendly local model (e.g. `llama3.2` or `tinyllama`):
```cmd
ollama pull llama3.2
```
Ensure Ollama server is running (default port: `http://localhost:11434`).

### 3. Backend Setup & Virtual Environment

```cmd
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install faster-whisper ollama
```

Copy `.env.example` to `.env` if custom configuration is required:
```cmd
copy .env.example .env
```

Start the backend FastAPI server:
```cmd
python main.py
```
Backend will start on `http://localhost:8000`. Verify health at `http://localhost:8000/health`.

### 4. Running the Web Client (PWA)

In a new terminal window:
```cmd
cd web-client
python -m http.server 3000
```
Open `http://localhost:3000` in your browser. Click **Start Mic** to grant microphone access and start real-time voice conversation.

### 5. Running the Desktop Tray Daemon (Optional)

In a new terminal window:
```cmd
cd desktop-client
pip install -r requirements.txt
python main.py
```
The tray daemon connects to `ws://localhost:8000/ws/audio`. Press `Ctrl+Shift+Space` to trigger instant barge-in interruption.

---

## 🧪 Automated Testing

Run the automated test suite:
```cmd
cd backend
pytest -v
```

Tests cover:
- `/health` and `/api/devices` REST endpoints
- Voice Activity Detector (VAD) speech boundary & RMS energy transitions
- SQLite session memory read/write
- Ollama LLM response streaming & offline server error diagnostics
- `faster-whisper` STT model load & PCM transcription
- `edge-tts` streaming synthesis
- WebSocket handshake, device registration, and interruption signals
- Desktop audio pipe MP3 PyAV decoding and playback

---

## ⚠️ Known Limitations & Hardware Context

- **Ollama Offline**: If Ollama is not running on `http://localhost:11434`, the server sends a clear diagnostic error response (`Ollama service unavailable...`) so you can launch Ollama.
- **Microphone Hardware in Headless Environment**: Automated CI unit tests run against mock/recorded audio fixtures. Live voice testing requires physical microphone hardware connected to the machine.

---

## 🛠 Recommended Development Next Steps (Phase 3)

1. Add local wake-word engine (e.g. OpenWakeWord / Porcupine) for hands-free activation.
2. Implement semantic RAG / tool-calling integrations with local SQLite knowledge search.
3. Enhance desktop daemon tray UI with real-time audio input level meter.
