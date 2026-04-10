from functools import lru_cache

from openai import OpenAI
from tqdm import tqdm

from ..chat.registry import EmbeddingModelSettings, get_active_embedding_model_settings, normalize_embedding_model_settings
from ..config import Config


class OpenAICompatibleEmbedder:
    @staticmethod
    def embed(
        data,
        settings: EmbeddingModelSettings | dict | None = None,
        max_retries: int = 3,
    ):
        """
        Embed chunks to vectors using the active embedding model in models.json.
        data: a single text (str) or an iterable of text chunks (e.g. list[str])
        """
        if isinstance(data, str):
            data = [data]

        resolved = normalize_embedding_model_settings(settings) if settings is not None else get_active_embedding_model_settings()
        embeddings = []
        for chunk in tqdm(data, desc="Embedding chunks"):
            try:
                embedding = OpenAICompatibleEmbedder._embed_single_text(
                    chunk,
                    resolved.model,
                    resolved.api_key,
                    resolved.base_url,
                    max_retries,
                )
                if embedding is not None:
                    embeddings.append(embedding)
            except Exception as exc:
                print(f"Error embedding chunk: {chunk[:30]}... Error: {exc}")
        return embeddings

    @staticmethod
    @lru_cache(maxsize=2048)
    def _embed_single_text(
        text: str,
        model: str | None,
        api_key: str | None,
        base_url: str | None,
        max_retries: int = 3,
    ):
        """
        Embed a single text chunk to a vector with retry.
        """
        if not api_key:
            raise ValueError(f"Missing API key. Update '{Config.MODELS_PATH.name}' with a valid embedding model api_key.")
        if not model:
            raise ValueError(f"Missing embedding model name. Update '{Config.MODELS_PATH.name}' with a valid model.")

        client = OpenAI(api_key=api_key, base_url=base_url)
        retry_count = 0

        while retry_count < max_retries:
            response = client.embeddings.create(model=model, input=[text])
            if response.data:
                return response.data[0].embedding
            retry_count += 1

        print(f"Failed to embed chunk after retries: {text[:30]}...")
        return None


if __name__ == "__main__":
    file_path = Config.TEST_FILE_PATH

    import os

    from .chunker import ChunkerFactory
    from .loader import DataLoaderFactory

    data = DataLoaderFactory.load(file_path)
    _, ext = os.path.splitext(file_path)
    chunks = ChunkerFactory.chunk(data, ext)
    embeddings = OpenAICompatibleEmbedder.embed(chunks)


HuggingFaceEmbedder = OpenAICompatibleEmbedder
