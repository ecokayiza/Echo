import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eco_rag.config import Config
from eco_rag.indexing.chunker import ChunkerFactory, MarkdownChunker
from eco_rag.indexing.embedder import OpenAICompatibleEmbedder
from eco_rag.indexing.errors import EmbeddingError, IndexingError
from eco_rag.indexing.loader import DataLoaderFactory, PDFDataLoader
from eco_rag.settings import AppSettings, save_app_settings


class IndexingPipelineTests(unittest.TestCase):
    def test_pdf_files_use_markdown_chunking(self):
        self.assertIs(ChunkerFactory._get_chunker(".pdf"), MarkdownChunker)

    def test_markdown_chunks_keep_header_context(self):
        text = "# Guide\n\n" + ("alpha " * 300) + "\n\n## Details\n\n" + ("beta " * 300)

        chunks = ChunkerFactory.chunk(text, ".md")

        self.assertGreater(len(chunks), 1)
        self.assertTrue(any(chunk.startswith("Context: Guide") for chunk in chunks))
        self.assertTrue(all(chunk.strip() for chunk in chunks))

    def test_long_markdown_paragraph_splits_on_sentence_boundaries(self):
        paragraph = (
            "To address this issue, this paper designs and implements a retrieval-augmented generation system "
            "based on autonomous planning and decision-making. "
            "A ReAct-like framework is adopted to construct a closed-loop process of planning, acting, and observation. "
            "At the planning stage, the system decomposes a composite query into an ordered sequence of dependent sub-questions. "
            "During execution, it decides whether to continue retrieval, switch tools, or rewrite the query according to intermediate evidence."
        )
        text = "# Thesis\n\n## Abstract\n\n### ABSTRACT\n\n" + paragraph

        chunks = MarkdownChunker.chunk(text, chunk_size=320, chunk_overlap=0)
        bodies = [chunk.split("\n\n", 1)[1] for chunk in chunks]

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.startswith("Context: Thesis > Abstract > ABSTRACT") for chunk in chunks))
        self.assertTrue(all(body.endswith(".") for body in bodies))
        self.assertIn("decision-making.", bodies[0])
        self.assertFalse(bodies[1].startswith("generation system based"))

    def test_missing_embedding_key_uses_standard_error(self):
        with self.assertRaises(EmbeddingError) as context:
            OpenAICompatibleEmbedder.embed_documents(
                ["hello"],
                settings={"name": "Test Embedding", "model": "test-model", "base_url": "https://example.test/v1"},
            )

        self.assertEqual(context.exception.stage, "embedding")
        self.assertIn("Missing API key", str(context.exception))

    def test_loader_uses_standard_error_for_unsupported_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notes.csv"
            path.write_text("hello", encoding="utf-8")

            with self.assertRaises(IndexingError) as context:
                DataLoaderFactory.load(str(path))

        self.assertEqual(context.exception.stage, "loading")
        self.assertIn("No loader found", str(context.exception))

    def test_pdf_loader_prefers_marker_markdown(self):
        events = []

        def fake_marker(command, progress_callback=None):
            self.assertIn("--disable_ocr", command)
            output_dir = Path(command[-1])
            markdown_dir = output_dir / "paper"
            markdown_dir.mkdir(parents=True)
            (markdown_dir / "paper.md").write_text("# Paper\n\nStructured content", encoding="utf-8")
            progress_callback("marker_progress", {"message": "Layout detection (50%)", "percent": 50})
            return "Layout detection: 50%"

        with patch("eco_rag.indexing.loader.shutil.which", return_value="marker_single"):
            with patch("eco_rag.indexing.loader._run_marker_command", side_effect=fake_marker):
                text = PDFDataLoader().load_data("paper.pdf", progress_callback=lambda stage, payload: events.append((stage, payload)))

        self.assertIn("# Paper", text)
        self.assertIn("Structured content", text)
        self.assertEqual([stage for stage, _payload in events], ["marker_started", "marker_progress", "marker_complete"])
        self.assertEqual(events[1][1]["percent"], 50)

    def test_pdf_loader_can_disable_marker_from_settings(self):
        previous_settings_path = Config.SETTINGS_PATH
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                Config.SETTINGS_PATH = Path(temp_dir) / "settings.json"
                save_app_settings(AppSettings(use_marker_pdf_loader=False))

                with patch("eco_rag.indexing.loader.shutil.which", return_value="marker_single"):
                    with patch("eco_rag.indexing.loader._run_marker_command", side_effect=AssertionError("Marker should be disabled")):
                        with patch("eco_rag.indexing.loader._load_pdf_with_pypdf2", return_value="Plain PDF text"):
                            text = PDFDataLoader().load_data("paper.pdf")

                self.assertEqual(text, "Plain PDF text")
        finally:
            Config.SETTINGS_PATH = previous_settings_path


if __name__ == "__main__":
    unittest.main()
