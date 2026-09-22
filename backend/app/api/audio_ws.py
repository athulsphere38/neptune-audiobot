import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.vad import VoiceActivityDetector
from app.core.config import settings
from app.services.stt import get_stt_service
from app.services.llm import get_llm_service
from app.services.tts import get_tts_service
from app.state.device_sync import device_sync_manager, DeviceInfo
from app.db.memory import memory_store

logger = logging.getLogger("audiobot.ws")
router = APIRouter()

@router.websocket("/ws/sync")
async def sync_websocket_endpoint(websocket: WebSocket):
    await device_sync_manager.register_sync_connection(websocket)
    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
                msg_type = data.get("type")
                if msg_type == "transfer_session":
                    target_id = data.get("target_device_id")
                    if target_id:
                        await device_sync_manager.transfer_session(target_id)
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        device_sync_manager.unregister_sync_connection(websocket)
    except Exception as e:
        logger.error(f"Sync WS Error: {e}")
        device_sync_manager.unregister_sync_connection(websocket)

@router.websocket("/ws/audio")
async def audio_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    device: Optional[DeviceInfo] = None
    vad = VoiceActivityDetector(
        sample_rate=settings.SAMPLE_RATE,
        threshold=settings.VAD_THRESHOLD,
        silence_ms=settings.SILENCE_DURATION_MS
    )
    
    stt_service = get_stt_service()
    llm_service = get_llm_service()
    tts_service = get_tts_service()

    bot_state = "idle" # idle, listening, thinking, speaking
    active_tts_task: Optional[asyncio.Task] = None

    async def update_state(new_state: str):
        nonlocal bot_state
        bot_state = new_state
        await websocket.send_json({"type": "state", "state": new_state})
        await device_sync_manager.broadcast_event({
            "type": "state_change",
            "device_id": device.device_id if device else "unknown",
            "state": new_state
        }, exclude_ws=websocket)

    async def cancel_ongoing_tts():
        nonlocal active_tts_task
        if active_tts_task and not active_tts_task.done():
            active_tts_task.cancel()
            active_tts_task = None
            logger.info("Cancelled ongoing TTS streaming pipeline due to user interruption.")
            await websocket.send_json({"type": "interrupted"})
            await update_state("listening")

    async def process_speech_and_respond(audio_bytes: bytes, explicit_transcript: Optional[str] = None):
        nonlocal active_tts_task
        try:
            await update_state("thinking")

            if explicit_transcript:
                transcript = explicit_transcript
            else:
                transcript = await stt_service.transcribe_audio_chunk(audio_bytes)

            if not transcript:
                logger.info("STT returned empty transcript.")
                await update_state("idle")
                return

            logger.info(f"User transcript: '{transcript}'")
            await websocket.send_json({"type": "transcript", "role": "user", "text": transcript})
            
            # Save to SQLite conversation memory
            session_id = device_sync_manager.current_session_id
            await memory_store.add_message(session_id, "user", transcript)

            # Retrieve recent memory context
            history = await memory_store.get_recent_messages(session_id, limit=10)

            await update_state("speaking")

            # Helper for LLM -> TTS stream
            async def generate_and_stream():
                full_bot_response = ""
                
                # Generator for LLM tokens
                async def llm_token_generator():
                    nonlocal full_bot_response
                    async for token in llm_service.stream_completion(transcript, history):
                        full_bot_response += token
                        await websocket.send_json({"type": "llm_delta", "text": token})
                        yield token

                # Synthesize TTS chunks and send to client
                try:
                    async for audio_chunk in tts_service.stream_tts(llm_token_generator()):
                        if bot_state != "speaking":
                            break
                        # Send raw audio bytes
                        await websocket.send_bytes(audio_chunk)
                        await asyncio.sleep(0.001)

                    if full_bot_response.strip():
                        await memory_store.add_message(session_id, "assistant", full_bot_response.strip())
                        await websocket.send_json({"type": "transcript", "role": "assistant", "text": full_bot_response})

                except asyncio.CancelledError:
                    logger.info("TTS Task cancelled cleanly.")
                    raise
                finally:
                    if bot_state == "speaking":
                        await update_state("idle")

            active_tts_task = asyncio.create_task(generate_and_stream())
            await active_tts_task

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error processing speech pipeline: {e}", exc_info=True)
            await update_state("idle")

    try:
        while True:
            message = await websocket.receive()
            
            if message.get("type") == "websocket.disconnect":
                break

            # Handle JSON messages (handshake, transcript, control)
            if "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "register":
                        dev_id = data.get("device_id", "web_client")
                        dev_name = data.get("device_name", "Web Client")
                        dev_type = data.get("device_type", "web_pwa")
                        device = await device_sync_manager.register_device(dev_id, dev_name, dev_type, websocket)
                        await websocket.send_json({
                            "type": "registered",
                            "device_id": device.device_id,
                            "is_active_mic": device.is_active_mic
                        })
                        await update_state("idle")

                    elif msg_type == "explicit_transcript":
                        text = data.get("text", "")
                        if text:
                            await cancel_ongoing_tts()
                            asyncio.create_task(process_speech_and_respond(b"", explicit_transcript=text))

                    elif msg_type == "interrupt":
                        await cancel_ongoing_tts()

                except json.JSONDecodeError:
                    pass

            # Handle Binary 16kHz PCM audio frames
            elif "bytes" in message and message["bytes"]:
                pcm_bytes = message["bytes"]

                # If user speaks while bot is speaking, perform instant BARGE-IN interruption
                if bot_state in ["speaking", "thinking"]:
                    # Check energy threshold for fast barge-in
                    import numpy as np
                    audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
                    if len(audio_int16) > 0:
                        rms = float(np.sqrt(np.mean((audio_int16.astype(np.float32) / 32768.0) ** 2)))
                        if rms > 0.03: # High energy user interruption
                            logger.info(f"Instant Barge-In detected! RMS={rms:.4f}")
                            await cancel_ongoing_tts()
                            vad.reset()

                # Process chunk through VAD engine
                event, speech_bytes = vad.process_pcm_chunk(pcm_bytes)

                if event == "speech_start":
                    await update_state("listening")
                elif event == "speech_end":
                    if speech_bytes:
                        asyncio.create_task(process_speech_and_respond(speech_bytes))

    except WebSocketDisconnect:
        logger.info("Audio WebSocket disconnected.")
    except Exception as e:
        logger.error(f"Audio WS Exception: {e}")
    finally:
        if device:
            await device_sync_manager.unregister_device(device.device_id)
