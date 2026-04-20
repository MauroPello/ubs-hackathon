from __future__ import annotations

import pytest

from ubs_hackathon.embeddings import OpenAIEmbeddingModel, SimpleEmbeddingModel, create_embedding_model


def test_create_embedding_model_falls_back_to_local_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("UBS_EMBEDDINGS_PROVIDER", raising=False)
    model = create_embedding_model()
    assert isinstance(model, SimpleEmbeddingModel)


def test_create_embedding_model_requires_key_when_openai_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        create_embedding_model(provider="openai")


def test_create_embedding_model_requires_key_when_openai_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UBS_EMBEDDINGS_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        create_embedding_model()


def test_create_embedding_model_openai_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UBS_EMBEDDINGS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    model = create_embedding_model()
    assert isinstance(model, OpenAIEmbeddingModel)
