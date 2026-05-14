from __future__ import annotations

import re
from abc import ABC, abstractmethod

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from echo.config import Config
from echo.settings import load_app_settings
from .errors import IndexingError

###########################################
CHUNK_SIZE = Config.CHUNK_SIZE
CHUNK_OVERLAP = Config.CHUNK_OVERLAP
###########################################
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?])\s*|(?<=\.)\s+(?=[A-Z0-9\"'“‘])")

# === Basic chunker ===
class Chunker(ABC):
    @abstractmethod
    def chunk(self, text: str, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP) -> list[str]:
        pass

class TextChunker(Chunker):
    @staticmethod
    def chunk(text: str, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP) -> list[str]:
        text = _normalize_text(text)
        if not text:
            return []
        return _split_blocks(text, chunk_size, chunk_overlap)
    
class MarkdownChunker(Chunker):
    @staticmethod
    def chunk(text: str, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP) -> list[str]:
        text = _normalize_text(text)
        if not text:
            return []
        header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
                ("####", "h4"),
            ],
            strip_headers=True,
        )
        chunks = []
        documents = header_splitter.split_text(text)
        if not documents:
            return _split_blocks(text, chunk_size, chunk_overlap)
        for document in documents:
            context = _markdown_context(document.metadata)
            content_size = max(200, chunk_size - len(context) - 2) if context else chunk_size
            for chunk in _split_blocks(document.page_content, content_size, chunk_overlap):
                chunks.append(f"{context}\n\n{chunk}" if context else chunk)
        return _clean_chunks(chunks)

# === Chunker Interface ===
class ChunkerFactory:
    @staticmethod
    def chunk(data: str, file_extension: str) -> list[str]:
        chunker = ChunkerFactory._get_chunker(file_extension)
        settings = load_app_settings()
        chunks = chunker.chunk(data, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)
        if not chunks:
            raise IndexingError("chunking", "No chunks were created from the loaded text.")
        print(f"Total |{len(chunks)} chunks| created using {chunker.__name__}")
        return chunks
    
    @staticmethod
    def _get_chunker(file_extension):
        file_extension = file_extension.lower()
        if file_extension in [".txt"]:
            return TextChunker
        elif file_extension in [".md", ".pdf"]:
            return MarkdownChunker
        else:
            return TextChunker  # Default to TextChunker


def _markdown_context(metadata: dict) -> str:
    breadcrumbs = [str(metadata[key]).strip() for key in ("h1", "h2", "h3", "h4") if metadata.get(key)]
    if not breadcrumbs:
        return ""
    return f"Context: {' > '.join(breadcrumbs)}"


def _normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


def _clean_chunks(chunks: list[str]) -> list[str]:
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def _split_blocks(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks = []
    current = ""
    for block in _markdown_blocks(text):
        block_chunks = _split_table(block, chunk_size) if _is_markdown_table(block) else _split_long_paragraph(block, chunk_size, chunk_overlap)
        for block_chunk in block_chunks:
            candidate = _join_blocks(current, block_chunk)
            if current and len(candidate) > chunk_size:
                chunks.append(current)
                current = _overlap_text(current, chunk_overlap)
                candidate = _join_blocks(current, block_chunk)
                if current and len(candidate) > chunk_size:
                    current = ""
                    candidate = block_chunk
            current = candidate
    if current:
        chunks.append(current)
    return _clean_chunks(chunks)


def _markdown_blocks(text: str) -> list[str]:
    blocks = []
    current = []
    in_fence = False
    fence = ""

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence = marker
            elif marker == fence:
                in_fence = False

        if not in_fence and not stripped:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())
    return _clean_chunks(blocks)


def _split_long_paragraph(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    current_sentences: list[str] = []
    for sentence in _sentence_units(text):
        for piece in _split_oversized_sentence(sentence, chunk_size, chunk_overlap):
            candidate = _join_sentences(current_sentences + [piece])
            if current_sentences and len(candidate) > chunk_size:
                chunks.append(_join_sentences(current_sentences))
                current_sentences = _overlap_sentences(current_sentences, chunk_overlap)
                while current_sentences and len(_join_sentences(current_sentences + [piece])) > chunk_size:
                    current_sentences.pop(0)
            current_sentences.append(piece)

    if current_sentences:
        chunks.append(_join_sentences(current_sentences))
    return _clean_chunks(chunks)


def _sentence_units(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    return [part.strip() for part in SENTENCE_SPLIT_PATTERN.split(compact) if part.strip()]


def _split_oversized_sentence(sentence: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if len(sentence) <= chunk_size:
        return [sentence]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["; ", "；", ", ", "，", " ", ""],
    )
    return _clean_chunks(splitter.split_text(sentence))


def _overlap_sentences(sentences: list[str], chunk_overlap: int) -> list[str]:
    if chunk_overlap <= 0:
        return []
    selected = []
    total = 0
    for sentence in reversed(sentences):
        total += len(sentence) + (1 if selected else 0)
        if total > chunk_overlap:
            break
        selected.insert(0, sentence)
    return selected


def _overlap_text(text: str, chunk_overlap: int) -> str:
    if chunk_overlap <= 0 or len(text) <= chunk_overlap:
        return ""
    return text[-chunk_overlap:].lstrip()


def _join_blocks(first: str, second: str) -> str:
    return f"{first}\n\n{second}".strip() if first else second.strip()


def _join_sentences(sentences: list[str]) -> str:
    return " ".join(sentence.strip() for sentence in sentences if sentence.strip()).strip()


def _is_markdown_table(block: str) -> bool:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    return len(lines) >= 2 and "|" in lines[0] and set(lines[1].replace("|", "").strip()) <= {"-", ":", " "}


def _split_table(block: str, chunk_size: int) -> list[str]:
    lines = [line.rstrip() for line in block.splitlines() if line.strip()]
    if len(block) <= chunk_size or len(lines) <= 2:
        return [block]

    header = lines[:2]
    chunks = []
    current = header[:]
    for row in lines[2:]:
        candidate = "\n".join([*current, row])
        if len(candidate) > chunk_size and len(current) > len(header):
            chunks.append("\n".join(current))
            current = [*header, row]
        else:
            current.append(row)
    if len(current) > len(header):
        chunks.append("\n".join(current))
    return chunks



if __name__ == "__main__":
    import os

    from .loader import DataLoaderFactory

    file_path = Config.TEST_FILE_PATH
    try:
        data = DataLoaderFactory.load(file_path)
        _, ext = os.path.splitext(file_path)
        chunks = ChunkerFactory.chunk(data, ext)        
    except ValueError as e:
        print(e)

