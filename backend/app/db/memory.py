import aiosqlite
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("audiobot.db")

class MemoryStore:
    def __init__(self, db_path: str = "audiobot.db"):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    active_device_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS device_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    device_name TEXT,
                    device_type TEXT,
                    event_type TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.commit()
        logger.info("SQLite Database initialized successfully.")

    async def add_message(self, session_id: str, role: str, content: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )
            await db.commit()

    async def get_recent_messages(self, session_id: str, limit: int = 20) -> List[Dict[str, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                # Return in chronological order
                return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    async def clear_session_messages(self, session_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            await db.commit()

    async def log_device_event(self, device_id: str, device_name: str, device_type: str, event_type: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO device_log (device_id, device_name, device_type, event_type) VALUES (?, ?, ?, ?)",
                (device_id, device_name, device_type, event_type)
            )
            await db.commit()

memory_store = MemoryStore()
