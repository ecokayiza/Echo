from __future__ import annotations

import argparse
import gzip
import json
import re
import struct
import sys
import textwrap
import uuid
import zipfile
from dataclasses import asdict, dataclass
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

FLASHRAG_ID_NAMESPACE = "RUC-NLPIR/FlashRAG_datasets"
MANUAL_CORPUS_URL = "https://www.modelscope.cn/datasets/hhjinjiajie/FlashRAG_Dataset/tree/master/retrieval_corpus"
WIKI_DPR_FILENAME = "retrieval-corpus/wiki18_100w.zip"
DEFAULT_LOCAL_E5_MODEL = "intfloat/e5-base-v2"
DEFAULT_LOCAL_E5_BASE_URL = "http://127.0.0.1:8092/v1"
DEFAULT_LOCAL_E5_API_KEY = "local-e5-service"
DEFAULT_HOTPOTQA_DIR = Path(__file__).resolve().parent / "hotpotqa"
HOTPOTQA_SPLIT_FILENAMES = {
    "dev": "hotpotqa/dev.jsonl",
    "test": "hotpotqa/dev.jsonl",
    "train": "hotpotqa/train.jsonl",
}
Retriever = Callable[[str, int], dict[str, Any]]


@dataclass(frozen=True)
class IndexSummary:
    database_name: str
    collection_name: str
    backend: str
    seen: int
    inserted: int
    skipped: int


@dataclass(frozen=True)
class EvaluationExample:
    question: str
    answers: list[str]
    hit: bool
    f1: float
    retrieved_titles: list[str]


@dataclass(frozen=True)
class EvaluationSummary:
    database_name: str
    split: str
    questions: int
    hits: int
    hit_rate: float
    average_f1: float
    top_k: int
    examples: list[EvaluationExample]


class JsonlOffsetDocstore:
    """Random-access JSONL reader backed by a uint64 byte-offset file."""

    def __init__(self, corpus_path: Path, offset_path: Path):
        self.corpus_path = corpus_path
        self.offset_path = offset_path
        self._corpus = corpus_path.open("rb")
        self._offsets = offset_path.open("rb")

    def close(self):
        self._offsets.close()
        self._corpus.close()

    def get(self, row_index: int) -> dict[str, Any]:
        if row_index < 0:
            raise IndexError(f"Corpus row index must be non-negative, got {row_index}.")
        self._offsets.seek(row_index * 8)
        payload = self._offsets.read(8)
        if len(payload) != 8:
            raise IndexError(f"Corpus row index {row_index} is not present in {self.offset_path}.")
        offset = struct.unpack("<Q", payload)[0]
        self._corpus.seek(offset)
        line = self._corpus.readline()
        if not line:
            raise IndexError(f"Corpus row index {row_index} points past the end of {self.corpus_path}.")
        return json.loads(line.decode("utf-8"))


class FlashRAGPrebuiltIndexRetriever:
    """Eval-only retriever for a prebuilt FlashRAG FAISS index plus wiki18_100w JSONL."""

    def __init__(
        self,
        *,
        index_path: Path,
        corpus_path: Path,
        offset_path: Path,
        local_e5_model: str = DEFAULT_LOCAL_E5_MODEL,
        local_e5_base_url: str = DEFAULT_LOCAL_E5_BASE_URL,
        local_e5_api_key: str = DEFAULT_LOCAL_E5_API_KEY,
        faiss_mmap: bool = True,
        database_name: str = "wiki18_100w",
    ):
        self.index_path = index_path
        self.corpus_path = corpus_path
        self.offset_path = offset_path
        self.local_e5_model = local_e5_model
        self.local_e5_base_url = local_e5_base_url
        self.local_e5_api_key = local_e5_api_key
        self.database_name = database_name
        self.faiss = _load_faiss_module()
        self.index = _read_faiss_index(self.faiss, index_path, faiss_mmap=faiss_mmap)
        self.docstore = JsonlOffsetDocstore(corpus_path, offset_path)

    def close(self):
        self.docstore.close()

    def retrieve(self, question: str, top_k: int) -> dict[str, Any]:
        from mcp_server.rag.embedder import OpenAICompatibleEmbedder

        import numpy as np

        query_embedding = OpenAICompatibleEmbedder.embed_query(
            question,
            settings={
                "name": "Local E5 FlashRAG",
                "model": self.local_e5_model,
                "api_key": self.local_e5_api_key,
                "base_url": self.local_e5_base_url,
            },
        )
        query = np.asarray([query_embedding], dtype="float32")
        self.faiss.normalize_L2(query)
        scores, ids = self.index.search(query, max(int(top_k), 1))
        items = []
        metric_type = _faiss_metric_type(self.faiss, self.index)
        for score, faiss_id in zip(list(scores[0]), list(ids[0])):
            row_index = int(faiss_id)
            if row_index < 0:
                continue
            record = self.docstore.get(row_index)
            text = extract_corpus_text(record)
            if not text:
                continue
            title = extract_corpus_title(record, fallback_id=str(row_index))
            items.append(
                {
                    "title": title,
                    "content": text,
                    "source_type": "flashrag_wikipedia_dpr",
                    "file_path": f"flashrag/wiki18_100w/{row_index}",
                    "url": None,
                    "distance": _faiss_distance(self.faiss, metric_type, float(score)),
                    "database_name": self.database_name,
                }
            )
        return {"type": "context", "skill_name": "database_search", "items": items}


def iter_jsonl_records(path: Path, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
    count = 0
    for line in _iter_jsonl_lines(path):
        if not line.strip():
            continue
        record = json.loads(line)
        if isinstance(record, dict):
            yield record
            count += 1
            if limit is not None and count >= limit:
                break


def _iter_jsonl_lines(path: Path) -> Iterator[str]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        yield from _iter_zip_jsonl_lines(path)
        return
    if suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            yield from handle
        return
    with path.open("r", encoding="utf-8") as handle:
        yield from handle


def _iter_zip_jsonl_lines(path: Path) -> Iterator[str]:
    with zipfile.ZipFile(path) as archive:
        members = sorted(name for name in archive.namelist() if name.lower().endswith(".jsonl"))
        if not members:
            raise ValueError(f"No JSONL file found inside {path}.")
        preferred = next((name for name in members if "wiki18_100w" in name.lower()), members[0])
        with archive.open(preferred) as raw:
            yield from TextIOWrapper(raw, encoding="utf-8")


def extract_corpus_text(record: dict[str, Any]) -> str:
    contents = record.get("contents")
    if isinstance(contents, str):
        return _clean_text(contents)

    title = str(record.get("title") or "").strip()
    text = str(record.get("text") or record.get("document") or record.get("passage") or "").strip()
    return _clean_text(f"{title}\n{text}" if title and text else title or text)


def extract_corpus_title(record: dict[str, Any], *, fallback_id: str) -> str:
    title = str(record.get("title") or "").strip()
    if title:
        return title
    contents = record.get("contents")
    if isinstance(contents, str):
        first_line = contents.strip().splitlines()[0].strip() if contents.strip() else ""
        if first_line:
            return first_line
    return f"FlashRAG wiki18_100w #{fallback_id}"


def extract_record_id(record: dict[str, Any], fallback_index: int) -> str:
    value = record.get("id", record.get("docid", record.get("_id", fallback_index)))
    return str(value)


def extract_question(record: dict[str, Any]) -> str:
    return _clean_text(str(record.get("question") or record.get("query") or ""))


def extract_answers(record: dict[str, Any]) -> list[str]:
    raw = record.get("golden_answers", record.get("answers", record.get("answer", [])))
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    answers = []
    for item in raw:
        answer = _clean_text(str(item))
        if answer:
            answers.append(answer)
    return answers


def answer_in_text(answers: Iterable[str], text: str) -> bool:
    normalized_text = _normalize_for_match(text)
    return any(_normalize_for_match(answer) in normalized_text for answer in answers if answer.strip())


def best_answer_f1(answers: Iterable[str], text: str) -> float:
    """Return the best normalized token F1 score between one retrieved text and the gold answers."""
    return max((_token_f1(answer, text) for answer in answers if answer.strip()), default=0.0)


def ensure_jsonl_offsets(corpus_path: Path, offset_path: Path) -> int:
    """Create a uint64 little-endian JSONL byte-offset file when missing."""
    if offset_path.exists():
        return offset_path.stat().st_size // 8
    offset_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with corpus_path.open("rb") as source, offset_path.open("wb") as offsets:
        while True:
            offset = source.tell()
            line = source.readline()
            if not line:
                break
            offsets.write(struct.pack("<Q", offset))
            count += 1
    return count


def _load_faiss_module():
    try:
        import faiss
    except ImportError as exc:
        raise SystemExit(
            "The flashrag-index retriever requires faiss-cpu. Install dependencies with `python -m pip install -e .`."
        ) from exc
    return faiss


def _read_faiss_index(faiss_module, index_path: Path, *, faiss_mmap: bool):
    flags = faiss_module.IO_FLAG_MMAP if faiss_mmap and hasattr(faiss_module, "IO_FLAG_MMAP") else 0
    try:
        return faiss_module.read_index(str(index_path), flags)
    except Exception as exc:
        mmap_note = " with mmap" if flags else ""
        raise SystemExit(
            f"Failed to load FlashRAG FAISS index{mmap_note} from {index_path}. "
            "Try a smaller index, disable mmap, or use a machine with more RAM."
        ) from exc


def _faiss_metric_type(faiss_module, index) -> int | None:
    metric_type = getattr(index, "metric_type", None)
    if metric_type is not None:
        return metric_type
    inner = getattr(index, "index", None)
    return getattr(inner, "metric_type", None) if inner is not None else None


def _faiss_distance(faiss_module, metric_type: int | None, score: float) -> float:
    if metric_type == getattr(faiss_module, "METRIC_INNER_PRODUCT", None):
        return 1.0 - score
    return score


def index_wikipedia_dpr(
    *,
    database_name: str,
    embedding_model_name: str | None,
    backend: str | None,
    corpus_path: Path,
    max_docs: int | None,
    batch_size: int,
    skip_existing: bool,
) -> IndexSummary:
    from mcp_server.rag.database_registry import (
        create_database_settings,
        list_database_settings,
        resolve_database_embedding_settings,
        select_database_settings,
    )
    from mcp_server.rag.embedder import OpenAICompatibleEmbedder
    from mcp_server.rag.vector_database import VectorDatabase

    document = list_database_settings()
    database = next((item for item in document.databases if item.name == database_name), None)
    if database is None:
        document = create_database_settings(
            name=database_name,
            embedding_model_name=embedding_model_name,
            backend=backend,
            select=True,
        )
        database = next(item for item in document.databases if item.name == database_name)
    else:
        select_database_settings(database.id)

    embedding_settings = resolve_database_embedding_settings(database)
    vector_db = VectorDatabase(collection_name=database.collection_name, backend=database.backend)

    seen = inserted = skipped = 0
    batch: list[tuple[str, str, dict[str, Any]]] = []
    for index, record in enumerate(iter_jsonl_records(corpus_path, limit=max_docs)):
        text = extract_corpus_text(record)
        if not text:
            continue
        source_id = extract_record_id(record, index)
        doc_id = deterministic_flashrag_id(WIKI_DPR_FILENAME, source_id)
        metadata = {
            "source_name": f"FlashRAG wiki18_100w #{source_id}",
            "source_type": "flashrag_wikipedia_dpr",
            "file_path": f"flashrag/{WIKI_DPR_FILENAME}/{source_id}",
            "chunk_index": 0,
            "flashrag_id": source_id,
        }
        batch.append((doc_id, text, metadata))
        seen += 1
        if len(batch) >= batch_size:
            inserted_now, skipped_now = _flush_index_batch(
                vector_db,
                embedding_settings,
                batch,
                skip_existing=skip_existing,
            )
            inserted += inserted_now
            skipped += skipped_now
            batch.clear()
            print(f"Indexed {seen} DPR passages (inserted={inserted}, skipped={skipped}).", flush=True)

    if batch:
        inserted_now, skipped_now = _flush_index_batch(
            vector_db,
            embedding_settings,
            batch,
            skip_existing=skip_existing,
        )
        inserted += inserted_now
        skipped += skipped_now

    return IndexSummary(
        database_name=database.name,
        collection_name=database.collection_name,
        backend=database.backend,
        seen=seen,
        inserted=inserted,
        skipped=skipped,
    )


def _flush_index_batch(
    vector_db,
    embedding_settings,
    batch: list[tuple[str, str, dict[str, Any]]],
    *,
    skip_existing: bool,
) -> tuple[int, int]:
    from mcp_server.rag.embedder import OpenAICompatibleEmbedder

    ids = [item[0] for item in batch]
    pending = batch
    skipped = 0
    if skip_existing:
        existing = set(vector_db.get_by_ids(ids).get("ids") or [])
        pending = [item for item in batch if item[0] not in existing]
        skipped = len(batch) - len(pending)

    if not pending:
        return 0, skipped

    texts = [item[1] for item in pending]
    embeddings = OpenAICompatibleEmbedder.embed_documents(texts, settings=embedding_settings)
    vector_db.add_documents(
        ids=[item[0] for item in pending],
        texts=texts,
        embeddings=embeddings,
        metadatas=[item[2] for item in pending],
    )
    return len(pending), skipped


def evaluate_hotpotqa(
    *,
    database_name: str,
    split: str,
    dataset_path: Path,
    max_questions: int | None,
    top_k: int,
    sample_examples: int,
    retriever: Retriever | None = None,
) -> EvaluationSummary:
    if retriever is None:
        from mcp_server.rag.database_registry import list_database_settings, select_database_settings
        from mcp_server.tools.database_search import database_search

        document = list_database_settings()
        database = next((item for item in document.databases if item.name == database_name), None)
        if database is None:
            raise SystemExit(f"Database '{database_name}' was not found. Index or create it first.")
        select_database_settings(database.id)
        resolved_database_name = database.name
        active_retriever: Retriever = lambda question, limit: database_search(question, top_k=limit)
    else:
        resolved_database_name = database_name
        active_retriever = retriever

    questions = hits = 0
    total_f1 = 0.0
    examples: list[EvaluationExample] = []
    for record in iter_jsonl_records(dataset_path, limit=max_questions):
        question = extract_question(record)
        answers = extract_answers(record)
        if not question or not answers:
            continue

        result = active_retriever(question, top_k)
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        items = result.get("items") or []
        retrieved_text = "\n".join(str(item.get("content") or "") for item in items if isinstance(item, dict))
        hit = answer_in_text(answers, retrieved_text)
        f1 = best_answer_f1(answers, retrieved_text)
        questions += 1
        hits += int(hit)
        total_f1 += f1

        if len(examples) < sample_examples:
            examples.append(
                EvaluationExample(
                    question=question,
                    answers=answers[:5],
                    hit=hit,
                    f1=f1,
                    retrieved_titles=[
                        str(item.get("title") or "")
                        for item in items[:top_k]
                        if isinstance(item, dict)
                    ],
                )
            )

    hit_rate = hits / questions if questions else 0.0
    average_f1 = total_f1 / questions if questions else 0.0
    return EvaluationSummary(
        database_name=resolved_database_name,
        split=split,
        questions=questions,
        hits=hits,
        hit_rate=hit_rate,
        average_f1=average_f1,
        top_k=top_k,
        examples=examples,
    )


def deterministic_flashrag_id(filename: str, source_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{FLASHRAG_ID_NAMESPACE}:{filename}:{source_id}"))


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _normalize_for_f1(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _token_f1(expected: str, predicted: str) -> float:
    expected_tokens = _normalize_for_f1(expected).split()
    predicted_tokens = _normalize_for_f1(predicted).split()
    if not expected_tokens or not predicted_tokens:
        return float(expected_tokens == predicted_tokens)

    remaining: dict[str, int] = {}
    for token in expected_tokens:
        remaining[token] = remaining.get(token, 0) + 1

    overlap = 0
    for token in predicted_tokens:
        count = remaining.get(token, 0)
        if count <= 0:
            continue
        overlap += 1
        remaining[token] = count - 1

    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted_tokens)
    recall = overlap / len(expected_tokens)
    return 2 * precision * recall / (precision + recall)


def _positive_or_none(value: int) -> int | None:
    return None if value <= 0 else value


def _json_ready(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_ready(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index a manually downloaded FlashRAG Wikipedia DPR corpus into Echo and evaluate retrieval with HotpotQA.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--database-name", default="wiki18_100w")
    parser.add_argument("--embedding-model-name", default="E5-base-v2")
    parser.add_argument("--backend", choices=["chroma", "faiss"], default=None)
    parser.add_argument("--retriever", choices=["echo-db", "flashrag-index"], default="echo-db")
    parser.add_argument(
        "--index-wiki",
        action="store_true",
        help="Index a manually downloaded wiki18_100w JSONL/JSONL.GZ/ZIP corpus.",
    )
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=None,
        help=f"Required with --index-wiki. Download wiki18_100w manually from {MANUAL_CORPUS_URL}.",
    )
    parser.add_argument("--max-corpus-docs", type=int, default=1000, help="Limit indexed DPR passages; 0 means all.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-evaluate", action="store_true", help="Skip HotpotQA retrieval evaluation.")
    parser.add_argument("--hotpotqa-split", choices=sorted(HOTPOTQA_SPLIT_FILENAMES), default="dev")
    parser.add_argument(
        "--hotpotqa-path",
        type=Path,
        default=None,
        help="Path to a local HotpotQA JSONL file. Defaults to tests/eval/hotpotqa/{split}.jsonl when present.",
    )
    parser.add_argument("--max-questions", type=int, default=50, help="Limit evaluated questions; 0 means all.")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--sample-examples", type=int, default=5)
    parser.add_argument("--flashrag-index-path", type=Path, default=None)
    parser.add_argument(
        "--offset-path",
        type=Path,
        default=None,
        help="Byte-offset file for the JSONL corpus. Defaults to <corpus-path>.offsets.u64 when omitted.",
    )
    parser.add_argument(
        "--local-e5-model",
        default=DEFAULT_LOCAL_E5_MODEL,
        help="Model name served by the manually launched local E5 embedding service.",
    )
    parser.add_argument("--local-e5-base-url", default=DEFAULT_LOCAL_E5_BASE_URL)
    parser.add_argument("--local-e5-api-key", default=DEFAULT_LOCAL_E5_API_KEY)
    parser.add_argument("--faiss-mmap", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=Path(__file__).with_name("flashrag_hotpotqa_last_run.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive.")
    if args.top_k <= 0:
        raise SystemExit("--top-k must be positive.")

    summary: dict[str, Any] = {}
    retriever: Retriever | None = None
    retriever_handle = None

    if args.retriever == "flashrag-index":
        if args.index_wiki:
            raise SystemExit("--index-wiki cannot be combined with --retriever flashrag-index.")
        corpus_path = _require_existing_path(
            args.corpus_path,
            label="wiki18_100w corpus",
            missing_message=(
                "--corpus-path is required with --retriever flashrag-index. "
                "Download wiki18_100w manually from the ModelScope retrieval_corpus page."
            ),
        )
        _require_uncompressed_jsonl(corpus_path)
        index_path = _require_existing_path(
            args.flashrag_index_path,
            label="FlashRAG FAISS index",
            missing_message="--flashrag-index-path is required with --retriever flashrag-index.",
        )
        offset_path = args.offset_path or Path(str(corpus_path) + ".offsets.u64")
        ensure_jsonl_offsets(corpus_path, offset_path)
        retriever_handle = FlashRAGPrebuiltIndexRetriever(
            index_path=index_path,
            corpus_path=corpus_path,
            offset_path=offset_path,
            local_e5_model=args.local_e5_model,
            local_e5_base_url=args.local_e5_base_url,
            local_e5_api_key=args.local_e5_api_key,
            faiss_mmap=args.faiss_mmap,
            database_name=args.database_name,
        )
        retriever = retriever_handle.retrieve

    if args.index_wiki:
        corpus_path = _require_existing_path(
            args.corpus_path,
            label="wiki18_100w corpus",
            missing_message=textwrap.dedent(
                f"""
                --corpus-path is required with --index-wiki.
                Download wiki18_100w manually from:
                  {MANUAL_CORPUS_URL}

                Then re-run, for example:
                  python tests/eval/flashrag_hotpotqa_eval.py --index-wiki --corpus-path path/to/wiki18_100w.zip
                """
            ).strip(),
        )
        index_summary = index_wikipedia_dpr(
            database_name=args.database_name,
            embedding_model_name=args.embedding_model_name,
            backend=args.backend,
            corpus_path=corpus_path,
            max_docs=_positive_or_none(args.max_corpus_docs),
            batch_size=args.batch_size,
            skip_existing=args.skip_existing,
        )
        summary["index"] = _json_ready(index_summary)
        print(json.dumps(summary["index"], ensure_ascii=False, indent=2), flush=True)

    if not args.no_evaluate:
        try:
            dataset_path = _require_existing_path(
                args.hotpotqa_path or _default_hotpotqa_path(args.hotpotqa_split),
                label="HotpotQA dataset",
                missing_message=(
                    f"HotpotQA dataset was not found. Pass --hotpotqa-path with a local JSONL file "
                    f"or place it at tests/eval/hotpotqa/{args.hotpotqa_split}.jsonl."
                ),
            )
            eval_summary = evaluate_hotpotqa(
                database_name=args.database_name,
                split=args.hotpotqa_split,
                dataset_path=dataset_path,
                max_questions=_positive_or_none(args.max_questions),
                top_k=args.top_k,
                sample_examples=max(args.sample_examples, 0),
                retriever=retriever,
            )
            summary["evaluation"] = _json_ready(eval_summary)
            print(json.dumps(summary["evaluation"], ensure_ascii=False, indent=2), flush=True)
        finally:
            if retriever_handle is not None:
                retriever_handle.close()
    elif retriever_handle is not None:
        retriever_handle.close()

    if summary:
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote summary to {args.summary_path}.", flush=True)

    return 0


def _default_hotpotqa_path(split: str) -> Path:
    return Path(__file__).resolve().parent / HOTPOTQA_SPLIT_FILENAMES[split]


def _require_existing_path(path: Path | None, *, label: str, missing_message: str) -> Path:
    if path is None:
        raise SystemExit(missing_message)
    resolved = Path(path)
    if not resolved.exists():
        raise SystemExit(f"{label} file does not exist: {resolved}")
    return resolved


def _require_uncompressed_jsonl(path: Path):
    suffix = path.suffix.lower()
    if suffix != ".jsonl":
        raise SystemExit("flashrag-index retriever requires an uncompressed .jsonl corpus.")


if __name__ == "__main__":
    raise SystemExit(main())
