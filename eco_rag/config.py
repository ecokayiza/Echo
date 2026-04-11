from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class Config:
    ROOT_DIR = ROOT_DIR
    MODELS_PATH = ROOT_DIR / "models.json"
    SETTINGS_PATH = ROOT_DIR / "settings.json"
    DATA_DIR = ROOT_DIR / "data"
    DB_PATH = ROOT_DIR / "db"
    MEMORY_DIR = ROOT_DIR / "memory"
    DATABASES_PATH = MEMORY_DIR / "databases.json"
    CHAT_MEMORY_DIR = MEMORY_DIR / "chat_sessions"
    MEMORY_ARTIFACTS_DIR = MEMORY_DIR / "artifacts"
    WORKFLOW_DRAFT_DIR = MEMORY_DIR / "workflow_live"
    TEST_FILE_PATH = DATA_DIR / "C1" / "markdown" / "easy-rl-chapter1.md"

    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
    LOCAL_EMBEDDING_MODEL_NAME = "Local Qwen3 Embedding"
    LOCAL_EMBEDDING_HOST = "127.0.0.1"
    LOCAL_EMBEDDING_PORT = 8091
    LOCAL_EMBEDDING_BASE_URL = f"http://{LOCAL_EMBEDDING_HOST}:{LOCAL_EMBEDDING_PORT}/v1"
    LOCAL_EMBEDDING_API_KEY = "local-embedding-service"

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
    print(f"models path: {Config.MODELS_PATH}")
    print(f"settings path: {Config.SETTINGS_PATH}")
