from pathlib import Path

from src.ingestion.loader import chunk_documents, load_documents

DOCS_DIR = Path(__file__).parent.parent / "data" / "docs"


def test_load_documents_reads_markdown_files():
    docs = load_documents(DOCS_DIR)
    assert len(docs) == 4
    sources = {doc.metadata["source"] for doc in docs}
    assert sources == {
        "authentication.md",
        "billing.md",
        "rate_limits.md",
        "webhooks.md",
    }


def test_chunk_documents_assigns_unique_ids():
    chunks = chunk_documents(load_documents(DOCS_DIR))
    assert len(chunks) > len(load_documents(DOCS_DIR))

    ids = [chunk.metadata["chunk_id"] for chunk in chunks]
    assert len(ids) == len(set(ids))
    assert all(chunk.metadata["source"] in chunk_id for chunk_id, chunk in zip(ids, chunks))
