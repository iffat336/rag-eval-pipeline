# RAG Eval Pipeline

A production-style Retrieval-Augmented Generation (RAG) system with **hybrid
search + reranking**, **LLM-driven query decomposition**, and a **RAGAS-based
evaluation suite that runs as a quality gate in CI** on every pull request.

This isn't a "wire an LLM to a vector store and call it done" demo. It's built
around the questions that actually determine whether a RAG system survives
contact with production: *Is retrieval finding the right passages? Is the
model answering from those passages or hallucinating? And — critically — how
do we know if a prompt change, a chunking change, or a model swap makes things
better or worse?* The answer here is automated evaluation wired directly into
the development loop, not a one-off notebook you run before a demo.

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Why these design choices](#why-these-design-choices)
  - [Why hybrid search instead of pure semantic search](#why-hybrid-search-instead-of-pure-semantic-search)
  - [Why rerank after fusion](#why-rerank-after-fusion)
  - [Why query decomposition](#why-query-decomposition)
  - [Why RAGAS instead of "looks right to me"](#why-ragas-instead-of-looks-right-to-me)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Getting started](#getting-started)
- [Usage](#usage)
- [Evaluation suite in depth](#evaluation-suite-in-depth)
- [CI/CD pipeline](#cicd-pipeline)
- [Configuration reference](#configuration-reference)
- [Running tests](#running-tests)
- [Extending this project](#extending-this-project)
- [Notes on the sample corpus](#notes-on-the-sample-corpus)
- [Troubleshooting](#troubleshooting)

---

## What it does

- **Hybrid search with cross-encoder reranking** — fuses dense (semantic,
  OpenAI embeddings stored in Qdrant) and sparse (BM25 keyword) retrieval into
  a single ranked candidate list, then reranks that fused list with a
  cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) before handing the
  top passages to the generator.
- **LLM-driven query decomposition** — compound questions ("How does X compare
  to Y, and which should I use for Z?") are split by an LLM into independent
  sub-questions. Each sub-question is retrieved separately and the
  deduplicated results are merged, so no single sub-topic gets crowded out of
  the context window by another.
- **RAGAS evaluation suite** — every run is scored on four axes —
  **faithfulness**, **answer relevancy**, **context precision**, and **context
  recall** — against a hand-labeled question/ground-truth dataset
  (`eval/eval_dataset.json`). Scores are checked against configurable
  thresholds, so "did this change break anything?" has a yes/no answer instead
  of a vibe.
- **CI/CD via GitHub Actions** — every pull request that touches retrieval,
  generation, prompts, or the source corpus automatically: spins up a fresh
  Qdrant instance, re-indexes the documents, runs the full RAGAS suite,
  uploads the JSON report as a downloadable artifact, and posts a results
  summary directly on the PR. A quality regression fails the build *before* it
  merges — the same philosophy as a unit-test gate, applied to LLM behavior.
- **LangSmith tracing** — every chain invocation (decomposition → retrieval →
  reranking → generation → evaluation) is traced end-to-end, so when an answer
  is wrong you can see exactly *where* it went wrong: bad sub-questions, bad
  retrieval, bad reranking, or bad generation from good context.

## Architecture

```
                     ┌─────────────────────┐
    question ──────► │   Query Decomposer   │── sub-questions ──┐
                     │  (LLM splits compound│                   │
                     │   questions)         │                   │
                     └─────────────────────┘                   │
                                                                 ▼
                                                   ┌───────────────────────────┐
                                                   │      Hybrid Retriever      │
                                                   │                            │
                                                   │  dense search (Qdrant) ──┐ │
                                                   │  sparse search (BM25)  ──┼─┤── score fusion
                                                   │                          │ │   (weighted)
                                                   │  cross-encoder reranker ◄┘ │
                                                   └───────────────────────────┘
                                                                 │
                                                     deduplicated, reranked
                                                          top-k passages
                                                                 │
                                                                 ▼
                                                   ┌───────────────────────────┐
                                                   │     Generation (LLM)       │
                                                   │  grounded answer + cited   │
                                                   │  sources, "I don't know"   │
                                                   │  if context is insufficient│
                                                   └───────────────────────────┘
                                                                 │
                                                                 ▼
                                                   ┌───────────────────────────┐
                                                   │   RAGAS Evaluation Suite   │
                                                   │  faithfulness · relevancy  │
                                                   │  context precision/recall  │
                                                   │  → pass/fail vs thresholds │
                                                   └───────────────────────────┘
```

**Request-time flow** (what happens when you ask a question):
1. The **Query Decomposer** asks an LLM whether the question has multiple
   independent parts. Simple questions pass through unchanged; compound ones
   are split into up to four sub-questions.
2. Each sub-question goes through the **Hybrid Retriever**: a dense
   (embedding-similarity) search against Qdrant and a sparse (BM25 keyword)
   search run in parallel, their normalized scores are fused with a
   configurable weight, and the fused candidate list is reranked by a
   cross-encoder that scores each (query, passage) pair jointly — a much more
   accurate relevance signal than embedding similarity alone, but too slow to
   run over the whole corpus, hence "retrieve broad, then rerank narrow."
3. Results across all sub-questions are deduplicated by chunk ID and merged.
4. The **Generator** receives the merged, reranked passages with source tags
   and produces a grounded answer, instructed to say "I don't know" rather
   than fabricate when the context is insufficient.

**Evaluation-time flow** (what CI runs on every PR): the same pipeline runs
against a fixed set of hand-labeled questions, and RAGAS scores the
question/answer/context/ground-truth quadruple on four independent axes (see
[Evaluation suite in depth](#evaluation-suite-in-depth)).

## Why these design choices

### Why hybrid search instead of pure semantic search

Dense (embedding) search is excellent at matching *meaning* — it'll connect
"how do I get billed twice for one cycle" to a passage about "duplicate
invoice charges" even with zero word overlap. But it's surprisingly weak at
matching exact tokens: error codes (`key_revoked`), product-specific terms
(`nb_live_`), version numbers, and acronyms often get diluted in the embedding
space among semantically-similar-but-wrong passages.

BM25 (sparse/keyword search) is the mirror image: it nails exact-token
matches but has no notion of meaning — it won't connect a question about
"getting locked out" to a passage about "key revocation" if they don't share
vocabulary.

Fusing both retrieves a candidate set that's resilient to either failure mode,
and the fusion weight (`DENSE_WEIGHT` in `src/config.py`) is a single tunable
knob for shifting the balance toward meaning-matching or token-matching
depending on your corpus.

### Why rerank after fusion

Embedding similarity and BM25 scores are both computed *independently* per
passage — neither actually looks at the query and the passage together. A
cross-encoder does: it takes the (query, passage) pair as joint input and
produces a single relevance score, which is far more accurate at judging "does
this passage actually answer this question" than any independent-encoding
method. The catch is that it's too slow to run over an entire corpus (it's
O(passages) inference calls per query). The standard solution — used here —
is **retrieve broad with cheap methods, then rerank narrow with an expensive
one**: pull the top ~20 candidates via fused dense+sparse search, then let the
cross-encoder pick the best 5 from those 20.

### Why query decomposition

Single-pass retrieval implicitly assumes one query embedding (or keyword set)
can represent everything the user is asking about. That assumption breaks down
on compound questions — "What's the difference between OAuth and service
account auth, and which should I use for a CI pipeline?" actually contains two
distinct information needs, and a single retrieval pass tends to either
over-index on one sub-topic or return generically-relevant-but-not-specific
passages for both. Decomposing into independent sub-questions lets the
retriever target each information need directly. This is the single biggest
lever for **context recall** on multi-part, comparison, and "how do these
relate" style questions — which is exactly what real users ask.

### Why RAGAS instead of "looks right to me"

Manually eyeballing RAG outputs doesn't scale and doesn't catch regressions —
a prompt tweak that improves answers for the five questions you happened to
test can silently degrade ten others. RAGAS turns evaluation into something
that scales and survives change:

- It separates **retrieval quality** (context precision/recall) from
  **generation quality** (faithfulness/answer relevancy), so when something
  breaks you know *which half of the system* to look at.
- It's **reference-based** (uses ground-truth answers) for the metrics where
  that matters (context recall) and **reference-free** where it doesn't
  (faithfulness checks the answer against the *retrieved context*, not a
  ground truth — which is the right comparison for hallucination detection).
- It produces **numbers you can threshold and track over time**, which is
  what makes "wire it into CI as a gate" possible at all.

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | [LangChain](https://www.langchain.com/) |
| Vector store | [Qdrant](https://qdrant.tech/) |
| Embeddings & LLM | OpenAI (`text-embedding-3-small`, `gpt-4o-mini`) |
| Keyword search | BM25 (`rank-bm25`) |
| Reranking | [sentence-transformers](https://www.sbert.net/) cross-encoder (`ms-marco-MiniLM-L-6-v2`) |
| Evaluation | [RAGAS](https://docs.ragas.io/) |
| Observability | [LangSmith](https://www.langchain.com/langsmith) |
| CI/CD | GitHub Actions |
| Testing | pytest |

## Project layout

```
rag-eval-pipeline/
├── src/
│   ├── config.py                  # all tunable parameters in one place
│   ├── ingestion/
│   │   ├── loader.py              # reads .md/.txt files, chunks them with overlap
│   │   └── indexer.py             # embeds chunks and upserts them into Qdrant
│   ├── retrieval/
│   │   ├── hybrid_search.py       # dense + sparse fusion, cross-encoder reranking
│   │   └── query_decomposition.py # LLM-based sub-question splitting + merged retrieval
│   └── generation/
│       └── rag_chain.py           # ties decomposition → retrieval → generation together
├── data/docs/                     # sample knowledge base (fictional API docs, see below)
├── eval/
│   ├── eval_dataset.json          # hand-labeled question / ground-truth pairs
│   ├── run_ragas_eval.py          # runs the pipeline + scores it with RAGAS + thresholds
│   └── results/                   # timestamped JSON eval reports land here (CI artifacts)
├── tests/                         # unit tests (mock-based — no API calls or live services)
├── .github/workflows/eval.yml     # CI: spins up Qdrant, indexes docs, runs evals, reports
├── docker-compose.yml             # local Qdrant instance
├── requirements.txt
├── pytest.ini
└── .env.example
```

## Getting started

### Prerequisites
- Python 3.10+
- Docker (for a local Qdrant instance) — or a Qdrant Cloud URL
- An OpenAI API key (for embeddings + generation)
- *(Optional)* A LangSmith API key, for tracing

### Setup

```bash
# 1. Clone and enter the project
git clone https://github.com/iffat336/rag-eval-pipeline.git
cd rag-eval-pipeline

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start Qdrant locally
docker compose up -d

# 5. Configure environment variables
cp .env.example .env
# then edit .env and fill in OPENAI_API_KEY (and optionally LANGCHAIN_API_KEY)
```

`.env.example` documents every variable the project reads — copy it to `.env`
and fill in the values relevant to you. `QDRANT_URL` already defaults to the
local docker-compose instance (`http://localhost:6333`).

## Usage

### 1. Index a document set

```bash
python -m src.ingestion.indexer data/docs
```

This loads every `.md`/`.txt` file under the given directory, splits it into
overlapping chunks (`CHUNK_SIZE`/`CHUNK_OVERLAP` in `src/config.py`), embeds
each chunk with OpenAI embeddings, and upserts them into the configured Qdrant
collection. Pass `recreate=True` (or call `index_documents` directly) to wipe
and rebuild the collection from scratch.

### 2. Ask a question

```bash
python -m src.generation.rag_chain "How does rate limiting differ between live and test API keys, and can I get my limit raised?"
```

This runs the full pipeline — decomposition, hybrid retrieval, reranking,
generation — and prints the sub-questions the decomposer generated, the final
grounded answer (with inline source citations), and the list of source
documents the answer was built from.

### 3. Run the evaluation suite

```bash
python -m eval.run_ragas_eval
```

Runs the pipeline against every question in `eval/eval_dataset.json`, scores
the results with RAGAS, writes a timestamped JSON report to `eval/results/`,
prints a summary, and **exits with a non-zero status code if any metric falls
below its threshold** — making it usable directly as a CI gate (which is
exactly how `.github/workflows/eval.yml` uses it).

## Evaluation suite in depth

Each metric targets a distinct failure mode, and together they let you
pinpoint *where* in the pipeline a regression originates:

| Metric | What it measures | What a low score tells you |
|---|---|---|
| **Faithfulness** | Whether every claim in the generated answer is supported by the retrieved context | The model is **hallucinating** — generating claims the context doesn't back up. Fix: tighten the generation prompt, lower temperature, or improve context quality. |
| **Answer relevancy** | Whether the answer actually addresses the question asked (vs. being technically grounded but off-topic or incomplete) | The model is **answering the wrong question** — often a sign that retrieval returned tangentially-related context that pulled the generation off-topic. |
| **Context precision** | Whether the *relevant* retrieved passages are ranked above irrelevant ones | **Retrieval/reranking is noisy** — relevant passages are being retrieved but buried below irrelevant ones, possibly getting cut off by the top-k limit. |
| **Context recall** | Whether retrieval surfaced *everything* needed to fully answer the question, judged against the ground truth | **Retrieval is incomplete** — some necessary information never made it into the context at all. Often the symptom decomposition is meant to fix on compound questions. |

Thresholds live in `THRESHOLDS` in `eval/run_ragas_eval.py` and currently default to:

```python
THRESHOLDS = {
    "faithfulness": 0.80,
    "answer_relevancy": 0.80,
    "context_precision": 0.70,
    "context_recall": 0.70,
}
```

The eval set itself (`eval/eval_dataset.json`) is a small, hand-curated set of
question/ground-truth pairs deliberately written to require synthesizing
information that lives in *different* source documents — e.g. a question about
service-account authentication that requires both the "Authentication" and
the cross-referenced behavior described elsewhere. This is what makes the eval
set a meaningful test of hybrid search and decomposition rather than a test of
"can you find the one paragraph that answers this."

## CI/CD pipeline

`.github/workflows/eval.yml` runs on every pull request that touches `src/`,
`data/docs/`, `eval/`, or the workflow file itself (plus on-demand via
`workflow_dispatch`). Each run:

1. Spins up a **Qdrant service container** for the duration of the job (no
   external dependencies or persistent state needed).
2. Installs dependencies and waits for Qdrant to report healthy.
3. **Re-indexes** the sample corpus from a clean slate.
4. **Runs the full RAGAS evaluation suite** against the freshly-indexed data.
5. **Uploads the JSON report** as a downloadable workflow artifact (so you can
   inspect exact scores from any run, not just the latest).
6. **Posts a summary** to the GitHub Actions run summary page, so reviewers
   can see pass/fail and scores without leaving the PR.

The job fails (and blocks the merge, if you've set up branch protection) when
`run_ragas_eval.py` exits non-zero — i.e., when any metric drops below its
threshold. This is the same "tests must pass to merge" discipline applied to
LLM output quality instead of code correctness.

> **Setup note:** for the workflow to actually run (rather than fail on
> missing credentials), add `OPENAI_API_KEY` — and optionally
> `LANGCHAIN_API_KEY` — as **repository secrets** under
> *Settings → Secrets and variables → Actions*.

## Configuration reference

All tunable parameters live in `src/config.py`:

| Variable | Default | Purpose |
|---|---|---|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model used for indexing and dense retrieval |
| `LLM_MODEL` | `gpt-4o-mini` | Model used for decomposition and generation |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Character-based chunking parameters (recursive splitter, markdown-aware separators) |
| `DENSE_WEIGHT` | `0.6` | Fusion weight for dense vs. sparse scores — `1.0` = pure semantic, `0.0` = pure keyword |
| `RETRIEVAL_TOP_K` | `20` | Candidates pulled from each retriever before fusion/reranking |
| `RERANK_TOP_K` | `5` | Final passage count handed to the generator after reranking |

Environment variables (set via `.env`, documented in `.env.example`):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Required — embeddings + LLM calls |
| `QDRANT_URL` / `QDRANT_API_KEY` / `QDRANT_COLLECTION` | Qdrant connection + collection name |
| `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` / `LANGCHAIN_PROJECT` | Optional LangSmith tracing |

## Running tests

```bash
pytest
```

The unit tests are mock-based — they exercise document loading/chunking and
the decomposition module's fallback/limiting behavior without making any API
calls or requiring a live Qdrant instance, so they run the same in CI as on
your machine. (The RAGAS suite, which *does* need live services and API
credentials, is intentionally kept separate — see
[Evaluation suite in depth](#evaluation-suite-in-depth).)

## Extending this project

Some natural directions to take this further:

- **Swap in your own corpus** — drop `.md`/`.txt` files into `data/docs/` (or
  point the indexer at a different directory) and re-run
  `python -m src.ingestion.indexer <dir>`. Write a matching set of
  question/ground-truth pairs into `eval/eval_dataset.json` for that corpus.
- **Track eval scores over time** — `eval/results/` already accumulates
  timestamped JSON reports; plotting these over commits turns the eval suite
  into a regression dashboard, not just a pass/fail gate.
- **Add a UI** — wrap `RagPipeline.answer()` in a small Streamlit/FastAPI app
  for interactive demos.
- **Try alternative rerankers or fusion strategies** — e.g. Reciprocal Rank
  Fusion (RRF) instead of weighted score fusion, or a larger cross-encoder.
- **Add metric-specific regression tests** — e.g. assert that a known
  hard compound question always triggers decomposition into ≥2 sub-questions.

## Notes on the sample corpus

`data/docs/` contains a small fictional API documentation set — authentication,
rate limits, webhooks, and billing — for a fictional product called "Nimbus."
It's deliberately written with **cross-references between documents** (e.g.
rate-limit *types* are defined in `rate_limits.md` but referenced from
`authentication.md` and `billing.md`), because that's precisely the scenario
where pure single-pass dense search struggles and where hybrid search + query
decomposition earn their keep. It's small enough to read end-to-end in a few
minutes if you want to verify the eval set's ground truths yourself.

## Troubleshooting

- **`KeyError: 'OPENAI_API_KEY'` on import** — `src/config.py` reads required
  environment variables at import time so misconfiguration fails fast and
  loudly rather than producing confusing downstream errors. Make sure `.env`
  exists and is populated (see [Setup](#setup)). Unit tests provide a dummy
  key via `tests/conftest.py` since they mock all external calls.
- **Qdrant connection errors** — confirm `docker compose up -d` is running and
  reachable at `http://localhost:6333` (or that `QDRANT_URL` points at a valid
  instance). `docker compose ps` and `curl http://localhost:6333/readyz` are
  good first checks.
- **First run is slow** — the cross-encoder reranker model
  (`ms-marco-MiniLM-L-6-v2`) is downloaded and cached by `sentence-transformers`
  on first use; subsequent runs are fast.
- **CI job fails on missing secrets** — add `OPENAI_API_KEY` (and optionally
  `LANGCHAIN_API_KEY`) as repository secrets under *Settings → Secrets and
  variables → Actions* (see [CI/CD pipeline](#cicd-pipeline)).
