from __future__ import annotations

import pytest

from ubs_hackathon.embeddings import (
    FallbackEmbeddingModel,
    HuggingFaceEmbeddingModel,
    OpenAIEmbeddingModel,
    SimpleEmbeddingModel,
    create_embedding_model,
)


def test_create_embedding_model_falls_back_to_local_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("UBS_EMBEDDINGS_PROVIDER", raising=False)
    model = create_embedding_model()
    assert isinstance(model, FallbackEmbeddingModel)


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


def test_create_embedding_model_hf_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UBS_EMBEDDINGS_PROVIDER", "huggingface")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    model = create_embedding_model()
    assert isinstance(model, HuggingFaceEmbeddingModel)


def test_openai_embedding_model_embed_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    model = OpenAIEmbeddingModel(api_key="test-key")

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"data":[{"embedding":[0.1,0.2,0.3]}]}'

    monkeypatch.setattr("ubs_hackathon.embeddings.request.urlopen", lambda *args, **kwargs: _FakeResponse())
    embedding = model.embed("hello world")
    assert embedding == [0.1, 0.2, 0.3]


def test_hf_embedding_model_embed_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    model = HuggingFaceEmbeddingModel()

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            pass

        def read(self) -> bytes:
            return b"[[0.2,0.4,0.6],[0.4,0.6,0.8]]"

    monkeypatch.setattr("ubs_hackathon.embeddings.request.urlopen", lambda *args, **kwargs: _FakeResponse())
    embedding = model.embed("hello world")
    assert embedding == pytest.approx([0.3, 0.5, 0.7])


def test_fallback_model_switches_to_local_on_primary_error() -> None:
    class _BrokenModel:
        def embed(self, text: str) -> list[float]:
            raise RuntimeError("boom")

    fallback = SimpleEmbeddingModel(dims=8)
    model = FallbackEmbeddingModel(primary=_BrokenModel(), fallback=fallback)
    emb = model.embed("hello")
    assert len(emb) == 8
