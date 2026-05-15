from __future__ import annotations

import re
from collections.abc import Callable

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from echo.chat.registry import EmbeddingModelSettings, get_active_embedding_model_settings, normalize_embedding_model_settings
from echo.settings import Config
from .errors import EmbeddingError
from .local_e5_embedder import DEFAULT_LOCAL_E5_MODEL, LocalE5Embedder, is_local_embedding_base_url

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

        try:
            resolved = normalize_embedding_model_settings(settings) if settings is not None else get_active_embedding_model_settings()
        except ValueError as exc:
            raise EmbeddingError(str(exc)) from exc

        if is_local_embedding_base_url(resolved.base_url):
            local_model = resolved.model
            if not local_model or local_model == Config.DEFAULT_EMBEDDING_MODEL:
                local_model = DEFAULT_LOCAL_E5_MODEL
            return LocalE5Embedder.embed(
                texts,
                model=local_model,
                input_type=input_type,
                batch_size=resolved.batch_size,
                progress_callback=progress_callback,
            )

        prepared = [
            _prepare_input_text(text, input_type=input_type, instruction=instruction)
            for text in texts
            if str(text).strip()
        ]
        if not prepared:
            return []
        if not resolved.api_key:
            raise EmbeddingError(f"Missing API key. Update '{Config.MODELS_PATH.name}' with a valid embedding model api_key.")
        if not resolved.model:
            raise EmbeddingError(f"Missing embedding model name. Update '{Config.MODELS_PATH.name}' with a valid model.")
        if not resolved.base_url:
            raise EmbeddingError(
                f"Missing embedding model base_url. Update '{Config.MODELS_PATH.name}' with a valid OpenAI-compatible endpoint."
            )

        client = OpenAI(api_key=resolved.api_key, base_url=resolved.base_url)
        request_kwargs = {"model": resolved.model, "input": prepared}
        if dimensions is not None:
            request_kwargs["dimensions"] = dimensions
        configured_batch_size = _configured_batch_size(resolved)
        try:
            if configured_batch_size is not None and len(prepared) > configured_batch_size:
                return _validate_embeddings(
                    _embed_in_batches(client, request_kwargs, configured_batch_size, progress_callback=progress_callback),
                    len(prepared),
                )

            try:
                embeddings = _extract_embeddings(client.embeddings.create(**request_kwargs))
                if progress_callback is not None:
                    progress_callback(len(prepared), len(prepared))
                return _validate_embeddings(embeddings, len(prepared))
            except BadRequestError as exc:
                max_batch_size = _extract_max_batch_size(exc)
                if max_batch_size is None or len(prepared) <= 1:
                    raise

            return _validate_embeddings(
                _embed_in_batches(client, request_kwargs, max_batch_size, progress_callback=progress_callback),
                len(prepared),
            )
        except OpenAIError as exc:
            raise _embedding_provider_error(exc, resolved) from exc
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"Unexpected embedding failure: {_short_error(exc)}") from exc

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


def _validate_embeddings(embeddings: list[list[float]], expected_count: int) -> list[list[float]]:
    if len(embeddings) != expected_count:
        raise EmbeddingError(f"Embedding provider returned {len(embeddings)} vector(s) for {expected_count} input chunk(s).")
    return embeddings


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


def _embedding_provider_error(exc: OpenAIError, settings: EmbeddingModelSettings) -> EmbeddingError:
    provider = f"'{settings.name}' ({settings.model} at {settings.base_url})"
    if isinstance(exc, AuthenticationError):
        return EmbeddingError(f"Embedding provider rejected the API key for {provider}.")
    if isinstance(exc, PermissionDeniedError):
        return EmbeddingError(f"Embedding provider denied access to {provider}.")
    if isinstance(exc, NotFoundError):
        return EmbeddingError(f"Embedding model or endpoint was not found for {provider}.")
    if isinstance(exc, RateLimitError):
        return EmbeddingError(f"Embedding provider rate-limited {provider}. Try again later or lower batch_size.")
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return EmbeddingError(f"Embedding provider is unavailable at {settings.base_url}. Confirm the service is running and reachable.")
    if isinstance(exc, BadRequestError):
        return EmbeddingError(f"Embedding request was rejected by {provider}: {_short_error(exc)}")
    if isinstance(exc, APIStatusError):
        return EmbeddingError(f"Embedding provider returned HTTP {exc.status_code} for {provider}: {_short_error(exc)}")
    return EmbeddingError(f"Embedding request failed for {provider}: {_short_error(exc)}")


def _short_error(exc: Exception) -> str:
    message = str(exc).strip().replace("\n", " ")
    return message[:500] or exc.__class__.__name__

HuggingFaceEmbedder = OpenAICompatibleEmbedder
