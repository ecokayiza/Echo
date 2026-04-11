from __future__ import annotations

import uuid
from typing import Any

import chromadb

from ..config import Config


class VectorDatabase:
    """Thin ChromaDB wrapper scoped to one logical database collection."""

    def __init__(self, collection_name: str = "rag_knowledge_base"):
        Config.DB_PATH.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(Config.DB_PATH))
        self.collection_name = collection_name
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ):
        """Upsert documents into the active collection."""
        resolved_ids = ids or [str(uuid.uuid4()) for _ in range(len(texts))]
        resolved_metadatas = metadatas or [{"source": "default"} for _ in range(len(texts))]
        self.collection.upsert(
            documents=texts,
            embeddings=embeddings,
            metadatas=resolved_metadatas,
            ids=resolved_ids,
        )

    def query_by_metadata(self, where: dict[str, Any], n_results: int | None = None):
        """Query documents by metadata only."""
        return self.collection.get(where=where, limit=n_results)

    def query_with_vector(self, query_embedding: list[float], n_results: int = 5, where: dict[str, Any] | None = None):
        """Query the collection with one embedding vector."""
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
        )

    def delete_documents(self, where: dict[str, Any]):
        """Delete documents matching a metadata filter."""
        results = self.collection.get(where=where)
        if results and results.get("ids"):
            self.collection.delete(where=where)

    def clear_collection(self):
        """Delete and recreate the active collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_collection(self):
        """Delete the active collection completely."""
        self.client.delete_collection(self.collection_name)

    def count(self) -> int:
        """Return the current collection size."""
        return int(self.collection.count())

    def peek(self, limit: int = 5):
        """Peek at a few documents in the collection."""
        return self.collection.peek(limit=limit)
