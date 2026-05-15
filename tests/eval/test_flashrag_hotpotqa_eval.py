import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import struct


MODULE_PATH = Path(__file__).resolve().with_name("flashrag_hotpotqa_eval.py")
SPEC = importlib.util.spec_from_file_location("flashrag_hotpotqa_eval", MODULE_PATH)
flashrag_hotpotqa_eval = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = flashrag_hotpotqa_eval
SPEC.loader.exec_module(flashrag_hotpotqa_eval)


class FlashRAGHotpotQAEvalTests(unittest.TestCase):
    def test_iter_jsonl_records_reads_plain_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.jsonl"
            path.write_text('{"id": "1", "contents": "Alpha"}\n\n{"id": "2", "contents": "Beta"}\n', encoding="utf-8")

            records = list(flashrag_hotpotqa_eval.iter_jsonl_records(path, limit=1))

        self.assertEqual(records, [{"id": "1", "contents": "Alpha"}])

    def test_iter_jsonl_records_reads_flashrag_zip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "wiki18_100w.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("wiki18_100w.jsonl", '{"id": "doc-1", "contents": "Title\\nPassage text"}\n')

            records = list(flashrag_hotpotqa_eval.iter_jsonl_records(path))

        self.assertEqual(records[0]["id"], "doc-1")
        self.assertEqual(records[0]["contents"], "Title\nPassage text")

    def test_extractors_accept_flashrag_dataset_shapes(self):
        record = {
            "id": "q-1",
            "question": " Where was the author born? ",
            "golden_answers": [" New York ", ""],
            "metadata": {"source": "hotpotqa"},
        }

        self.assertEqual(flashrag_hotpotqa_eval.extract_question(record), "Where was the author born?")
        self.assertEqual(flashrag_hotpotqa_eval.extract_answers(record), ["New York"])

    def test_answer_match_is_case_and_whitespace_insensitive(self):
        answers = ["New York City"]
        text = "The answer is new   york city, according to the passage."

        self.assertTrue(flashrag_hotpotqa_eval.answer_in_text(answers, text))

    def test_best_answer_f1_scores_token_overlap(self):
        score = flashrag_hotpotqa_eval.best_answer_f1(["New York City"], "new york")

        self.assertGreater(score, 0.79)
        self.assertLess(score, 0.81)

    def test_deterministic_flashrag_id_is_stable(self):
        first = flashrag_hotpotqa_eval.deterministic_flashrag_id("retrieval-corpus/wiki18_100w.zip", "123")
        second = flashrag_hotpotqa_eval.deterministic_flashrag_id("retrieval-corpus/wiki18_100w.zip", "123")

        self.assertEqual(first, second)

    def test_json_ready_serializes_nested_dataclasses(self):
        example = flashrag_hotpotqa_eval.EvaluationExample(
            question="Q?",
            answers=["A"],
            hit=True,
            f1=1.0,
            retrieved_titles=["doc"],
        )
        summary = flashrag_hotpotqa_eval.EvaluationSummary(
            database_name="Wikipedia DPR",
            split="dev",
            questions=1,
            hits=1,
            hit_rate=1.0,
            average_f1=1.0,
            top_k=4,
            examples=[example],
        )

        payload = flashrag_hotpotqa_eval._json_ready(summary)

        self.assertEqual(json.loads(json.dumps(payload))["examples"][0]["hit"], True)

    def test_flush_index_batch_uses_backend_neutral_id_lookup(self):
        class FakeVectorDatabase:
            def __init__(self):
                self.looked_up_ids = []
                self.added_ids = []

            def get_by_ids(self, ids):
                self.looked_up_ids = ids
                return {"ids": ["existing"]}

            def add_documents(self, *, ids, texts, embeddings, metadatas):
                self.added_ids = ids

        vector_db = FakeVectorDatabase()
        batch = [
            ("existing", "Existing text", {"source_name": "Existing"}),
            ("new", "New text", {"source_name": "New"}),
        ]

        with patch("mcp_server.rag.embedder.OpenAICompatibleEmbedder.embed_documents", return_value=[[0.1, 0.2]]):
            inserted, skipped = flashrag_hotpotqa_eval._flush_index_batch(
                vector_db,
                object(),
                batch,
                skip_existing=True,
            )

        self.assertEqual(vector_db.looked_up_ids, ["existing", "new"])
        self.assertEqual(vector_db.added_ids, ["new"])
        self.assertEqual(inserted, 1)
        self.assertEqual(skipped, 1)

    def test_offsets_file_supports_random_access_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus_path = Path(temp_dir) / "wiki18_100w.jsonl"
            offset_path = Path(temp_dir) / "wiki18_100w.offsets.u64"
            corpus_path.write_text(
                '{"id": "0", "contents": "First passage"}\n{"id": "1", "contents": "Second passage"}\n',
                encoding="utf-8",
            )

            count = flashrag_hotpotqa_eval.ensure_jsonl_offsets(corpus_path, offset_path)
            store = flashrag_hotpotqa_eval.JsonlOffsetDocstore(corpus_path, offset_path)
            try:
                self.assertEqual(count, 2)
                self.assertEqual(store.get(1)["contents"], "Second passage")
                with offset_path.open("rb") as handle:
                    self.assertEqual(struct.unpack("<Q", handle.read(8))[0], 0)
            finally:
                store.close()

    def test_flashrag_index_retriever_returns_echo_items(self):
        class FakeIndex:
            metric_type = 0

            def search(self, query, top_k):
                assert top_k == 2, top_k
                return [[0.9, 0.7]], [[0, 1]]

        class FakeFaiss:
            IO_FLAG_MMAP = 1
            METRIC_INNER_PRODUCT = 0
            METRIC_L2 = 1

            @staticmethod
            def normalize_L2(matrix):
                return None

        with tempfile.TemporaryDirectory() as temp_dir:
            corpus_path = Path(temp_dir) / "wiki18_100w.jsonl"
            offset_path = Path(temp_dir) / "wiki18_100w.offsets.u64"
            index_path = Path(temp_dir) / "index.faiss"
            corpus_path.write_text(
                '{"id": "0", "title": "Alpha", "contents": "Alpha\\nAlpha text"}\n'
                '{"id": "1", "title": "Beta", "contents": "Beta\\nBeta text"}\n',
                encoding="utf-8",
            )
            flashrag_hotpotqa_eval.ensure_jsonl_offsets(corpus_path, offset_path)
            index_path.write_bytes(b"fake")

            with patch("flashrag_hotpotqa_eval._load_faiss_module", return_value=FakeFaiss()):
                with patch("flashrag_hotpotqa_eval._read_faiss_index", return_value=FakeIndex()):
                    with patch(
                        "mcp_server.rag.local_e5_embedder.LocalE5Embedder.embed_query",
                        return_value=[0.1, 0.2, 0.3],
                    ):
                        retriever = flashrag_hotpotqa_eval.FlashRAGPrebuiltIndexRetriever(
                            index_path=index_path,
                            corpus_path=corpus_path,
                            offset_path=offset_path,
                            database_name="wiki18_100w",
                        )
                        try:
                            result = retriever.retrieve("Who is alpha?", 2)
                        finally:
                            retriever.close()

        self.assertEqual(result["type"], "context")
        self.assertEqual(result["items"][0]["title"], "Alpha")
        self.assertAlmostEqual(result["items"][0]["distance"], 0.1)
        self.assertEqual(result["items"][0]["database_name"], "wiki18_100w")

    def test_index_requires_manual_corpus_path(self):
        with self.assertRaises(SystemExit) as context:
            flashrag_hotpotqa_eval.main(["--index-wiki", "--no-evaluate"])

        self.assertIn("--corpus-path is required", str(context.exception))
        self.assertIn("modelscope.cn", str(context.exception))

    def test_flashrag_index_mode_rejects_compressed_corpus(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus_path = Path(temp_dir) / "wiki18_100w.zip"
            corpus_path.write_bytes(b"fake")
            with self.assertRaises(SystemExit) as context:
                flashrag_hotpotqa_eval._require_uncompressed_jsonl(corpus_path)

        self.assertIn("requires an uncompressed .jsonl corpus", str(context.exception))

    def test_hotpotqa_default_path_is_local_eval_file(self):
        path = flashrag_hotpotqa_eval._default_hotpotqa_path("dev")

        self.assertEqual(path, Path(__file__).resolve().parent / "hotpotqa" / "dev.jsonl")


if __name__ == "__main__":
    unittest.main()
