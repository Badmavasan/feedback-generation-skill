from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # API security
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8  # 8 hours

    # Admin credentials (used for JWT login via frontend)
    admin_username: str = "admin"
    admin_password: str = "change-me-in-production"

    # API keys for platform clients (comma-separated: key1,key2,...)
    # Each platform registers its API key in PLATFORM_API_KEYS env var
    # Format: "platform_id:key,platform_id2:key2"
    platform_api_keys: str = ""

    # Model API keys
    anthropic_api_key: str = ""
    mistral_api_key: str = ""
    google_api_key: str = ""  # For Gemini + Imagen

    # Claude orchestrator model
    orchestrator_model: str = "claude-sonnet-4-6"

    # Mistral feedback model
    mistral_model: str = "mistral-large-latest"

    # Gemini model for annotation
    gemini_model: str = "gemini-2.0-flash"
    imagen_model: str = "imagen-3.0-generate-002"

    # Image annotation: max iterations before accepting best result
    image_max_iterations: int = 3

    # Text feedback: max orchestrator-driven regeneration attempts per component
    text_max_iterations: int = 3

    # PostgreSQL connection (asyncpg) — local feedback DB
    database_url: str = "postgresql+asyncpg://feedback:feedback@db:5432/feedback"

    # AlgoPython source database (read-only) — leave empty to disable
    algopython_database_url: str = ""

    # ChromaDB storage path
    chroma_persist_dir: str = "./data/chroma"

    # Embedding model for RAG
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_platform_api_keys_map(self) -> dict[str, str]:
        """Parse 'platform_id:key,platform_id2:key2' into a dict."""
        if not self.platform_api_keys:
            return {}
        result = {}
        for entry in self.platform_api_keys.split(","):
            entry = entry.strip()
            if ":" in entry:
                pid, key = entry.split(":", 1)
                result[pid.strip()] = key.strip()
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()
