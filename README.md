# RAG Eval Pipeline

A production-style Retrieval-Augmented Generation system with hybrid search,
query decomposition, and an automated RAGAS evaluation suite that runs in CI
on every pull request.

Built to demo end-to-end RAG engineering: not just "wire up an LLM to a vector
store," but the retrieval-quality and regression-testing concerns that come up
once a RAG system needs to stay reliable as the corpus and prompts change.

## What it does

- **Hybrid search with reranking** — fuses dense (semantic, via OpenAI
  embeddings + Qdrant) and sparse (BM25 keyword) retrieval, then reranks the
  merged candidates with a cross-encoder (`ms-marco-MiniLM-L-6-v2`). Dense
  search alone misses literal matches like error codes or product names; BM25
  alone misses semantically-related but differently-worded passages. Fusing
  both and reranking the union gets the best of each.
- **Query decomposition** — an LLM splits compound questions ("How does X
  compare to Y, and which should I use for Z?") into independent
  sub-questions, retrieves for each separately, and merges deduplicated
  results. This measurably improves context recall on multi-part questions
  that no single chunk can answer.
- **RAGAS evaluation suite** — scores every pipeline run on **faithfulness**
  (hallucination detection), **answer relevancy**, **context precision**, and
  **context recall** against a hand-labeled question/ground-truth set. Scores
  are checked against thresholds, turning "does this still work" into a
  pass/fail gate rather than a vibes check.
- **CI/CD via GitHub Actions** — every PR that touches retrieval, generation,
  or the source corpus spins up a Qdrant instance, re-indexes the docs, runs
  the full RAGAS suite, uploads the JSON report as an artifact, and posts a
  summary to the PR. A regression in retrieval or generation quality fails
  the build before it merges.
- **LangSmith tracing** — every chain run (decomposition, retrieval,
  generation, and eval) is traced for step-by-step debugging of *why* an
  answer was wrong: bad retrieval vs. bad generation vs. bad decomposition.

## Architecture

```
                    ┌────────────────────┐
   question ──────► │  Query Decomposer   │── sub-questions ──┐
                    └────────────────────┘                    │
                                                               ▼
                                                   ┌──────────────────────┐
                                                   │   Hybrid Retriever    │
                                                   │  dense (Qdrant) ─┐    │
                                                   │  sparse (BM25)  ─┼─►  │── fused, reranked
                                                   │  cross-encoder rerank │    passages
                                                   └──────────────────────┘
                                                               │
                                                               ▼
                                                   ┌──────────────────────┐
                                                   │   Generation (LLM)    │── grounded, cited answer
                                                   └──────────────────────┘
```

## Stack

LangChain · Qdrant · RAGAS · LangSmith · OpenAI (embeddings + LLM) ·
sentence-transformers (cross-encoder reranking) · GitHub Actions

## Project layout

```
src/
  ingestion/        document loading, chunking, embedding, Qdrant indexing
  retrieval/        hybrid (dense+sparse) search, reranking, query decomposition
  generation/       the end-to-end RAG chain (decompose -> retrieve -> generate)
data/docs/          sample knowledge base the pipeline indexes (fictional API docs)
eval/
  eval_dataset.json  hand-labeled question/ground-truth pairs
  run_ragas_eval.py  scores the pipeline against RAGAS metrics + thresholds
  results/           timestamped JSON eval reports (CI artifacts land here)
.github/workflows/   CI pipeline that runs the eval suite on every PR
```

## Running it locally

1. **Start Qdrant** (or point `QDRANT_URL` at a cloud instance):
   ```bash
   docker compose up -d
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment** — copy `.env.example` to `.env` and fill in your
   OpenAI (and optionally LangSmith) API keys.

4. **Index the sample corpus**:
   ```bash
   python -m src.ingestion.indexer data/docs
   ```

5. **Ask a question**:
   ```bash
   python -m src.generation.rag_chain "How does rate limiting differ between live and test API keys, and can I get my limit raised?"
   ```

6. **Run the evaluation suite**:
   ```bash
   python -m eval.run_ragas_eval
   ```
   This scores the pipeline against `eval/eval_dataset.json`, writes a
   timestamped report to `eval/results/`, and exits non-zero if any metric
   falls below its threshold (see `THRESHOLDS` in `eval/run_ragas_eval.py`).

## Running tests

```bash
pytest
```

## Notes on the sample corpus

`data/docs/` contains a small fictional API documentation set (auth, rate
limits, webhooks, billing) for a product called "Nimbus." It's deliberately
the kind of content that has cross-references between documents (e.g. rate
limit *types* are defined in one file but referenced from another), which is
exactly the scenario hybrid search and query decomposition are meant to
handle well. Swap in your own `.md`/`.txt` files and re-run the indexer to
point this at a different knowledge base.
