from __future__ import annotations

import json
import math
import os
import re
from typing import Protocol
from urllib import error as urlerror
from urllib import request


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class EmbeddingModel(Protocol):
    def embed(self, text: str) -> list[float]:
        ...


class SimpleEmbeddingModel:
    """Small local embedding model for hackathon demos."""

    def __init__(self, dims: int = 256) -> None:
        self.dims = dims

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        tokens = TOKEN_RE.findall(text.lower())
        if not tokens:
            return vec

        for token in tokens:
            vec[hash(token) % self.dims] += 1.0

        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


class OpenAIEmbeddingModel:
    """Managed embedding model backed by OpenAI embeddings API."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required for managed embeddings")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model, "input": text}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/embeddings",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:  # nosec B310
                body = resp.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Managed embedding request failed ({exc.code}): {detail}") from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"Managed embedding request failed: {exc.reason}") from exc

        parsed = json.loads(body)
        data = parsed.get("data") or []
        if not data or "embedding" not in data[0]:
            raise RuntimeError("Managed embedding response missing embedding data")
        return [float(v) for v in data[0]["embedding"]]


def create_embedding_model(
    provider: str | None = None,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    local_dims: int = 256,
) -> EmbeddingModel:
    resolved_provider = (provider or os.getenv("UBS_EMBEDDINGS_PROVIDER", "auto")).strip().lower()
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY", "")
    if resolved_provider == "auto":
        resolved_provider = "openai" if resolved_api_key else "local"

    if resolved_provider in {"openai", "managed"}:
        if resolved_api_key:
            return OpenAIEmbeddingModel(
                api_key=resolved_api_key,
                model=model or os.getenv("UBS_EMBEDDINGS_MODEL", "text-embedding-3-small"),
                base_url=base_url or os.getenv("UBS_EMBEDDINGS_BASE_URL", "https://api.openai.com/v1"),
            )
        raise ValueError("Managed embeddings provider selected but OPENAI_API_KEY is not set")
    return SimpleEmbeddingModel(dims=local_dims)


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2, strict=True))
