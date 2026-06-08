"""Run the RAG pipeline over the labeled eval set and score it with RAGAS.

Scores four axes that catch different failure modes:
  - faithfulness:        does the answer avoid claims unsupported by context? (hallucination)
  - answer_relevancy:    does the answer actually address the question asked?
  - context_precision:   are the retrieved passages ranked with the relevant ones first?
  - context_recall:      did retrieval surface everything needed to answer fully?

Faithfulness and context metrics are what make this an *eval suite* rather than
a vibes check — they isolate whether failures come from retrieval or generation.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

from src.generation.rag_chain import RagPipeline

EVAL_DATASET_PATH = Path(__file__).parent / "eval_dataset.json"
RESULTS_DIR = Path(__file__).parent / "results"

# Minimum acceptable scores. CI fails the build if any metric drops below its
# threshold, turning eval results into a regression gate rather than a report.
THRESHOLDS = {
    "faithfulness": 0.80,
    "answer_relevancy": 0.80,
    "context_precision": 0.70,
    "context_recall": 0.70,
}


def build_eval_dataset(pipeline: RagPipeline, cases: list[dict]) -> Dataset:
    questions, answers, contexts, ground_truths = [], [], [], []
    for case in cases:
        result = pipeline.answer(case["question"])
        questions.append(case["question"])
        answers.append(result.answer)
        contexts.append([doc.page_content for doc in result.contexts])
        ground_truths.append(case["ground_truth"])

    return Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )


def run() -> dict:
    cases = json.loads(EVAL_DATASET_PATH.read_text(encoding="utf-8"))
    pipeline = RagPipeline()

    dataset = build_eval_dataset(pipeline, cases)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )

    scores = {name: float(value) for name, value in result.items()}
    failures = {
        name: scores[name]
        for name, threshold in THRESHOLDS.items()
        if scores.get(name, 0.0) < threshold
    }

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scores": scores,
        "thresholds": THRESHOLDS,
        "failures": failures,
        "passed": not failures,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"eval_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nSaved report to {out_path}")
    return report


if __name__ == "__main__":
    report = run()
    sys.exit(0 if report["passed"] else 1)
