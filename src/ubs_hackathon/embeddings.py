from __future__ import annotations

import json
import ipaddress
import math
import os
import re
from typing import Protocol
from urllib import error as urlerror
from urllib import parse
from urllib import request


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class EmbeddingModel(Protocol):
    def embed(self, text: str) -> list[float]:
        ...


def _validate_https_public_base_url(base_url: str) -> None:
    parsed = parse.urlparse(base_url)
    if parsed.scheme != "https":
        raise ValueError("Managed embeddings base URL must use https")
    hostname = (parsed.hostname or "").strip().lower()
    if hostname == "localhost":
        raise ValueError("Managed embeddings base URL must not target localhost")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip and (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    ):
        raise ValueError("Managed embeddings base URL must not target private/local IPs")


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
            raise ValueError(
                "OpenAI API key is required for managed embeddings. "
                "Set OPENAI_API_KEY or pass api_key explicitly."
            )
        _validate_https_public_base_url(base_url)
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
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Managed embedding request failed ({exc.code}): {detail}") from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"Managed embedding request failed: {exc.reason}") from exc

        parsed = json.loads(body)
        data = parsed.get("data")
        if data is None:
            raise RuntimeError("Managed embedding response missing data field")
        if (
            not isinstance(data, list)
            or not data
            or not isinstance(data[0], dict)
            or "embedding" not in data[0]
        ):
            raise RuntimeError("Managed embedding response missing embedding data")
        return [float(v) for v in data[0]["embedding"]]


class HuggingFaceEmbeddingModel:
    """Free online embeddings using Hugging Face Inference API."""

    def __init__(
        self,
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
        base_url: str = "https://api-inference.huggingface.co",
        api_token: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        _validate_https_public_base_url(base_url)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token or ""
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        payload = json.dumps({"inputs": text, "options": {"wait_for_model": True}}).encode("utf-8")
        model_path = parse.quote(self.model, safe="")
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        req = request.Request(
            f"{self.base_url}/pipeline/feature-extraction/{model_path}",
            data=payload,
            method="POST",
            headers=headers,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Hugging Face embedding request failed ({exc.code}): {detail}") from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"Hugging Face embedding request failed: {exc.reason}") from exc

        parsed_body = json.loads(body)
        if isinstance(parsed_body, dict) and parsed_body.get("error"):
            raise RuntimeError(f"Hugging Face embedding response error: {parsed_body['error']}")
        if not isinstance(parsed_body, list) or not parsed_body:
            raise RuntimeError("Hugging Face embedding response missing embedding data")

        if isinstance(parsed_body[0], (int, float)):
            return [float(v) for v in parsed_body]

        if isinstance(parsed_body[0], list):
            token_vectors = parsed_body
            dims = len(token_vectors[0]) if token_vectors[0] else 0
            if dims == 0:
                raise RuntimeError("Hugging Face embedding response contained empty token vectors")
            accum = [0.0] * dims
            count = 0
            for token_vec in token_vectors:
                if not isinstance(token_vec, list) or len(token_vec) != dims:
                    raise RuntimeError("Hugging Face embedding response has inconsistent token vector shapes")
                for i, value in enumerate(token_vec):
                    accum[i] += float(value)
                count += 1
            return [v / max(count, 1) for v in accum]

        raise RuntimeError("Hugging Face embedding response format is not supported")


class FallbackEmbeddingModel:
    """Try primary embeddings first, then permanently fallback to local model on error."""

    def __init__(self, primary: EmbeddingModel, fallback: EmbeddingModel) -> None:
        self._primary = primary
        self._fallback = fallback
        self._fallback_active = False

    def embed(self, text: str) -> list[float]:
        if self._fallback_active:
            return self._fallback.embed(text)
        try:
            return self._primary.embed(text)
        except RuntimeError:
            self._fallback_active = True
            return self._fallback.embed(text)


def create_embedding_model(
    provider: str | None = None,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    local_dims: int = 256,
) -> EmbeddingModel:
    resolved_provider = (provider or os.getenv("UBS_EMBEDDINGS_PROVIDER", "auto")).strip().lower()
    resolved_openai_api_key = api_key or os.getenv("OPENAI_API_KEY", "")
    resolved_hf_token = os.getenv("HF_API_TOKEN", "")
    resolved_hf_model = model or os.getenv(
        "UBS_HF_EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    resolved_hf_base_url = base_url or os.getenv(
        "UBS_HF_EMBEDDINGS_BASE_URL", "https://api-inference.huggingface.co"
    )
    if resolved_provider == "auto":
        if resolved_openai_api_key:
            return OpenAIEmbeddingModel(
                api_key=resolved_openai_api_key,
                model=os.getenv("UBS_EMBEDDINGS_MODEL", "text-embedding-3-small"),
                base_url=os.getenv("UBS_EMBEDDINGS_BASE_URL", "https://api.openai.com/v1"),
            )
        return FallbackEmbeddingModel(
            primary=HuggingFaceEmbeddingModel(
                model=resolved_hf_model,
                base_url=resolved_hf_base_url,
                api_token=resolved_hf_token,
            ),
            fallback=SimpleEmbeddingModel(dims=local_dims),
        )

    if resolved_provider in {"openai", "managed"}:
        if resolved_openai_api_key:
            return OpenAIEmbeddingModel(
                api_key=resolved_openai_api_key,
                model=model or os.getenv("UBS_EMBEDDINGS_MODEL", "text-embedding-3-small"),
                base_url=base_url or os.getenv("UBS_EMBEDDINGS_BASE_URL", "https://api.openai.com/v1"),
            )
        raise ValueError(
            "Managed embeddings provider selected but OPENAI_API_KEY is not set. "
            "Set OPENAI_API_KEY or change UBS_EMBEDDINGS_PROVIDER to 'local'."
        )
    if resolved_provider in {"huggingface", "hf", "huggingface_public", "free_online"}:
        return HuggingFaceEmbeddingModel(
            model=resolved_hf_model,
            base_url=resolved_hf_base_url,
            api_token=resolved_hf_token,
        )
    if resolved_provider == "local":
        return SimpleEmbeddingModel(dims=local_dims)
    return SimpleEmbeddingModel(dims=local_dims)


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2, strict=True))
