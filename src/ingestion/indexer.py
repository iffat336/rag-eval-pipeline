"""Embed document chunks and upsert them into a Qdrant collection."""

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from src.config import (
    EMBEDDING_MODEL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
)
from src.ingestion.loader import chunk_documents, load_documents

EMBEDDING_DIM = 1536  # text-embedding-3-small


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def ensure_collection(client: QdrantClient, recreate: bool = False) -> None:
    exists = client.collection_exists(QDRANT_COLLECTION)
    if exists and recreate:
        client.delete_collection(QDRANT_COLLECTION)
        exists = False
    if not exists:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def index_documents(docs_dir: str, recreate: bool = False) -> int:
    """Load, chunk, embed and upsert documents from docs_dir. Returns chunk count."""
    documents: list[Document] = chunk_documents(load_documents(docs_dir))
    if not documents:
        raise ValueError(f"No .md/.txt documents found under {docs_dir}")

    client = get_qdrant_client()
    ensure_collection(client, recreate=recreate)

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    store = QdrantVectorStore(
        client=client,
        collection_name=QDRANT_COLLECTION,
        embedding=embeddings,
    )
    ids = [doc.metadata["chunk_id"] for doc in documents]
    store.add_documents(documents, ids=ids)
    return len(documents)


if __name__ == "__main__":
    import sys

    docs_dir = sys.argv[1] if len(sys.argv) > 1 else "data/docs"
    count = index_documents(docs_dir, recreate=True)
    print(f"Indexed {count} chunks from {docs_dir} into collection '{QDRANT_COLLECTION}'")
