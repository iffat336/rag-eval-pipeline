from unittest.mock import MagicMock

from src.retrieval.query_decomposition import QueryDecomposer


def test_decompose_falls_back_to_original_question_on_error():
    retriever = MagicMock()
    decomposer = QueryDecomposer.__new__(QueryDecomposer)
    decomposer._retriever = retriever
    decomposer._llm = MagicMock()
    decomposer._chain = MagicMock()
    decomposer._chain.invoke.side_effect = RuntimeError("LLM unavailable")

    result = decomposer.decompose("How does rate limiting work?")

    assert result == ["How does rate limiting work?"]


def test_decompose_caps_at_four_sub_questions():
    decomposer = QueryDecomposer.__new__(QueryDecomposer)
    decomposer._retriever = MagicMock()
    decomposer._llm = MagicMock()
    decomposer._chain = MagicMock()
    decomposer._chain.invoke.return_value = {
        "sub_questions": [f"sub-question {i}" for i in range(6)]
    }

    result = decomposer.decompose("A very complex multi-part question")

    assert len(result) == 4
