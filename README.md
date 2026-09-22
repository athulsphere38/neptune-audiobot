# Cross-Device Ambient Audio Agent Architecture & Implementation

An end-to-end, ultra-low-latency, cross-platform **Ambient Audio/Voice Bot** engineered to operate seamlessly across Web PWAs, Desktop Tray Daemons, and Mobile devices with real-time synchronized context, presence registry, and audio session handoff.

---

## 🏗 Core Pipeline Architecture

```
[Microphone Audio In]
       │ (16kHz 16-bit Linear PCM Stream / Web Audio Worklet / WebSocket)
       ▼
[Voice Activity Detection (Silero VAD / Dynamic RMS Threshold)]
       │ (speech_start / speech_chunk / speech_end)
       ▼
[Streaming STT (Deepgram Nova-2 / Groq Whisper / Mock Service)]
       │ (Interim & Final Transcripts)
       ▼
[Agent Core / Tool Orchestrator (FastAPI Async Streaming + Memory Context)]
       │ (Streaming Token Yield via Function Calling & System Context)
       ▼
[Low-Latency TTS (Cartesia Sonic / ElevenLabs Turbo v2.5 / Edge-TTS)]
       │ (Streaming MP3 / PCM Audio Chunks)
       ▼
[Audio Sink / Speaker Out on Active Device (Web Audio Queue / SoundDevice)]
```

---

## 🌟 Key Features

1. **Ultra-Low Latency Duplex Streaming**: Raw 16kHz 16-bit linear PCM audio streaming over bidirectional WebSockets without full-sentence buffering.
2. **Hardware-Thread Mic Capture**: Web Audio `AudioWorkletProcessor` (`audio-processor.worklet.js`) downsampling microphone data off the main UI thread.
3. **Instant Barge-In (Interruption Handling)**: When user speaks while bot is outputting audio, server immediately emits `interrupted` signal, cancels downstream LLM/TTS pipeline, and client flushes speaker audio buffer instantly.
4. **Multi-Device Synchronization & Session Handoff**: Central WebSocket state broker tracking connected devices (`web_pwa`, `desktop_tray`, `mobile_pwa`) with `/api/session/transfer` REST/WS endpoints for zero-friction active session transfers.
5. **Persistent Conversation Memory**: SQLite DB (`aiosqlite`) storing session messages and device audit history.
6. **Zero-Configuration Fallback Support**: Built-in zero-cost providers (`edge-tts`, RMS VAD engine, mock streaming) so the codebase is 100% runnable without paid API keys, while fully supporting production keys (`DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `CARTESIA_API_KEY`, `ELEVENLABS_API_KEY`).

---

## 📂 Codebase Directory Layout

```
audiobot--/
├── backend/
│   ├── app/
│   │   ├── core/         # Config, VAD, audio buffers
│   │   ├── services/     # STT, LLM, TTS providers
│   │   ├── api/          # WebSocket routes, REST endpoints
│   │   ├── state/        # Session manager, device sync
│   │   └── db/           # SQLite conversation memory
│   ├── tests/            # Automated pytest test suite
│   ├── main.py           # FastAPI entrypoint
│   ├── requirements.txt  # Python backend dependencies
│   └── .env.example      # Environment config example
├── web-client/           # PWA with AudioWorklet & Canvas Visualizer
│   ├── src/
│   │   ├── app.js        # Main UI & visualizer orchestrator
│   │   ├── audio-processor.worklet.js # 16kHz PCM AudioWorklet
│   │   ├── audio-player.js            # Streaming player with flush()
│   │   └── sync-client.js             # WebSocket multi-device sync
│   ├── index.html        # Glassmorphic HTML shell
│   ├── style.css         # Modern dark glassmorphic styling
│   ├── manifest.json     # PWA manifest
│   └── sw.js             # Service worker
├── desktop-client/       # Desktop background tray daemon
│   ├── main.py           # Tray daemon with global hotkeys
│   ├── audio_pipe.py     # Hardware sound capture & playback
│   └── requirements.txt  # Desktop dependencies
└── README.md
```

---

## 🚀 Quick Start Guide

### 1. Backend Server Setup

```bash
cd backend
pip install -r requirements.txt

# Start backend server on http://localhost:8000
python main.py
```

### 2. Web Client (PWA)

Serve the `web-client` directory using any static web server (e.g. Python `http.server` or Vite/live-server):

```bash
cd web-client
python -m http.server 3000
```
Open `http://localhost:3000` in Chrome/Edge/Safari or on a mobile browser on the same Wi-Fi network.

### 3. Desktop Tray Daemon

```bash
cd desktop-client
pip install -r requirements.txt
python main.py
```

---

## 🧪 Verification & Testing

Run automated backend unit tests:
```bash
python -m pytest backend/tests -v
```
