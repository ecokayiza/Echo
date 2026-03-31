import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional local dependency during bootstrap
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv()


class Config:
    API_KEY = os.getenv("API_KEY")
    BASE_URL = os.getenv("BASE_URL")
    MODEL = os.getenv("MODEL")
    HF_TOKEN = os.getenv("HF_TOKEN")

    ROOT_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = ROOT_DIR / "data"
    DB_PATH = ROOT_DIR / "db"
    MEMORY_DIR = ROOT_DIR / "memory"
    CHAT_MEMORY_DIR = MEMORY_DIR / "chat_sessions"
    MEMORY_ARTIFACTS_DIR = MEMORY_DIR / "artifacts"
    TEST_FILE_PATH = DATA_DIR / "C1" / "markdown" / "easy-rl-chapter1.md"

    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    EMBEDDING_MODEL = "BAAI/bge-m3"

    @staticmethod
    def get_relative_path(file_path, data_dir=DATA_DIR):
        try:
            rel_path = Path(file_path).relative_to(data_dir)
            rel_path = str(rel_path).replace("\\", "/")
        except ValueError:
            rel_path = Path(file_path).name
        return rel_path


if __name__ == "__main__":
    print(f"ROOT_DIR: {Config.ROOT_DIR}")
    print(f"model: {Config.MODEL}")
