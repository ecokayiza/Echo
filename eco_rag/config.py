from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class Config:
    ROOT_DIR = ROOT_DIR
    MODELS_PATH = ROOT_DIR / "models.json"
    DATA_DIR = ROOT_DIR / "data"
    DB_PATH = ROOT_DIR / "db"
    MEMORY_DIR = ROOT_DIR / "memory"
    CHAT_MEMORY_DIR = MEMORY_DIR / "chat_sessions"
    MEMORY_ARTIFACTS_DIR = MEMORY_DIR / "artifacts"
    TEST_FILE_PATH = DATA_DIR / "C1" / "markdown" / "easy-rl-chapter1.md"

    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"

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
