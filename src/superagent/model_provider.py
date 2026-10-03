from __future__ import annotations

import os
from typing import Protocol

import httpx


class ModelProvider(Protocol):
    async def complete(self, messages: list[dict]) -> str: ...


class OfflineProvider:
    async def complete(self, messages: list[dict]) -> str:
        return "Offline provider produced a bounded synthetic analysis."


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def complete(self, messages: list[dict]) -> str:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "temperature": 0},
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]


def provider_from_environment() -> ModelProvider:
    if os.getenv("AGENT_MODEL_PROVIDER") == "openai-compatible":
        return OpenAICompatibleProvider(
            os.environ["AGENT_MODEL_BASE_URL"], os.environ["AGENT_MODEL_API_KEY"], os.environ["AGENT_MODEL_NAME"]
        )
    return OfflineProvider()
