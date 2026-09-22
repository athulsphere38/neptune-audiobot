import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SECRET_KEY: str = "audiobot_super_secret_key"

    # Audio Engine Pipeline Settings
    SAMPLE_RATE: int = 16000
    CHANNELS: int = 1
    CHUNK_SIZE: int = 512
    VAD_THRESHOLD: float = 0.5
    SILENCE_DURATION_MS: int = 700

    # Provider Options
    STT_PROVIDER: str = "mock"  # mock, deepgram, groq
    TTS_PROVIDER: str = "edge_tts" # edge_tts, cartesia, elevenlabs, web
    LLM_PROVIDER: str = "mock"  # mock, openai, groq, anthropic, gemini

    # API Keys
    DEEPGRAM_API_KEY: str = ""
    CARTESIA_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./audiobot.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
