import asyncio
import json
import logging
import httpx
from typing import AsyncGenerator, List, Dict, Any
from app.core.config import settings

logger = logging.getLogger("audiobot.llm")

SYSTEM_PROMPT = """You are an ultra-low latency, ambient audio AI agent operating across web, desktop, and mobile devices.
Your responses should be concise, conversational, intelligent, and optimized for spoken text-to-speech output (avoid markdown code blocks, complex bullet points, or unpronounceable formatting).
Keep answers direct, informative, and engaging (1-3 spoken sentences maximum).
Current system state: Sync Engine online, WebSocket duplex streaming active.
"""

class BaseLLMService:
    async def stream_completion(
        self,
        prompt: str,
        chat_history: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError

class MockLLMService(BaseLLMService):
    async def stream_completion(
        self,
        prompt: str,
        chat_history: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        response_text = f"I heard you ask: '{prompt}'. The cross-device audio pipeline is synchronized and operating at ultra-low latency."
        words = response_text.split(" ")
        for word in words:
            yield word + " "
            await asyncio.sleep(0.04)

class OllamaLLMService(BaseLLMService):
    """
    Local LLM Service using local Ollama instance (/api/chat streaming endpoint).
    """
    def __init__(self, host: str = "http://localhost:11434", model_name: str = "llama3.2"):
        self.host = host.rstrip('/')
        self.model_name = model_name

    async def stream_completion(
        self,
        prompt: str,
        chat_history: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in chat_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})

        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.7,
                "num_predict": 250
            }
        }

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("POST", url, json=payload, timeout=30.0) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        err_text = err_body.decode('utf-8', errors='ignore')
                        logger.error(f"Ollama API Error {response.status_code}: {err_text}")
                        yield f"Ollama service error ({response.status_code}): {err_text[:100]}"
                        return

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("message", {}).get("content", "")
                            if chunk:
                                yield chunk
                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            pass
            except (httpx.ConnectError, httpx.ConnectTimeout):
                logger.error(f"Could not connect to Ollama server at {self.host}")
                yield f"Ollama service unavailable at {self.host}. Please verify Ollama is running and model '{self.model_name}' is loaded."
            except Exception as e:
                logger.error(f"Ollama Streaming Exception: {e}")
                yield f"Ollama service error: {str(e)}"

class OpenAICompatibleLLMService(BaseLLMService):
    def __init__(self, api_key: str, api_base: str, model_name: str):
        self.api_key = api_key
        self.api_base = api_base
        self.model_name = model_name

    async def stream_completion(
        self,
        prompt: str,
        chat_history: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        if not self.api_key:
            logger.warning("LLM API key missing, using fallback response.")
            yield "LLM API key missing."
            return

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in chat_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "max_tokens": 250,
            "temperature": 0.7
        }

        url = f"{self.api_base.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("POST", url, headers=headers, json=payload, timeout=15.0) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        logger.error(f"LLM API Error {response.status_code}: {err_body.decode()}")
                        yield "I encountered an error connecting to the intelligence server."
                        return

                    async for line in response.aiter_lines():
                        if line.startswith("data: ") and not line.endswith("[DONE]"):
                            try:
                                json_str = line[6:]
                                data = json.loads(json_str)
                                delta = data['choices'][0]['delta']
                                content = delta.get('content', '')
                                if content:
                                    yield content
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"LLM Streaming Exception: {e}")
                yield f"System pipeline error: {str(e)}"

def get_llm_service() -> BaseLLMService:
    if settings.DEMO_MODE:
        return MockLLMService()

    provider = settings.LLM_PROVIDER.lower()
    if provider == "ollama":
        return OllamaLLMService(host=settings.OLLAMA_HOST, model_name=settings.OLLAMA_MODEL)
    elif provider == "openai" and settings.OPENAI_API_KEY:
        return OpenAICompatibleLLMService(settings.OPENAI_API_KEY, "https://api.openai.com/v1", "gpt-4o")
    elif provider == "groq" and settings.GROQ_API_KEY:
        return OpenAICompatibleLLMService(settings.GROQ_API_KEY, "https://api.groq.com/openai/v1", "llama-3.1-70b-versatile")
    elif provider == "gemini" and settings.GEMINI_API_KEY:
        return OpenAICompatibleLLMService(settings.GEMINI_API_KEY, "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-1.5-flash")
    elif provider == "mock":
        return MockLLMService()

    return OllamaLLMService(host=settings.OLLAMA_HOST, model_name=settings.OLLAMA_MODEL)
