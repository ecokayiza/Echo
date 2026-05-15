from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .errors import EmbeddingError

DEFAULT_LOCAL_E5_MODEL = "intfloat/e5-base-v2"
LOCAL_EMBEDDING_SCHEME = "local://"

_MODEL_CACHE: dict[tuple[str, str | None], Any] = {}


class LocalE5Embedder:
    """Embed texts locally with sentence-transformers E5-compatible formatting."""

    @staticmethod
    def embed(
        data: str | list[str],
        *,
        model: str | None = None,
        input_type: str = "document",
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        texts = [data] if isinstance(data, str) else [str(item) for item in data]
        prepared = [_prepare_e5_text(text, input_type=input_type) for text in texts if str(text).strip()]
        if not prepared:
            return []

        resolved_model = (model or DEFAULT_LOCAL_E5_MODEL).strip() or DEFAULT_LOCAL_E5_MODEL
        encoder = _get_model(resolved_model)
        effective_batch_size = batch_size if batch_size and batch_size > 0 else 32
        embeddings: list[list[float]] = []
        completed = 0
        for batch in _batched(prepared, effective_batch_size):
            encoded = encoder.encode(
                batch,
                batch_size=effective_batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            embeddings.extend(_as_float_lists(encoded))
            completed += len(batch)
            if progress_callback is not None:
                progress_callback(completed, len(prepared))
        return embeddings

    @staticmethod
    def embed_documents(
        data: str | list[str],
        *,
        model: str | None = None,
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        return LocalE5Embedder.embed(
            data,
            model=model,
            input_type="document",
            batch_size=batch_size,
            progress_callback=progress_callback,
        )

    @staticmethod
    def embed_query(
        query: str,
        *,
        model: str | None = None,
        batch_size: int | None = None,
    ) -> list[float]:
        embeddings = LocalE5Embedder.embed(query, model=model, input_type="query", batch_size=batch_size)
        if not embeddings:
            raise EmbeddingError("Embedding model returned no vectors.")
        return embeddings[0]


def is_local_embedding_base_url(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith(LOCAL_EMBEDDING_SCHEME)


def _prepare_e5_text(text: str, *, input_type: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    prefix = "query: " if input_type == "query" else "passage: "
    return f"{prefix}{cleaned}"


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
        raise EmbeddingError(f"Failed to load local E5 embedding model '{model_name}': {_short_error(exc)}") from exc
    _MODEL_CACHE[key] = model
    return model


def _load_sentence_transformer_class():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingError(
            "Local E5 embeddings require optional dependencies. "
            "Install them with `python -m pip install -e \".[local-embeddings]\"`."
        ) from exc
    return SentenceTransformer


def _as_float_lists(encoded) -> list[list[float]]:
    values = encoded.tolist() if hasattr(encoded, "tolist") else encoded
    return [[float(value) for value in row] for row in values]


def _batched(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _short_error(exc: Exception) -> str:
    message = str(exc).strip().replace("\n", " ")
    return message[:500] or exc.__class__.__name__
