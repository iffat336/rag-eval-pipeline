"""Hybrid retrieval: fuse dense (semantic) and sparse (BM25 keyword) search,
then rerank the merged candidates with a cross-encoder.

Dense search finds passages that are *semantically* close even when wording
differs; BM25 finds passages with strong literal term overlap (good for
acronyms, product names, error codes). Fusing both and reranking the union
catches cases either retriever alone would miss.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from sentence_transformers import CrossEncoder

from src.config import (
    DENSE_WEIGHT,
    EMBEDDING_MODEL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
    RERANK_TOP_K,
    RETRIEVAL_TOP_K,
)

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_reranker: CrossEncoder | None = None


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


def _normalize(scores: list[float]) -> list[float]:
    if not scores:
        return scores
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


class HybridRetriever:
    """Combines a Qdrant dense retriever with an in-memory BM25 retriever,
    fuses scores, and reranks the result with a cross-encoder."""

    def __init__(self, corpus: list[Document]):
        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
        self._dense_store = QdrantVectorStore.from_existing_collection(
            embedding=embeddings,
            collection_name=QDRANT_COLLECTION,
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
        )
        self._bm25 = BM25Retriever.from_documents(corpus)
        self._bm25.k = RETRIEVAL_TOP_K

    def _dense_search(self, query: str) -> list[tuple[Document, float]]:
        return self._dense_store.similarity_search_with_relevance_scores(
            query, k=RETRIEVAL_TOP_K
        )

    def _sparse_search(self, query: str) -> list[Document]:
        return self._bm25.invoke(query)

    def _fuse(self, query: str) -> list[Document]:
        dense_hits = self._dense_search(query)
        sparse_hits = self._sparse_search(query)

        dense_scores = _normalize([score for _, score in dense_hits])
        # BM25Retriever doesn't expose raw scores via .invoke; approximate rank-based
        # scores so sparse hits can be fused on the same [0, 1] scale as dense hits.
        sparse_scores = _normalize([len(sparse_hits) - i for i in range(len(sparse_hits))])

        fused: dict[str, dict] = {}
        for (doc, _), score in zip(dense_hits, dense_scores):
            key = doc.metadata.get("chunk_id", doc.page_content[:80])
            fused[key] = {"doc": doc, "score": DENSE_WEIGHT * score}
        for doc, score in zip(sparse_hits, sparse_scores):
            key = doc.metadata.get("chunk_id", doc.page_content[:80])
            entry = fused.setdefault(key, {"doc": doc, "score": 0.0})
            entry["score"] += (1 - DENSE_WEIGHT) * score

        ranked = sorted(fused.values(), key=lambda e: e["score"], reverse=True)
        return [e["doc"] for e in ranked[:RETRIEVAL_TOP_K]]

    def _rerank(self, query: str, candidates: list[Document]) -> list[Document]:
        if not candidates:
            return candidates
        reranker = _get_reranker()
        pairs = [[query, doc.page_content] for doc in candidates]
        scores = reranker.predict(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in ranked[:RERANK_TOP_K]]

    def retrieve(self, query: str) -> list[Document]:
        candidates = self._fuse(query)
        return self._rerank(query, candidates)
