"""Embedding providers for semantic memory retrieval.

Provider format:
    "openai:text-embedding-3-small"
    "fastembed:bge-small-en-v1.5"
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional
from config import logger


class OpenAIEmbedding():
    def __init__(self, model: str = "text-embedding-3-small", base_url: Optional[str] = None) -> None:
        self.model = model
        self.base_url = base_url
        self._client: Any = None

    def init(self) -> None:
        try:
            from openai import AsyncOpenAI  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError("Install optional dependency 'openai' for embeddings") from e

        self._client = AsyncOpenAI(base_url=self.base_url)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self.model,
            input=text,
        )
        return list(response.data[0].embedding)


class FastEmbedEmbedding():
    _ALIASES = {
        "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
    }

    def __init__(self, model: str = "bge-small-en-v1.5") -> None:
        self.model = model
        self._model: Any = None

    def init(self) -> None:
        try:
            from fastembed import TextEmbedding  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError("Install optional dependency 'fastembed' for local embeddings") from e

        model_name = self._ALIASES.get(self.model, self.model)
        self._model = TextEmbedding(model_name=model_name)

    async def embed(self, text: str) -> list[float]:
        def _run() -> list[float]:
            output = next(iter(self._model.embed([text])))
            return output.tolist() if hasattr(output, "tolist") else [float(v) for v in output]

        return await asyncio.to_thread(_run)


class EmbeddingEngine:
    """Provider-agnostic embedding facade with safe degradation."""

    def __init__(self, embedding_provider: str, base_url: Optional[str] = None) -> None:
        self.embedding_provider = embedding_provider or "fastembed:bge-small-en-v1.5"
        self.base_url = base_url

        provider, model = self._parse_provider_spec(self.embedding_provider)
        self.provider = provider
        self.model = model

        self._enabled = False
        self._dimension: Optional[int] = None
        self._embedding: Optional[OpenAIEmbedding | FastEmbedEmbedding] = None

    @staticmethod
    def _parse_provider_spec(provider_spec: str) -> tuple[str, str]:
        if ":" not in provider_spec:
            raise ValueError(
                "Embedding provider must use format 'provider:model', "
                f"got '{provider_spec}'"
            )
        provider, model = provider_spec.split(":", 1)
        return provider.strip().lower(), model.strip()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def dimension(self) -> Optional[int]:
        return self._dimension

    def provider_id(self) -> str:
        return self.provider

    def model_id(self) -> str:
        return self.model

    def init_model(self) -> None:
        """Initialize provider client/model. Never raises; disables on failure."""
        try:
            if self.provider == "openai":
                self._embedding = OpenAIEmbedding(self.model, base_url=self.base_url)
            elif self.provider == "fastembed":
                self._embedding = FastEmbedEmbedding(self.model)
            else:
                raise ValueError(f"Unsupported embedding provider: {self.provider}")

            self._embedding.init()

            self._enabled = True
            logger.debug(
                f"EmbeddingEngine: initialized {self.provider}:{self.model}"
            )
        except Exception as e:
            self._enabled = False
            logger.warning(f"EmbeddingEngine {self.provider} error - {e}")

    async def embed_one(self, text: str) -> Optional[list[float]]:
        """Return embedding vector for text, or None when disabled/failing."""
        if not self._enabled:
            return None

        if not text or not text.strip():
            logger.warning("EmbeddingEngine: empty text, skipping embedding")
            return None

        try:
            if self._embedding is None:
                return None

            vector = await self._embedding.embed(text)
            if self._dimension is None:
                self._dimension = len(vector)
            return vector
        except Exception as e:
            logger.warning(f"EmbeddingEngine: {self.provider} embedding failed - {e}")
            return None
