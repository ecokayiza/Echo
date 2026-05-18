from __future__ import annotations

import argparse
import os
from collections.abc import Iterable
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DEFAULT_LOCAL_E5_MODEL = "intfloat/e5-base-v2"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8092

_MODEL_CACHE: dict[tuple[str, str | None], Any] = {}


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = DEFAULT_LOCAL_E5_MODEL
    encoding_format: str | None = None


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: list[float]


class EmbeddingUsage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingResponse(BaseModel):
    object: str = "list"
    model: str
    data: list[EmbeddingData] = Field(default_factory=list)
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)


def create_app(default_model: str = DEFAULT_LOCAL_E5_MODEL, default_batch_size: int = 32) -> FastAPI:
    app = FastAPI(
        title="Echo Local E5 Embedding Service",
        version="0.1.0",
        description="Manually launched OpenAI-compatible embedding endpoint backed by sentence-transformers.",
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "model": default_model}

    @app.post("/v1/embeddings", response_model=EmbeddingResponse)
    def embeddings(payload: EmbeddingRequest):
        model_name = (payload.model or default_model).strip() or default_model
        texts = _input_texts(payload.input)
        if not texts:
            raise HTTPException(status_code=400, detail="Embedding input cannot be empty.")
        try:
            vectors = embed_texts(texts, model_name=model_name, batch_size=default_batch_size)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return EmbeddingResponse(
            model=model_name,
            data=[EmbeddingData(index=index, embedding=vector) for index, vector in enumerate(vectors)],
            usage=EmbeddingUsage(total_tokens=sum(_rough_token_count(text) for text in texts)),
        )

    return app


def embed_texts(texts: list[str], *, model_name: str = DEFAULT_LOCAL_E5_MODEL, batch_size: int = 32) -> list[list[float]]:
    encoder = _get_model(model_name)
    vectors: list[list[float]] = []
    effective_batch_size = batch_size if batch_size > 0 else 32
    for batch in _batched(texts, effective_batch_size):
        encoded = encoder.encode(
            batch,
            batch_size=effective_batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors.extend(_as_float_lists(encoded))
    return vectors


def _get_model(model_name: str):
    device = os.getenv("ECHO_LOCAL_EMBEDDING_DEVICE") or None
    key = (model_name, device)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    sentence_transformer = _load_sentence_transformer_class()
    try:
        model = sentence_transformer(model_name, device=device) if device else sentence_transformer(model_name)
    except Exception as exc:
        raise RuntimeError(f"Failed to load local E5 embedding model '{model_name}': {_short_error(exc)}") from exc
    _MODEL_CACHE[key] = model
    return model


def _load_sentence_transformer_class():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Local E5 embedding service requires optional dependencies. "
            "Install them with `python -m pip install -e \".[local-embeddings]\"`."
        ) from exc
    return SentenceTransformer


def _input_texts(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value if str(item).strip()]


def _as_float_lists(encoded) -> list[list[float]]:
    values = encoded.tolist() if hasattr(encoded, "tolist") else encoded
    return [[float(value) for value in row] for row in values]


def _batched(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _rough_token_count(text: str) -> int:
    return max(1, len(text.split()))


def _short_error(exc: Exception) -> str:
    message = str(exc).strip().replace("\n", " ")
    return message[:500] or exc.__class__.__name__


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Echo's local E5 OpenAI-compatible embedding service.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--model", default=DEFAULT_LOCAL_E5_MODEL)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    import uvicorn

    uvicorn.run(
        create_app(default_model=args.model, default_batch_size=args.batch_size),
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
