from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.state.device_sync import device_sync_manager
from app.db.memory import memory_store

router = APIRouter()

class TransferSessionRequest(BaseModel):
    target_device_id: str

class DeviceControlRequest(BaseModel):
    target_device_id: str
    speaker_enabled: Optional[bool] = None

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Ambient Audio Agent Server",
        "sync_engine": "online"
    }

@router.get("/api/devices")
async def list_devices():
    return {
        "session_id": device_sync_manager.current_session_id,
        "active_mic_device_id": device_sync_manager.active_mic_device_id,
        "devices": device_sync_manager.get_online_devices()
    }

@router.post("/api/session/transfer")
async def transfer_session(req: TransferSessionRequest):
    success = await device_sync_manager.transfer_session(req.target_device_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Target device {req.target_device_id} not found.")
    
    await memory_store.log_device_event(
        device_id=req.target_device_id,
        device_name="Target",
        device_type="Unknown",
        event_type="session_transfer_received"
    )
    return {
        "status": "success",
        "active_mic_device_id": device_sync_manager.active_mic_device_id
    }

@router.post("/api/session/control")
async def control_device(req: DeviceControlRequest):
    if req.speaker_enabled is not None:
        await device_sync_manager.set_speaker_output(req.target_device_id, req.speaker_enabled)
    return {"status": "success"}

@router.get("/api/messages")
async def get_messages(session_id: str = "default_session", limit: int = 30):
    messages = await memory_store.get_recent_messages(session_id, limit)
    return {"session_id": session_id, "messages": messages}
