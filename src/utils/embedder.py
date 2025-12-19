from Config import Config
from huggingface_hub import InferenceClient
from tqdm import tqdm
from functools import lru_cache
###########################################
HF_TOKEN = Config.HF_TOKEN
MODEL_ID = Config.EMBEDDING_MODEL
###########################################

# === Embedder Interface ===
# Embedding via HuggingFace Inference API
class HuggingFaceEmbedder:
    @staticmethod
    def embed(data, model_id=MODEL_ID, hf_token=HF_TOKEN,max_retries=3):
        """
        Embed chunks to vectors using HuggingFace Inference API
        data: a single text (str) or an iterable of text chunks (e.g. list[str])
        """
        if isinstance(data, str):
            data = [data]

        embeddings = []

        
        for chunk in tqdm(data, desc="Embedding chunks"):
            try:
                embedding = HuggingFaceEmbedder._embed_single_text(chunk, model_id, hf_token,max_retries)
                if embedding is not None:
                    embeddings.append(embedding)
            except Exception as e:
                print(f"Error embedding chunk: {chunk[:30]}... Error: {e}")
        return embeddings

    @staticmethod
    @lru_cache(maxsize=2048)
    def _embed_single_text(text, model_id=MODEL_ID, hf_token=HF_TOKEN, max_retries=3):
        """
        Embed a single text chunk to a vector with retry
        """
        client = InferenceClient(model=model_id, token=hf_token)
        embedding = client.feature_extraction([text])
        if embedding is not None:
            return embedding[0]
        else:
            # retry 3 times
            retry_count = 0
            while retry_count < max_retries:
                embedding = HuggingFaceEmbedder._embed_single_text(chunk, client)
                if embedding is not None:
                    embeddings.append(embedding)
                    return embedding[0]
                retry_count += 1
            print(f"Failed to embed chunk after retries: {chunk[:30]}...")
            return None


if __name__ == "__main__":
    file_path = Config.TEST_FILE_PATH
    import os
    from Loader import DataLoaderFactory
    from Chunker import ChunkerFactory
    data = DataLoaderFactory.load(file_path)
    _, ext = os.path.splitext(file_path)
    chunks = ChunkerFactory.chunk(data, ext)
    embeddings = HuggingFaceEmbedder.embed(chunks)