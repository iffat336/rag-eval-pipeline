"""Break a complex multi-part question into independent sub-questions,
retrieve passages for each, and merge the results.

Single-pass retrieval struggles with questions like "How does X compare to Y,
and which should I use for Z?" because no single chunk covers all three
sub-topics. Decomposing into separate sub-questions lets the retriever target
each sub-topic directly, which improves context recall on compound questions.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.config import LLM_MODEL
from src.retrieval.hybrid_search import HybridRetriever

_DECOMPOSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You break user questions into the minimal set of standalone "
            "sub-questions needed to answer them fully. "
            "If the question is already simple and single-topic, return it "
            "unchanged as the only item. "
            "Respond with a JSON object: {{\"sub_questions\": [\"...\", ...]}}. "
            "Return at most 4 sub-questions.",
        ),
        ("human", "{question}"),
    ]
)


class QueryDecomposer:
    def __init__(self, retriever: HybridRetriever, llm: ChatOpenAI | None = None):
        self._retriever = retriever
        self._llm = llm or ChatOpenAI(model=LLM_MODEL, temperature=0)
        self._chain = _DECOMPOSE_PROMPT | self._llm | JsonOutputParser()

    def decompose(self, question: str) -> list[str]:
        try:
            result = self._chain.invoke({"question": question})
            sub_questions = result.get("sub_questions") or [question]
        except Exception:
            sub_questions = [question]
        return sub_questions[:4] or [question]

    def retrieve(self, question: str) -> tuple[list[str], list[Document]]:
        """Returns (sub_questions, deduplicated merged passages)."""
        sub_questions = self.decompose(question)

        seen: set[str] = set()
        merged: list[Document] = []
        for sub_q in sub_questions:
            for doc in self._retriever.retrieve(sub_q):
                key = doc.metadata.get("chunk_id", doc.page_content[:80])
                if key not in seen:
                    seen.add(key)
                    merged.append(doc)
        return sub_questions, merged
