
from typing import Iterable

from ..domain.schema import RAGRecord


class Retriever:
    """
    Thin wrapper interface for retrieval implementations.
    """

    def retrieve(self, query: str) -> Iterable[RAGRecord]:
        raise NotImplementedError("Provide a retrieval implementation for the active data source.")
