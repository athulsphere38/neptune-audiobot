import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.config import settings
from app.db.memory import memory_store
from app.api.rest import router as rest_router
from app.api.audio_ws import router as ws_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("audiobot.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Ambient Audio Agent Backend Server...")
    await memory_store.init_db()
    yield
    logger.info("Shutting down Ambient Audio Agent Backend Server...")

app = FastAPI(
    title="Ambient Audio Agent Hub",
    version="1.0.0",
    description="Decoupled, event-driven streaming server for cross-device ambient voice agents.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_router)
app.include_router(ws_router)

if __name__ == "__main__":
    logger.info(f"Starting server on http://{settings.HOST}:{settings.PORT}")
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)
