from .assembler import Assembler
from .database_registry import (
    DatabaseSettings,
    DatabaseSettingsDocument,
    create_database_settings,
    delete_database_settings,
    ensure_database_settings_document,
    get_active_database_settings,
    list_database_settings,
    rename_database_settings,
    resolve_database_embedding_settings,
    select_database_settings,
)
from .embedder import HuggingFaceEmbedder, OpenAICompatibleEmbedder
from .errors import EmbeddingError, IndexingError

try:
    from .chunker import ChunkerFactory, MarkdownChunker, TextChunker
except ModuleNotFoundError:
    ChunkerFactory = None
    MarkdownChunker = None
    TextChunker = None

try:
    from .loader import DataLoaderFactory, MarkDownDataLoader, PDFDataLoader
except ModuleNotFoundError:
    DataLoaderFactory = None
    MarkDownDataLoader = None
    PDFDataLoader = None

try:
    from .vector_database import VectorDatabase
except ModuleNotFoundError:
    VectorDatabase = None

__all__ = [
    "Assembler",
    "create_database_settings",
    "ChunkerFactory",
    "DataLoaderFactory",
    "DatabaseSettings",
    "DatabaseSettingsDocument",
    "delete_database_settings",
    "HuggingFaceEmbedder",
    "EmbeddingError",
    "ensure_database_settings_document",
    "get_active_database_settings",
    "IndexingError",
    "list_database_settings",
    "OpenAICompatibleEmbedder",
    "MarkDownDataLoader",
    "MarkdownChunker",
    "PDFDataLoader",
    "rename_database_settings",
    "resolve_database_embedding_settings",
    "select_database_settings",
    "TextChunker",
    "VectorDatabase",
]
