/**
 * WebSocket Multi-Device Synchronization & Handoff Client.
 */
export class DeviceSyncClient {
  constructor(wsBaseUrl) {
    this.wsUrl = `${wsBaseUrl}/ws/sync`;
    this.ws = null;
    this.onPresenceUpdate = null;
    this.onSessionTransferred = null;
    this.deviceId = this.getOrCreateDeviceId();
  }

  getOrCreateDeviceId() {
    let id = localStorage.getItem('audiobot_device_id');
    if (!id) {
      id = 'web_' + Math.random().toString(36).substring(2, 10);
      localStorage.setItem('audiobot_device_id', id);
    }
    return id;
  }

  connect() {
    this.ws = new WebSocket(this.wsUrl);

    this.ws.onopen = () => {
      console.log('Sync WebSocket connected.');
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'presence_update') {
          if (this.onPresenceUpdate) this.onPresenceUpdate(data);
        } else if (data.type === 'session_transferred') {
          if (this.onSessionTransferred) this.onSessionTransferred(data);
        }
      } catch (err) {
        console.error('Error parsing sync message:', err);
      }
    };

    this.ws.onclose = () => {
      console.log('Sync WebSocket closed. Reconnecting in 3s...');
      setTimeout(() => this.connect(), 3000);
    };

    this.ws.onerror = (err) => {
      console.error('Sync WS Error:', err);
    };
  }

  transferSession(targetDeviceId) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'transfer_session',
        target_device_id: targetDeviceId
      }));
    }
  }
}
