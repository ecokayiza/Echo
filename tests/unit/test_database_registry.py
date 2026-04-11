import json
import tempfile
import unittest
from unittest.mock import patch

from eco_rag.chat.registry import embedding_model_key, resolve_embedding_model_settings
from eco_rag.config import Config
from eco_rag.indexing.database_registry import (
    create_database_settings,
    get_active_database_settings,
    list_database_settings,
    resolve_database_embedding_settings,
    select_database_settings,
)
from eco_rag.tools.database_search import database_search


class DatabaseRegistryTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._previous_models_path = Config.MODELS_PATH
        self._previous_databases_path = Config.DATABASES_PATH
        self._previous_db_path = Config.DB_PATH
        Config.MODELS_PATH = type(Config.MODELS_PATH)(self._temp_dir.name) / "models.json"
        Config.DATABASES_PATH = type(Config.DATABASES_PATH)(self._temp_dir.name) / "databases.json"
        Config.DB_PATH = type(Config.DB_PATH)(self._temp_dir.name) / "db"
        Config.MODELS_PATH.write_text(
            json.dumps(
                {
                    "active_chat_model": "Test Chat",
                    "active_embedding_model": "Local Qwen3 Embedding",
                    "chat_models": [{"name": "Test Chat", "model": "chat-model", "api_key": "chat-key", "base_url": "https://example.test"}],
                    "embedding_models": [
                        {
                            "name": "Local Qwen3 Embedding",
                            "model": "Qwen/Qwen3-Embedding-0.6B",
                            "api_key": "local-embedding-service",
                            "base_url": "http://127.0.0.1:8091/v1",
                        },
                        {
                            "name": "External Embedding",
                            "model": "text-embedding-3-small",
                            "api_key": "embedding-key",
                            "base_url": "https://api.openai.com/v1",
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        Config.MODELS_PATH = self._previous_models_path
        Config.DATABASES_PATH = self._previous_databases_path
        Config.DB_PATH = self._previous_db_path
        self._temp_dir.cleanup()

    def test_databases_are_paired_to_one_embedding_model(self):
        created = create_database_settings(name="External DB", embedding_model_name="External Embedding", select=True)
        database = next(item for item in created.databases if item.name == "External DB")
        embedding = resolve_database_embedding_settings(database)

        self.assertEqual(embedding.name, "External Embedding")
        self.assertEqual(database.embedding_model_key, embedding_model_key(embedding))

        select_database_settings(database.id)
        self.assertEqual(get_active_database_settings().id, database.id)
        self.assertEqual(list_database_settings().active_database_id, database.id)

    def test_database_search_uses_the_paired_embedding_model(self):
        create_database_settings(name="External DB", embedding_model_name="External Embedding", select=True)

        class FakeVectorDatabase:
            def __init__(self, collection_name: str):
                self.collection_name = collection_name

            def query_with_vector(self, query_embedding, n_results=5, where=None):
                return {
                    "ids": [["doc-1"]],
                    "documents": [["chunk"]],
                    "metadatas": [[{"source_name": "doc.md", "source_type": "md", "file_path": "doc.md", "chunk_index": 0}]],
                    "distances": [[0.1]],
                }

        with patch("eco_rag.indexing.embedder.OpenAICompatibleEmbedder.embed_query", return_value=[0.1, 0.2]) as embed_query:
            with patch("eco_rag.indexing.vector_database.VectorDatabase", FakeVectorDatabase):
                result = database_search.invoke({"query": "hello", "top_k": 2})

        self.assertEqual(result["type"], "context")
        self.assertEqual(result["items"][0]["database_name"], "External DB")
        used_settings = embed_query.call_args.kwargs["settings"]
        self.assertEqual(resolve_embedding_model_settings(name=used_settings.name).name, "External Embedding")


if __name__ == "__main__":
    unittest.main()
