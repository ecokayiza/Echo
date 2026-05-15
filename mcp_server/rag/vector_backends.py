from __future__ import annotations

DEFAULT_VECTOR_BACKEND = "chroma"
SUPPORTED_VECTOR_BACKENDS = ("chroma", "faiss")


def normalize_vector_backend(value: object | None = None) -> str:
    """Normalize and validate the vector database backend name."""
    backend = str(value or DEFAULT_VECTOR_BACKEND).strip().lower()
    if backend not in SUPPORTED_VECTOR_BACKENDS:
        supported = ", ".join(SUPPORTED_VECTOR_BACKENDS)
        raise ValueError(f"Unsupported vector database backend '{value}'. Supported backends: {supported}.")
    return backend
