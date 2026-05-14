from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IndexingStage = Literal["loading", "chunking", "embedding", "storing"]


@dataclass(frozen=True)
class IndexingErrorDetail:
    stage: IndexingStage
    message: str


class IndexingError(RuntimeError):
    """User-facing indexing error with a stable pipeline stage."""

    def __init__(self, stage: IndexingStage, message: str):
        self.detail = IndexingErrorDetail(stage=stage, message=message)
        super().__init__(f"{stage.title()} failed: {message}")

    @property
    def stage(self) -> str:
        return self.detail.stage

    @property
    def message(self) -> str:
        return self.detail.message


class EmbeddingError(IndexingError):
    """Raised when the configured embedding provider cannot create vectors."""

    def __init__(self, message: str):
        super().__init__("embedding", message)
