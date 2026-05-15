from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb

from echo.settings import Config
from .vector_backends import normalize_vector_backend


class VectorDatabase:
    """Vector database wrapper scoped to one logical database collection."""

    def __init__(self, collection_name: str = "rag_knowledge_base", backend: str = "chroma"):
        self.collection_name = collection_name
        self.backend = normalize_vector_backend(backend)
        if self.backend == "chroma":
            self._store = _ChromaVectorStore(collection_name)
            self.client = self._store.client
            self.collection = self._store.collection
        else:
            self._store = _FaissVectorStore(collection_name)
            self.client = None
            self.collection = None

    def add_documents(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ):
        """Upsert documents into the active collection."""
        return self._store.add_documents(texts=texts, embeddings=embeddings, metadatas=metadatas, ids=ids)

    def query_by_metadata(self, where: dict[str, Any], n_results: int | None = None):
        """Query documents by metadata only."""
        return self._store.query_by_metadata(where=where, n_results=n_results)

    def query_with_vector(self, query_embedding: list[float], n_results: int = 5, where: dict[str, Any] | None = None):
        """Query the collection with one embedding vector."""
        return self._store.query_with_vector(query_embedding=query_embedding, n_results=n_results, where=where)

    def get_by_ids(self, ids: list[str]):
        """Return stored records for the requested document ids."""
        return self._store.get_by_ids(ids=ids)

    def delete_documents(self, where: dict[str, Any]):
        """Delete documents matching a metadata filter."""
        return self._store.delete_documents(where=where)

    def update_document_metadata(self, where: dict[str, Any], updates: dict[str, Any]) -> bool:
        """Update metadata for all documents matching a metadata filter."""
        return self._store.update_document_metadata(where=where, updates=updates)

    def clear_collection(self):
        """Delete and recreate the active collection."""
        return self._store.clear_collection()

    def delete_collection(self):
        """Delete the active collection completely."""
        return self._store.delete_collection()

    def count(self) -> int:
        """Return the current collection size (number of chunks)."""
        return self._store.count()

    def file_count(self) -> int:
        """Return the number of unique files/documents in the collection."""
        return self._store.file_count()

    def peek(self, limit: int = 5):
        """Peek at a few documents in the collection."""
        return self._store.peek(limit=limit)

    def list_document_summaries(self):
        """Return one summary per stored source document."""
        return self._store.list_document_summaries()


class _ChromaVectorStore:
    def __init__(self, collection_name: str):
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
        resolved_ids = ids or [str(uuid.uuid4()) for _ in range(len(texts))]
        resolved_metadatas = metadatas or [{"source": "default"} for _ in range(len(texts))]
        self.collection.upsert(
            documents=texts,
            embeddings=embeddings,
            metadatas=resolved_metadatas,
            ids=resolved_ids,
        )

    def query_by_metadata(self, where: dict[str, Any], n_results: int | None = None):
        return self.collection.get(where=where, limit=n_results)

    def query_with_vector(self, query_embedding: list[float], n_results: int = 5, where: dict[str, Any] | None = None):
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
        )

    def get_by_ids(self, ids: list[str]):
        if not ids:
            return _flat_results()
        return self.collection.get(ids=ids)

    def delete_documents(self, where: dict[str, Any]):
        results = self.collection.get(where=where)
        if results and results.get("ids"):
            self.collection.delete(where=where)

    def update_document_metadata(self, where: dict[str, Any], updates: dict[str, Any]) -> bool:
        results = self.collection.get(where=where)
        ids = results.get("ids") or []
        metadatas = results.get("metadatas") or []
        if not ids:
            return False

        next_metadatas = []
        for metadata in metadatas:
            current = metadata if isinstance(metadata, dict) else {}
            next_metadatas.append({**current, **updates})

        self.collection.update(ids=ids, metadatas=next_metadatas)
        return True

    def clear_collection(self):
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_collection(self):
        self.client.delete_collection(self.collection_name)

    def count(self) -> int:
        return int(self.collection.count())

    def file_count(self) -> int:
        results = self.collection.get(include=["metadatas"])
        return len(_document_summary_map(results.get("metadatas") or []))

    def peek(self, limit: int = 5):
        return self.collection.peek(limit=limit)

    def list_document_summaries(self):
        results = self.collection.get()
        return _sorted_document_summaries(results.get("metadatas") or [])


@dataclass
class _FaissRecord:
    id: str
    int_id: int
    document: str
    metadata: dict[str, Any]


class _FaissVectorStore:
    _VERSION = 1
    _METRIC = "cosine"

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.path = Config.DB_PATH / "faiss" / collection_name
        self.records_path = self.path / "records.json"
        self.index_path = self.path / "index.faiss"
        self._faiss, self._np = _load_faiss_dependencies()
        self._lock = _faiss_collection_lock(self.path)
        self.path.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._load()

    def add_documents(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ):
        _validate_add_payload(texts=texts, embeddings=embeddings, metadatas=metadatas, ids=ids)
        if not texts:
            return

        resolved_ids = ids or [str(uuid.uuid4()) for _ in range(len(texts))]
        resolved_metadatas = metadatas or [{"source": "default"} for _ in range(len(texts))]

        with self._lock:
            matrix = self._normalized_matrix(embeddings, expected_dimension=self._dimension)
            if self._dimension is None:
                self._dimension = int(matrix.shape[1])
                self._index = self._new_index(self._dimension)
            elif matrix.shape[1] != self._dimension:
                raise ValueError(f"Embedding dimension mismatch: expected {self._dimension}, got {matrix.shape[1]}.")

            last_position_by_id: dict[str, int] = {}
            ordered_ids: list[str] = []
            for index, doc_id in enumerate(resolved_ids):
                if doc_id not in last_position_by_id:
                    ordered_ids.append(doc_id)
                last_position_by_id[doc_id] = index

            existing_int_ids = [
                self._records[doc_id].int_id
                for doc_id in ordered_ids
                if doc_id in self._records
            ]
            if existing_int_ids:
                self._index.remove_ids(self._np.asarray(existing_int_ids, dtype="int64"))

            matrix_rows = []
            faiss_ids = []
            for doc_id in ordered_ids:
                source_index = last_position_by_id[doc_id]
                current = self._records.get(doc_id)
                int_id = current.int_id if current is not None else self._next_faiss_id()
                metadata = resolved_metadatas[source_index]
                self._records[doc_id] = _FaissRecord(
                    id=doc_id,
                    int_id=int_id,
                    document=str(texts[source_index]),
                    metadata=dict(metadata) if isinstance(metadata, dict) else {},
                )
                matrix_rows.append(matrix[source_index])
                faiss_ids.append(int_id)

            if matrix_rows:
                vectors = self._np.ascontiguousarray(self._np.vstack(matrix_rows), dtype="float32")
                self._index.add_with_ids(vectors, self._np.asarray(faiss_ids, dtype="int64"))
            self._persist()

    def query_by_metadata(self, where: dict[str, Any], n_results: int | None = None):
        with self._lock:
            records = self._records_matching(where)
            if n_results is not None:
                records = records[: max(int(n_results), 0)]
            return _flat_results_from_records(records)

    def query_with_vector(self, query_embedding: list[float], n_results: int = 5, where: dict[str, Any] | None = None):
        with self._lock:
            total = len(self._records)
            if total == 0 or self._index is None or self._dimension is None:
                return _nested_results()

            limit = max(int(n_results or 5), 1)
            query = self._normalized_matrix([query_embedding], expected_dimension=self._dimension)
            records_by_int_id = {record.int_id: record for record in self._records.values()}

            if where:
                window = min(total, max(limit, min(total, limit * 4)))
                candidates: list[tuple[_FaissRecord, float]] = []
                while True:
                    candidates = self._search(query, window, records_by_int_id, where)
                    if len(candidates) >= limit or window >= total:
                        break
                    window = min(total, max(window * 2, window + limit))
            else:
                candidates = self._search(query, min(limit, total), records_by_int_id, None)

            records = candidates[:limit]
            return {
                "ids": [[record.id for record, _distance in records]],
                "documents": [[record.document for record, _distance in records]],
                "metadatas": [[dict(record.metadata) for record, _distance in records]],
                "distances": [[distance for _record, distance in records]],
            }

    def get_by_ids(self, ids: list[str]):
        if not ids:
            return _flat_results()
        with self._lock:
            records = [self._records[doc_id] for doc_id in ids if doc_id in self._records]
            return _flat_results_from_records(records)

    def delete_documents(self, where: dict[str, Any]):
        with self._lock:
            records = self._records_matching(where)
            if not records:
                return
            int_ids = [record.int_id for record in records]
            if self._index is not None:
                self._index.remove_ids(self._np.asarray(int_ids, dtype="int64"))
            for record in records:
                self._records.pop(record.id, None)
            self._persist()

    def update_document_metadata(self, where: dict[str, Any], updates: dict[str, Any]) -> bool:
        with self._lock:
            records = self._records_matching(where)
            if not records:
                return False
            for record in records:
                record.metadata.update(updates)
            self._persist()
            return True

    def clear_collection(self):
        with self._lock:
            if self.path.exists():
                shutil.rmtree(self.path)
            self.path.mkdir(parents=True, exist_ok=True)
            self._dimension = None
            self._next_int_id = 1
            self._records: dict[str, _FaissRecord] = {}
            self._index = None
            self._persist()

    def delete_collection(self):
        with self._lock:
            if self.path.exists():
                shutil.rmtree(self.path)
            self._dimension = None
            self._next_int_id = 1
            self._records = {}
            self._index = None

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def file_count(self) -> int:
        with self._lock:
            return len(_document_summary_map([record.metadata for record in self._records.values()]))

    def peek(self, limit: int = 5):
        with self._lock:
            records = sorted(self._records.values(), key=lambda item: item.int_id)[: max(int(limit), 0)]
            return _flat_results_from_records(records)

    def list_document_summaries(self):
        with self._lock:
            return _sorted_document_summaries([record.metadata for record in self._records.values()])

    def _load(self):
        self._dimension: int | None = None
        self._next_int_id = 1
        self._records: dict[str, _FaissRecord] = {}
        self._index = None

        if self.records_path.exists():
            payload = json.loads(self.records_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"FAISS records file '{self.records_path.name}' must contain a JSON object.")
            dimension = payload.get("dimension")
            self._dimension = int(dimension) if dimension is not None else None
            self._next_int_id = max(int(payload.get("next_int_id") or 1), 1)
            for item in payload.get("records") or []:
                if not isinstance(item, dict):
                    continue
                record_id = str(item.get("id") or "").strip()
                if not record_id:
                    continue
                metadata = item.get("metadata")
                self._records[record_id] = _FaissRecord(
                    id=record_id,
                    int_id=int(item.get("int_id")),
                    document=str(item.get("document") or ""),
                    metadata=dict(metadata) if isinstance(metadata, dict) else {},
                )
            if self._records:
                self._next_int_id = max(self._next_int_id, max(record.int_id for record in self._records.values()) + 1)

        if self._dimension is None:
            return

        if not self.index_path.exists():
            if self._records:
                raise ValueError(f"FAISS index is missing for collection '{self.collection_name}'.")
            self._index = self._new_index(self._dimension)
            return

        self._index = self._faiss.read_index(str(self.index_path))
        if int(self._index.ntotal) != len(self._records):
            raise ValueError(f"FAISS index and metadata are out of sync for collection '{self.collection_name}'.")

    def _persist(self):
        self.path.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self._VERSION,
            "dimension": self._dimension,
            "metric": self._METRIC,
            "next_int_id": self._next_int_id,
            "records": [
                {
                    "id": record.id,
                    "int_id": record.int_id,
                    "document": record.document,
                    "metadata": record.metadata,
                }
                for record in sorted(self._records.values(), key=lambda item: item.int_id)
            ],
        }
        records_temp = self.records_path.with_name(f"{self.records_path.name}.tmp")
        index_temp = self.index_path.with_name(f"{self.index_path.name}.tmp")
        records_temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if self._index is not None:
            self._faiss.write_index(self._index, str(index_temp))
            os.replace(index_temp, self.index_path)
        elif self.index_path.exists():
            self.index_path.unlink()
        os.replace(records_temp, self.records_path)

    def _new_index(self, dimension: int):
        return self._faiss.IndexIDMap2(self._faiss.IndexFlatIP(int(dimension)))

    def _next_faiss_id(self) -> int:
        value = self._next_int_id
        self._next_int_id += 1
        return value

    def _normalized_matrix(self, embeddings: list[list[float]], expected_dimension: int | None):
        matrix = self._np.asarray(embeddings, dtype="float32")
        if matrix.ndim != 2:
            raise ValueError("Embeddings must be a list of vectors.")
        if matrix.shape[1] <= 0:
            raise ValueError("Embedding vectors must not be empty.")
        if expected_dimension is not None and matrix.shape[1] != expected_dimension:
            raise ValueError(f"Embedding dimension mismatch: expected {expected_dimension}, got {matrix.shape[1]}.")
        matrix = self._np.ascontiguousarray(matrix.copy(), dtype="float32")
        norms = self._np.linalg.norm(matrix, axis=1)
        if self._np.any(norms <= 0):
            raise ValueError("Embedding vectors must not be all zeros.")
        self._faiss.normalize_L2(matrix)
        return matrix

    def _records_matching(self, where: dict[str, Any] | None) -> list[_FaissRecord]:
        return [
            record
            for record in sorted(self._records.values(), key=lambda item: item.int_id)
            if _metadata_matches(record.metadata, where)
        ]

    def _search(
        self,
        query,
        window: int,
        records_by_int_id: dict[int, _FaissRecord],
        where: dict[str, Any] | None,
    ) -> list[tuple[_FaissRecord, float]]:
        scores, int_ids = self._index.search(query, max(int(window), 1))
        candidates: list[tuple[_FaissRecord, float]] = []
        for score, int_id in zip(scores[0], int_ids[0]):
            resolved_int_id = int(int_id)
            if resolved_int_id < 0:
                continue
            record = records_by_int_id.get(resolved_int_id)
            if record is None or not _metadata_matches(record.metadata, where):
                continue
            similarity = max(-1.0, min(1.0, float(score)))
            candidates.append((record, 1.0 - similarity))
        return candidates


_FAISS_LOCKS: dict[Path, threading.RLock] = {}
_FAISS_LOCKS_GUARD = threading.Lock()


def _faiss_collection_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _FAISS_LOCKS_GUARD:
        lock = _FAISS_LOCKS.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _FAISS_LOCKS[resolved] = lock
        return lock


def _load_faiss_dependencies():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError(
            "FAISS vector database backend requires the 'faiss-cpu' package. "
            "Install it with `python -m pip install faiss-cpu` or `python -m pip install -e .`."
        ) from exc
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("FAISS vector database backend requires NumPy, which is installed with 'faiss-cpu'.") from exc
    return faiss, np


def _validate_add_payload(
    *,
    texts: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict[str, Any]] | None,
    ids: list[str] | None,
):
    expected = len(texts)
    if len(embeddings) != expected:
        raise ValueError(f"Expected {expected} embedding vector(s), got {len(embeddings)}.")
    if metadatas is not None and len(metadatas) != expected:
        raise ValueError(f"Expected {expected} metadata record(s), got {len(metadatas)}.")
    if ids is not None and len(ids) != expected:
        raise ValueError(f"Expected {expected} id(s), got {len(ids)}.")


def _metadata_matches(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    for key, expected in where.items():
        if isinstance(expected, dict) and "$eq" in expected:
            expected = expected["$eq"]
        if metadata.get(key) != expected:
            return False
    return True


def _flat_results() -> dict[str, list[Any]]:
    return {"ids": [], "documents": [], "metadatas": []}


def _nested_results() -> dict[str, list[list[Any]]]:
    return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


def _flat_results_from_records(records: list[_FaissRecord]) -> dict[str, list[Any]]:
    return {
        "ids": [record.id for record in records],
        "documents": [record.document for record in records],
        "metadatas": [dict(record.metadata) for record in records],
    }


def _document_summary_map(metadatas: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for metadata in metadatas:
        if not isinstance(metadata, dict):
            continue
        file_path = str(metadata.get("file_path") or "").strip() or None
        source_name = str(metadata.get("source_name") or file_path or "Untitled").strip() or "Untitled"
        source_type = str(metadata.get("source_type") or "unknown").strip() or "unknown"
        key = file_path or f"{source_name}:{source_type}"
        current = summaries.get(key)
        if current is None:
            summaries[key] = {
                "id": key,
                "source_name": source_name,
                "source_type": source_type,
                "file_path": file_path,
                "chunk_count": 1,
            }
            continue
        current["chunk_count"] += 1
    return summaries


def _sorted_document_summaries(metadatas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = _document_summary_map(metadatas)
    return sorted(summaries.values(), key=lambda item: (item["source_name"].lower(), item["file_path"] or ""))
