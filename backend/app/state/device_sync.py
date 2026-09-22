import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Set
from fastapi import WebSocket

logger = logging.getLogger("audiobot.sync")

class DeviceInfo:
    def __init__(self, device_id: str, device_name: str, device_type: str, client_ws: WebSocket):
        self.device_id = device_id
        self.device_name = device_name
        self.device_type = device_type # 'web_pwa', 'desktop_tray', 'mobile_pwa'
        self.ws = client_ws
        self.is_active_mic = False
        self.is_active_speaker = True
        self.connected_at = asyncio.get_event_loop().time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "is_active_mic": self.is_active_mic,
            "is_active_speaker": self.is_active_speaker
        }

class DeviceSyncManager:
    def __init__(self):
        # Map of device_id -> DeviceInfo
        self.devices: Dict[str, DeviceInfo] = {}
        # Active session ID mapping
        self.current_session_id: str = "default_session"
        self.active_mic_device_id: Optional[str] = None
        self.sync_connections: Set[WebSocket] = set()

    async def register_sync_connection(self, websocket: WebSocket):
        await websocket.accept()
        self.sync_connections.add(websocket)
        logger.info(f"Sync WebSocket connected. Total sync sockets: {len(self.sync_connections)}")
        # Send current state immediately
        await self.broadcast_device_state()

    def unregister_sync_connection(self, websocket: WebSocket):
        if websocket in self.sync_connections:
            self.sync_connections.remove(websocket)
            logger.info("Sync WebSocket disconnected.")

    async def register_device(self, device_id: str, device_name: str, device_type: str, websocket: WebSocket) -> DeviceInfo:
        device = DeviceInfo(device_id, device_name, device_type, websocket)
        
        # If first device, auto-assign active mic
        if not self.active_mic_device_id or len(self.devices) == 0:
            device.is_active_mic = True
            self.active_mic_device_id = device_id

        self.devices[device_id] = device
        logger.info(f"Device registered: {device_name} ({device_id}, {device_type})")
        await self.broadcast_device_state()
        return device

    async def unregister_device(self, device_id: str):
        if device_id in self.devices:
            dev = self.devices.pop(device_id)
            logger.info(f"Device unregistered: {dev.device_name} ({device_id})")
            
            if self.active_mic_device_id == device_id:
                # Reassign mic to next available device
                if self.devices:
                    next_id = next(iter(self.devices))
                    self.devices[next_id].is_active_mic = True
                    self.active_mic_device_id = next_id
                else:
                    self.active_mic_device_id = None
            
            await self.broadcast_device_state()

    async def transfer_session(self, target_device_id: str) -> bool:
        """
        Transfers active microphone session to target_device_id.
        """
        if target_device_id not in self.devices:
            logger.warning(f"Target device {target_device_id} not found for transfer.")
            return False

        for dev_id, dev in self.devices.items():
            if dev_id == target_device_id:
                dev.is_active_mic = True
                self.active_mic_device_id = target_device_id
            else:
                dev.is_active_mic = False

        logger.info(f"Session transferred to device: {target_device_id}")
        await self.broadcast_device_state()
        await self.broadcast_event({
            "type": "session_transferred",
            "active_device_id": target_device_id,
            "session_id": self.current_session_id
        })
        return True

    async def set_speaker_output(self, target_device_id: str, enabled: bool):
        if target_device_id in self.devices:
            self.devices[target_device_id].is_active_speaker = enabled
            await self.broadcast_device_state()

    async def broadcast_device_state(self):
        state_payload = {
            "type": "presence_update",
            "session_id": self.current_session_id,
            "active_mic_device_id": self.active_mic_device_id,
            "devices": [dev.to_dict() for dev in self.devices.values()]
        }
        await self.broadcast_event(state_payload)

    async def broadcast_event(self, event_data: Dict[str, Any], exclude_ws: Optional[WebSocket] = None):
        message = json.dumps(event_data)
        # Broadcast to all sync WS connections
        disconnected = []
        for ws in list(self.sync_connections):
            if ws == exclude_ws:
                continue
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.unregister_sync_connection(ws)

        # Broadcast to all audio WS connections
        for dev in list(self.devices.values()):
            if dev.ws == exclude_ws:
                continue
            try:
                await dev.ws.send_text(message)
            except Exception:
                pass

    def get_online_devices(self) -> List[Dict[str, Any]]:
        return [dev.to_dict() for dev in self.devices.values()]

device_sync_manager = DeviceSyncManager()
