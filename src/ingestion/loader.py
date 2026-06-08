from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from src.config import CHUNK_OVERLAP, CHUNK_SIZE


def load_documents(docs_dir: str | Path) -> list[Document]:
    """Read every .md/.txt file in docs_dir into a Document with source metadata."""
    docs_dir = Path(docs_dir)
    documents = []
    for path in sorted(docs_dir.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        documents.append(
            Document(page_content=text, metadata={"source": path.relative_to(docs_dir).as_posix()})
        )
    return documents


def chunk_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = f"{chunk.metadata['source']}::{i}"
    return chunks
