from __future__ import annotations

import math
import re


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


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


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2, strict=True))
