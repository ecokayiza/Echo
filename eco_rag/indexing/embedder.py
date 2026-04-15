from __future__ import annotations

import re
from collections.abc import Callable

from openai import BadRequestError, OpenAI

from ..chat.registry import EmbeddingModelSettings, get_active_embedding_model_settings, normalize_embedding_model_settings
from ..config import Config

DEFAULT_QUERY_INSTRUCTION = "Given a user query, retrieve relevant passages that answer the query."
MAX_BATCH_SIZE_PATTERN = re.compile(r"batch size is invalid, it should not be larger than (\d+)", re.IGNORECASE)


class OpenAICompatibleEmbedder:
    """Embed documents and queries through an OpenAI-compatible API."""

    @staticmethod
    def embed(
        data: str | list[str],
        settings: EmbeddingModelSettings | dict | None = None,
        *,
        input_type: str = "document",
        instruction: str | None = None,
        dimensions: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        texts = [data] if isinstance(data, str) else [str(item) for item in data]
        if not texts:
            return []

        resolved = normalize_embedding_model_settings(settings) if settings is not None else get_active_embedding_model_settings()
        prepared = [
            _prepare_input_text(text, input_type=input_type, instruction=instruction)
            for text in texts
            if str(text).strip()
        ]
        if not prepared:
            return []
        if not resolved.api_key:
            raise ValueError(f"Missing API key. Update '{Config.MODELS_PATH.name}' with a valid embedding model api_key.")
        if not resolved.model:
            raise ValueError(f"Missing embedding model name. Update '{Config.MODELS_PATH.name}' with a valid model.")
        if not resolved.base_url:
            raise ValueError(
                f"Missing embedding model base_url. Update '{Config.MODELS_PATH.name}' with a valid OpenAI-compatible endpoint."
            )

        client = OpenAI(api_key=resolved.api_key, base_url=resolved.base_url)
        request_kwargs = {"model": resolved.model, "input": prepared}
        if dimensions is not None:
            request_kwargs["dimensions"] = dimensions
        configured_batch_size = _configured_batch_size(resolved)
        if configured_batch_size is not None and len(prepared) > configured_batch_size:
            return _embed_in_batches(client, request_kwargs, configured_batch_size, progress_callback=progress_callback)

        try:
            embeddings = _extract_embeddings(client.embeddings.create(**request_kwargs))
            if progress_callback is not None:
                progress_callback(len(prepared), len(prepared))
            return embeddings
        except BadRequestError as exc:
            max_batch_size = _extract_max_batch_size(exc)
            if max_batch_size is None or len(prepared) <= 1:
                raise

        return _embed_in_batches(client, request_kwargs, max_batch_size, progress_callback=progress_callback)

    @staticmethod
    def embed_documents(
        data: str | list[str],
        settings: EmbeddingModelSettings | dict | None = None,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        """Embed one or more documents without query instruction prefixes."""
        return OpenAICompatibleEmbedder.embed(data, settings, input_type="document", progress_callback=progress_callback)

    @staticmethod
    def embed_query(
        query: str,
        settings: EmbeddingModelSettings | dict | None = None,
        *,
        instruction: str | None = None,
    ) -> list[float]:
        """Embed one retrieval query using the Qwen query format when needed."""
        embeddings = OpenAICompatibleEmbedder.embed(
            query,
            settings,
            input_type="query",
            instruction=instruction or DEFAULT_QUERY_INSTRUCTION,
        )
        if not embeddings:
            raise ValueError("Embedding model returned no vectors.")
        return embeddings[0]


def _prepare_input_text(text: str, *, input_type: str, instruction: str | None) -> str:
    """Format one text payload before sending it to the embedding model."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    if input_type == "query":
        task = (instruction or DEFAULT_QUERY_INSTRUCTION).strip()
        return f"Instruct: {task}\nQuery: {cleaned}"
    return cleaned


def _extract_embeddings(response) -> list[list[float]]:
    return [item.embedding for item in response.data]


def _embed_in_batches(
    client: OpenAI,
    request_kwargs: dict,
    max_batch_size: int,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    embeddings: list[list[float]] = []
    total = len(request_kwargs["input"])
    completed = 0
    for batch in _batched(request_kwargs["input"], max_batch_size):
        batch_kwargs = {**request_kwargs, "input": batch}
        embeddings.extend(_extract_embeddings(client.embeddings.create(**batch_kwargs)))
        completed += len(batch)
        if progress_callback is not None:
            progress_callback(completed, total)
    return embeddings


def _configured_batch_size(settings: EmbeddingModelSettings) -> int | None:
    return settings.batch_size if settings.batch_size and settings.batch_size > 0 else None


def _extract_max_batch_size(exc: BadRequestError) -> int | None:
    message = str(exc)
    match = MAX_BATCH_SIZE_PATTERN.search(message)
    if match is None:
        return None
    size = int(match.group(1))
    return size if size > 0 else None


def _batched(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]

HuggingFaceEmbedder = OpenAICompatibleEmbedder
