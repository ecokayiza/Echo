from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


@tool
def database_search(query: str, top_k: int = 4) -> dict[str, Any]:
    """Search the local Eco_RAG vector database for semantically related chunks."""
    cleaned = " ".join((query or "").strip().split())
    limit = max(1, min(int(top_k or 4), 8))
    if not cleaned:
        return {
            "type": "context",
            "skill_name": "database_search",
            "items": [],
            "query": cleaned,
            "error": "Query cannot be empty.",
        }

    try:
        from ..domain.schema import RAGRecord
        from ..indexing.embedder import OpenAICompatibleEmbedder
        from ..indexing.vector_database import VectorDatabase

        embeddings = OpenAICompatibleEmbedder.embed(cleaned)
        if not embeddings:
            return {
                "type": "context",
                "skill_name": "database_search",
                "items": [],
                "query": cleaned,
                "error": "Embedding model returned no vectors.",
            }

        results = VectorDatabase().query_with_vector(embeddings[0], n_results=limit)
        records = RAGRecord.get_records_from_results(results)
        items = [
            {
                "title": record.metadata.source_name,
                "content": record.document,
                "source_type": record.metadata.source_type,
                "file_path": record.metadata.attributes.file_path,
                "url": record.metadata.attributes.url,
                "distance": record.distance,
            }
            for record in records
        ]
        return {
            "type": "context",
            "skill_name": "database_search",
            "items": items,
            "query": cleaned,
            "count": len(items),
        }
    except Exception as exc:
        return {
            "type": "context",
            "skill_name": "database_search",
            "items": [],
            "query": cleaned,
            "error": str(exc),
        }
