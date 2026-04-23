"""ChromaDB vector store — one collection per platform."""
from __future__ import annotations

import uuid
from functools import lru_cache
from typing import TYPE_CHECKING

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.config import get_settings

if TYPE_CHECKING:
    from platforms.models import PlatformContextChunk


class VectorStore:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedder = None  # lazy-loaded

    def _get_embedder(self):
        if self._embedder is None:
            from rag.embedder import get_embedder
            self._embedder = get_embedder()
        return self._embedder

    def _collection(self, platform_id: str):
        """Get or create a ChromaDB collection for this platform."""
        return self._client.get_or_create_collection(
            name=f"platform_{platform_id}",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, platform_id: str, chunks: list[PlatformContextChunk]) -> None:
        collection = self._collection(platform_id)
        embedder = self._get_embedder()
        texts = [c.content for c in chunks]
        embeddings = embedder.encode(texts, convert_to_numpy=True).tolist()
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [{"section": c.section, "platform_id": platform_id} for c in chunks]
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def query(
        self,
        platform_id: str,
        query_text: str,
        n_results: int = 5,
        section_filter: str | None = None,
    ) -> list[str]:
        """Return top-k relevant context chunks for a query."""
        collection = self._collection(platform_id)
        embedder = self._get_embedder()
        query_embedding = embedder.encode([query_text], convert_to_numpy=True).tolist()

        if section_filter:
            where = {"$and": [{"platform_id": platform_id}, {"section": section_filter}]}
        else:
            where = {"platform_id": platform_id}

        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(n_results, self.count_chunks(platform_id) or 1),
            where=where,
            include=["documents"],
        )
        docs = results.get("documents", [[]])[0]
        return docs

    def count_chunks(self, platform_id: str) -> int:
        try:
            return self._collection(platform_id).count()
        except Exception:
            return 0

    def delete_platform(self, platform_id: str) -> None:
        try:
            self._client.delete_collection(f"platform_{platform_id}")
        except Exception:
            pass

    def get_chunks_by_section(self, platform_id: str) -> dict[str, list[str]]:
        """Return all stored chunks grouped by section, ordered by insertion."""
        collection = self._collection(platform_id)
        total = collection.count()
        if total == 0:
            return {}
        results = collection.get(
            where={"platform_id": platform_id},
            include=["documents", "metadatas"],
        )
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        grouped: dict[str, list[str]] = {}
        for doc, meta in zip(docs, metas):
            section = meta.get("section", "unknown")
            grouped.setdefault(section, []).append(doc)
        return grouped

    def delete_section(self, platform_id: str, section: str) -> None:
        collection = self._collection(platform_id)
        results = collection.get(where={"section": section}, include=[])
        ids = results.get("ids", [])
        if ids:
            collection.delete(ids=ids)


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    return VectorStore()
