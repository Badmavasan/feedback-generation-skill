"""Lazy-loaded sentence-transformer embedder (singleton)."""
from functools import lru_cache
from core.config import get_settings


@lru_cache(maxsize=1)
def get_embedder():
    from sentence_transformers import SentenceTransformer
    settings = get_settings()
    return SentenceTransformer(settings.embedding_model)
