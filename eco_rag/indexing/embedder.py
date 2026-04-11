from __future__ import annotations

from openai import OpenAI

from ..chat.registry import EmbeddingModelSettings, get_active_embedding_model_settings, normalize_embedding_model_settings
from ..config import Config

DEFAULT_QUERY_INSTRUCTION = "Given a user query, retrieve relevant passages that answer the query."


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
        response = client.embeddings.create(model=resolved.model, input=prepared, dimensions=dimensions)
        return [item.embedding for item in response.data]

    @staticmethod
    def embed_documents(data: str | list[str], settings: EmbeddingModelSettings | dict | None = None) -> list[list[float]]:
        """Embed one or more documents without query instruction prefixes."""
        return OpenAICompatibleEmbedder.embed(data, settings, input_type="document")

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

HuggingFaceEmbedder = OpenAICompatibleEmbedder
