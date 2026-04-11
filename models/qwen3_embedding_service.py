from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from huggingface_hub import snapshot_download
from pydantic import BaseModel

MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
MODEL_DIR = Path(__file__).resolve().parent / "Qwen3-Embedding-0.6B"
MAX_LENGTH = int(os.getenv("EMBEDDING_MAX_LENGTH", "8192"))


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str | None = None
    dimensions: int | None = None


def ensure_model_downloaded() -> Path:
    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    required_files = {"config.json", "tokenizer.json"}
    if all((MODEL_DIR / filename).exists() for filename in required_files):
        return MODEL_DIR
    snapshot_download(repo_id=MODEL_NAME, local_dir=str(MODEL_DIR), local_dir_use_symlinks=False)
    return MODEL_DIR


def create_app() -> FastAPI:
    app = FastAPI(
        title="Qwen3 Embedding Service",
        version="0.1.0",
        description="Standalone OpenAI-compatible embedding server for Qwen3 embeddings.",
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "model": MODEL_NAME, "model_dir": str(MODEL_DIR)}

    @app.post("/v1/embeddings")
    def embeddings(payload: EmbeddingRequest):
        try:
            inputs = payload.input if isinstance(payload.input, list) else [payload.input]
            return build_openai_embedding_response(inputs, model=payload.model or MODEL_NAME, dimensions=payload.dimensions)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def build_openai_embedding_response(inputs: list[str], *, model: str, dimensions: int | None = None) -> dict[str, Any]:
    vectors, prompt_tokens = embed_texts(inputs, dimensions=dimensions)
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "embedding": vector,
                "index": index,
            }
            for index, vector in enumerate(vectors)
        ],
        "model": model,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "total_tokens": prompt_tokens,
        },
    }


def embed_texts(texts: list[str], *, dimensions: int | None = None) -> tuple[list[list[float]], int]:
    cleaned = [str(text).strip() for text in texts if str(text).strip()]
    if not cleaned:
        return [], 0

    torch = _torch()
    F = torch.nn.functional
    tokenizer, model, device = _model_bundle()

    with torch.no_grad():
        batch = tokenizer(
            cleaned,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        batch = {key: value.to(device) for key, value in batch.items()}
        outputs = model(**batch)
        vectors = _last_token_pool(outputs.last_hidden_state, batch["attention_mask"])
        vectors = F.normalize(vectors, p=2, dim=1)
        if isinstance(dimensions, int) and 0 < dimensions < vectors.shape[1]:
            vectors = F.normalize(vectors[:, :dimensions], p=2, dim=1)
        prompt_tokens = int(batch["attention_mask"].sum().item())
    return vectors.cpu().tolist(), prompt_tokens


def _last_token_pool(last_hidden_state, attention_mask):
    left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
    if left_padding:
        return last_hidden_state[:, -1]
    sequence_lengths = attention_mask.sum(dim=1) - 1
    batch_size = last_hidden_state.shape[0]
    return last_hidden_state[range(batch_size), sequence_lengths]


@lru_cache(maxsize=1)
def _model_bundle():
    try:
        from transformers import AutoModel, AutoTokenizer
    except ModuleNotFoundError as exc:
        raise ValueError("Install 'transformers>=4.51.0' in the environment running this service.") from exc

    torch = _torch()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    ensure_model_downloaded()
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), padding_side="left")
    model = AutoModel.from_pretrained(str(MODEL_DIR), dtype=dtype).to(device)
    model.eval()
    return tokenizer, model, device


@lru_cache(maxsize=1)
def _torch():
    try:
        import torch
    except ModuleNotFoundError as exc:
        raise ValueError("Install 'torch' in the environment running this service.") from exc
    return torch


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("EMBEDDING_SERVICE_HOST", "0.0.0.0"), port=int(os.getenv("EMBEDDING_SERVICE_PORT", "8091")))
