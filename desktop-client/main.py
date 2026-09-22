import time
import json
import threading
import logging
import uuid
import websocket
from PIL import Image, ImageDraw
import pystray

from audio_pipe import AudioPipeManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [DesktopDaemon] - %(levelname)s - %(message)s"
)
logger = logging.getLogger("desktop_daemon")

SERVER_WS_URL = "ws://localhost:8000/ws/audio"
DEVICE_ID = "desktop_" + str(uuid.uuid4())[:8]
DEVICE_NAME = "Windows Desktop Daemon"

class DesktopDaemonApp:
    def __init__(self):
        self.ws = None
        self.audio_pipe = AudioPipeManager()
        self.is_connected = False
        self.is_ptt_active = False
        self.icon = None

    def create_tray_icon_image(self, color="cyan"):
        image = Image.new('RGB', (64, 64), color=(15, 23, 42))
        draw = ImageDraw.Draw(image)
        c_map = {
            "cyan": (0, 242, 254),
            "green": (16, 185, 129),
            "pink": (236, 72, 153),
            "red": (239, 68, 68)
        }
        fill_color = c_map.get(color, (0, 242, 254))
        draw.ellipse((16, 16, 48, 48), fill=fill_color, outline=(255, 255, 255), width=2)
        return image

    def on_ws_open(self, ws):
        logger.info("Connected to Ambient Hub WebSocket!")
        self.is_connected = True
        # Register device
        reg_payload = {
            "type": "register",
            "device_id": DEVICE_ID,
            "device_name": DEVICE_NAME,
            "device_type": "desktop_tray"
        }
        ws.send(json.dumps(reg_payload))

        # Start continuous audio mic capture callback
        self.audio_pipe.start_capture(self.send_audio_chunk)

    def on_ws_message(self, ws, message):
        if isinstance(message, str):
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                if msg_type == "state":
                    state = data.get("state")
                    logger.info(f"Server bot state: {state}")
                    if self.icon:
                        c_val = "green" if state == "listening" else "pink" if state == "speaking" else "cyan"
                        self.icon.icon = self.create_tray_icon_image(c_val)
                elif msg_type == "interrupted":
                    logger.info("Interruption signal received. Flushing desktop speaker playback.")
                    self.audio_pipe.flush_output()
                elif msg_type == "transcript":
                    logger.info(f"Transcript [{data.get('role')}]: {data.get('text')}")
            except Exception as e:
                logger.error(f"Error parsing message: {e}")
        elif isinstance(message, bytes):
            # Incoming audio chunk from server TTS
            self.audio_pipe.play_chunk(message)

    def on_ws_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def on_ws_close(self, ws, close_status_code, close_msg):
        logger.info("WebSocket disconnected. Retrying in 5 seconds...")
        self.is_connected = False
        time.sleep(5)
        self.connect_ws()

    def send_audio_chunk(self, pcm_bytes: bytes):
        if self.ws and self.is_connected:
            try:
                self.ws.send(pcm_bytes, opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception:
                pass

    def connect_ws(self):
        self.ws = websocket.WebSocketApp(
            SERVER_WS_URL,
            on_open=self.on_ws_open,
            on_message=self.on_ws_message,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close
        )
        ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        ws_thread.start()

    def setup_hotkeys(self):
        try:
            import keyboard
            logger.info("Setting up Push-to-Talk hotkey (Ctrl+Shift+Space)...")
            
            def toggle_barge_in():
                logger.info("Hotkey triggered: Barge-In (Flush Audio)")
                self.audio_pipe.flush_output()
                if self.ws and self.is_connected:
                    self.ws.send(json.dumps({"type": "interrupt"}))

            keyboard.add_hotkey('ctrl+shift+space', toggle_barge_in)
        except Exception as e:
            logger.warning(f"Global hotkey registration skipped ({e}). Press Ctrl+C in console to exit.")

    def run(self):
        self.connect_ws()
        self.setup_hotkeys()

        # Build system tray icon
        menu = pystray.Menu(
            pystray.MenuItem("Ambient Audio Agent (Active)", lambda: None, enabled=False),
            pystray.MenuItem("Flush Speaker Audio", lambda: self.audio_pipe.flush_output()),
            pystray.MenuItem("Exit Daemon", lambda: self.stop())
        )
        self.icon = pystray.Icon(
            "audiobot_tray",
            self.create_tray_icon_image("cyan"),
            "Ambient Audio Agent Daemon",
            menu
        )
        logger.info("Desktop Tray Daemon running. Double click tray icon or use menu options.")
        self.icon.run()

    def stop(self):
        self.audio_pipe.stop_capture()
        if self.ws:
            self.ws.close()
        if self.icon:
            self.icon.stop()

if __name__ == "__main__":
    app = DesktopDaemonApp()
    app.run()
