"""End-to-end RAG: decompose -> hybrid retrieve+rerank -> generate a grounded answer."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.config import LLM_MODEL
from src.ingestion.loader import chunk_documents, load_documents
from src.retrieval.hybrid_search import HybridRetriever
from src.retrieval.query_decomposition import QueryDecomposer

_ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Answer the user's question using ONLY the provided context. "
            "If the context doesn't contain the answer, say you don't know — "
            "do not make anything up. Cite sources inline using their "
            "[source] tag.",
        ),
        (
            "human",
            "Context:\n{context}\n\nQuestion: {question}",
        ),
    ]
)


@dataclass
class RagResult:
    question: str
    answer: str
    sub_questions: list[str]
    contexts: list[Document]


def _format_context(docs: list[Document]) -> str:
    return "\n\n".join(
        f"[{doc.metadata.get('source', 'unknown')}]\n{doc.page_content}" for doc in docs
    )


class RagPipeline:
    def __init__(self, docs_dir: str = "data/docs", llm: ChatOpenAI | None = None):
        corpus = chunk_documents(load_documents(docs_dir))
        self._retriever = HybridRetriever(corpus)
        self._llm = llm or ChatOpenAI(model=LLM_MODEL, temperature=0)
        self._decomposer = QueryDecomposer(self._retriever, llm=self._llm)
        self._chain = _ANSWER_PROMPT | self._llm

    def answer(self, question: str) -> RagResult:
        sub_questions, contexts = self._decomposer.retrieve(question)
        response = self._chain.invoke(
            {"context": _format_context(contexts), "question": question}
        )
        return RagResult(
            question=question,
            answer=response.content,
            sub_questions=sub_questions,
            contexts=contexts,
        )


if __name__ == "__main__":
    import sys

    pipeline = RagPipeline()
    question = " ".join(sys.argv[1:]) or "What is this project about?"
    result = pipeline.answer(question)
    print(f"Sub-questions: {result.sub_questions}\n")
    print(f"Answer:\n{result.answer}\n")
    print("Sources:", [doc.metadata.get("source") for doc in result.contexts])
