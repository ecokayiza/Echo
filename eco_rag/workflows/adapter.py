
from typing import Iterable

from ..domain.schema import RAGRecord


class Adapter:
    """
    Normalizes retrieval output into a generation-friendly context payload.
    """

    def prepare_context(self, records: Iterable[RAGRecord]) -> list[RAGRecord]:
        return list(records)
