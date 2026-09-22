import { StreamingAudioPlayer } from './audio-player.js';
import { DeviceSyncClient } from './sync-client.js';

class AmbientAudioApp {
  constructor() {
    this.serverHost = window.location.hostname || 'localhost';
    this.serverPort = '8000';
    this.wsBaseUrl = `ws://${this.serverHost}:${this.serverPort}`;
    this.apiBaseUrl = `http://${this.serverHost}:${this.serverPort}`;

    this.audioPlayer = new StreamingAudioPlayer();
    this.syncClient = new DeviceSyncClient(this.wsBaseUrl);
    
    this.audioWs = null;
    this.audioCtx = null;
    this.workletNode = null;
    this.mediaStream = null;

    this.botState = 'idle'; // idle, listening, thinking, speaking
    this.isMicActive = false;
    this.deviceId = this.syncClient.deviceId;
    this.deviceName = this.getDeviceName();

    this.initDOM();
    this.initCanvasVisualizer();
    this.initSync();
  }

  getDeviceName() {
    const ua = navigator.userAgent;
    if (/mobile/i.test(ua)) return 'Mobile Browser';
    if (/Macintosh/i.test(ua)) return 'Mac Web Client';
    if (/Windows/i.test(ua)) return 'Windows Web Client';
    return 'Web Client';
  }

  initDOM() {
    this.orbCanvas = document.getElementById('orb-canvas');
    this.stateBadge = document.getElementById('state-badge');
    this.micToggleBtn = document.getElementById('mic-toggle-btn');
    this.interruptBtn = document.getElementById('interrupt-btn');
    this.transcriptList = document.getElementById('transcript-list');
    this.devicesList = document.getElementById('devices-list');
    this.textInput = document.getElementById('text-input');
    this.sendTextBtn = document.getElementById('send-text-btn');

    this.micToggleBtn.addEventListener('click', () => this.toggleMicrophone());
    this.interruptBtn.addEventListener('click', () => this.handleInterrupt());
    
    if (this.sendTextBtn && this.textInput) {
      this.sendTextBtn.addEventListener('click', () => this.sendTextMessage());
      this.textInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') this.sendTextMessage();
      });
    }
  }

  initSync() {
    this.syncClient.onPresenceUpdate = (data) => this.renderPresence(data);
    this.syncClient.onSessionTransferred = (data) => {
      this.addTranscript('system', `Session context transferred to device ID: ${data.active_device_id}`);
    };
    this.syncClient.connect();
    this.connectAudioWs();
  }

  connectAudioWs() {
    this.audioWs = new WebSocket(`${this.wsBaseUrl}/ws/audio`);
    this.audioWs.binaryType = 'arraybuffer';

    this.audioWs.onopen = () => {
      console.log('Audio WebSocket connected.');
      // Register device
      this.audioWs.send(JSON.stringify({
        type: 'register',
        device_id: this.deviceId,
        device_name: this.deviceName,
        device_type: 'web_pwa'
      }));
    };

    this.audioWs.onmessage = async (event) => {
      if (typeof event.data === 'string') {
        const data = JSON.parse(event.data);
        this.handleServerSignal(data);
      } else if (event.data instanceof ArrayBuffer) {
        // Incoming audio chunk from server TTS
        if (this.botState !== 'speaking') {
          this.setBotState('speaking');
        }
        await this.audioPlayer.playChunk(event.data);
      }
    };

    this.audioWs.onclose = () => {
      console.log('Audio WebSocket closed. Reconnecting in 3s...');
      setTimeout(() => this.connectAudioWs(), 3000);
    };
  }

  handleServerSignal(data) {
    if (data.type === 'state') {
      this.setBotState(data.state);
    } else if (data.type === 'interrupted') {
      console.log('Server sent interruption signal!');
      this.audioPlayer.flush();
      this.setBotState('listening');
    } else if (data.type === 'transcript') {
      this.addTranscript(data.role, data.text);
    } else if (data.type === 'llm_delta') {
      this.appendLlmDelta(data.text);
    }
  }

  async toggleMicrophone() {
    if (this.isMicActive) {
      this.stopMicrophone();
    } else {
      await this.startMicrophone();
    }
  }

  async startMicrophone() {
    try {
      this.audioPlayer.init();
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      const AudioContext = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new AudioContext();
      
      // Load AudioWorklet processor
      await this.audioCtx.audioWorklet.addModule('./src/audio-processor.worklet.js');
      
      const source = this.audioCtx.createMediaStreamSource(this.mediaStream);
      this.workletNode = new AudioWorkletNode(this.audioCtx, 'audio-processor');

      this.workletNode.port.onmessage = (event) => {
        if (this.audioWs && this.audioWs.readyState === WebSocket.OPEN) {
          // Send raw 16kHz PCM ArrayBuffer to backend server
          this.audioWs.send(event.data);
        }
      };

      source.connect(this.workletNode);
      this.workletNode.connect(this.audioCtx.destination);

      this.isMicActive = true;
      this.micToggleBtn.classList.add('active');
      this.micToggleBtn.querySelector('.btn-label').textContent = 'Mute Mic';
      this.setBotState('listening');
    } catch (err) {
      console.error('Microphone Access Error:', err);
      alert('Microphone access failed: ' + err.message);
    }
  }

  stopMicrophone() {
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.audioCtx) {
      this.audioCtx.close();
      this.audioCtx = null;
    }
    this.isMicActive = false;
    this.micToggleBtn.classList.remove('active');
    this.micToggleBtn.querySelector('.btn-label').textContent = 'Start Mic';
    this.setBotState('idle');
  }

  handleInterrupt() {
    this.audioPlayer.flush();
    if (this.audioWs && this.audioWs.readyState === WebSocket.OPEN) {
      this.audioWs.send(JSON.stringify({ type: 'interrupt' }));
    }
    this.setBotState('listening');
  }

  sendTextMessage() {
    const text = this.textInput.value.trim();
    if (!text) return;
    this.textInput.value = '';

    this.audioPlayer.flush();
    if (this.audioWs && this.audioWs.readyState === WebSocket.OPEN) {
      this.audioWs.send(JSON.stringify({
        type: 'explicit_transcript',
        text: text
      }));
    }
  }

  setBotState(state) {
    this.botState = state;
    this.stateBadge.textContent = state.toUpperCase();
    this.stateBadge.className = `state-badge state-${state}`;
  }

  addTranscript(role, text) {
    const item = document.createElement('div');
    item.className = `transcript-item ${role}-item`;
    item.innerHTML = `
      <div class="role-tag">${role.toUpperCase()}</div>
      <div class="content">${text}</div>
    `;
    this.transcriptList.appendChild(item);
    this.transcriptList.scrollTop = this.transcriptList.scrollHeight;
  }

  appendLlmDelta(text) {
    let lastItem = this.transcriptList.lastElementChild;
    if (!lastItem || !lastItem.classList.contains('assistant-item')) {
      this.addTranscript('assistant', text);
    } else {
      const contentEl = lastItem.querySelector('.content');
      contentEl.textContent += text;
      this.transcriptList.scrollTop = this.transcriptList.scrollHeight;
    }
  }

  renderPresence(data) {
    if (!this.devicesList) return;
    this.devicesList.innerHTML = '';
    const devices = data.devices || [];

    devices.forEach((dev) => {
      const isSelf = dev.device_id === this.deviceId;
      const card = document.createElement('div');
      card.className = `device-card ${dev.is_active_mic ? 'active-mic' : ''}`;
      card.innerHTML = `
        <div class="device-info">
          <span class="device-name">${dev.device_name} ${isSelf ? '(This Device)' : ''}</span>
          <span class="device-type">${dev.device_type}</span>
        </div>
        <div class="device-actions">
          ${dev.is_active_mic 
            ? '<span class="active-tag">Active Audio Source</span>'
            : `<button class="handoff-btn" data-id="${dev.device_id}">Handoff Session</button>`}
        </div>
      `;

      const handoffBtn = card.querySelector('.handoff-btn');
      if (handoffBtn) {
        handoffBtn.addEventListener('click', () => {
          this.syncClient.transferSession(dev.device_id);
        });
      }

      this.devicesList.appendChild(card);
    });
  }

  initCanvasVisualizer() {
    const canvas = this.orbCanvas;
    const ctx = canvas.getContext('2d');
    let angle = 0;

    const resize = () => {
      canvas.width = canvas.parentElement.clientWidth;
      canvas.height = canvas.parentElement.clientHeight;
    };
    window.addEventListener('resize', resize);
    resize();

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const baseRadius = Math.min(centerX, centerY) * 0.45;

      angle += 0.03;

      // Color scheme according to state
      let color1, color2;
      if (this.botState === 'idle') {
        color1 = 'rgba(0, 242, 254, 0.6)';
        color2 = 'rgba(79, 172, 254, 0.2)';
      } else if (this.botState === 'listening') {
        color1 = 'rgba(16, 185, 129, 0.8)';
        color2 = 'rgba(52, 211, 153, 0.3)';
      } else if (this.botState === 'thinking') {
        color1 = 'rgba(139, 92, 246, 0.8)';
        color2 = 'rgba(192, 132, 252, 0.3)';
      } else if (this.botState === 'speaking') {
        color1 = 'rgba(236, 72, 153, 0.9)';
        color2 = 'rgba(244, 114, 182, 0.4)';
      }

      // Draw glowing background aura
      const grad = ctx.createRadialGradient(centerX, centerY, 5, centerX, centerY, baseRadius * 1.6);
      grad.addColorStop(0, color1);
      grad.addColorStop(0.6, color2);
      grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, baseRadius * 1.6, 0, Math.PI * 2);
      ctx.fill();

      // Draw pulsating waveform orb
      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.beginPath();
      const points = 80;
      for (let i = 0; i <= points; i++) {
        const theta = (i / points) * Math.PI * 2;
        let r = baseRadius;

        if (this.botState === 'listening') {
          r += Math.sin(theta * 6 + angle * 2) * 12;
        } else if (this.botState === 'thinking') {
          r += Math.cos(theta * 8 - angle * 3) * 16;
        } else if (this.botState === 'speaking') {
          r += Math.sin(theta * 10 + angle * 4) * (20 + Math.sin(angle * 2) * 10);
        } else {
          r += Math.sin(theta * 4 + angle) * 4;
        }

        const x = Math.cos(theta) * r;
        const y = Math.sin(theta) * r;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.strokeStyle = color1;
      ctx.lineWidth = 3;
      ctx.shadowColor = color1;
      ctx.shadowBlur = 20;
      ctx.stroke();
      ctx.restore();

      requestAnimationFrame(render);
    };

    render();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new AmbientAudioApp();
});
