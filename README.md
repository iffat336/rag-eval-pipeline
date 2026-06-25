# RAG Evaluation Pipeline

A production-style Retrieval-Augmented Generation system with hybrid search,
cross-encoder reranking, LLM-driven query decomposition, a FastAPI demo, and a
RAGAS evaluation suite that can act as a quality gate.

The project focuses on the difficult parts of RAG engineering: retrieving the
right passages, grounding answers in those passages, measuring regressions,
and operating a public demo without uncontrolled API usage.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Request lifecycle](#request-lifecycle)
- [Evaluation lifecycle](#evaluation-lifecycle)
- [Project structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Indexing documents](#indexing-documents)
- [Asking questions](#asking-questions)
- [Running the web demo](#running-the-web-demo)
- [Running evaluations](#running-evaluations)
- [Testing](#testing)
- [Docker deployment](#docker-deployment)
- [Evaluation metrics](#evaluation-metrics)
- [Design decisions](#design-decisions)
- [Troubleshooting](#troubleshooting)
- [Security and cost controls](#security-and-cost-controls)

## Features

- **Dense retrieval:** OpenAI embeddings stored in Qdrant.
- **Sparse retrieval:** BM25 keyword matching for exact terms and identifiers.
- **Weighted score fusion:** combines semantic and lexical candidates.
- **Cross-encoder reranking:** scores query-passage pairs for stronger final
  relevance.
- **Query decomposition:** splits compound questions into focused
  sub-questions.
- **Grounded generation:** answers from retrieved context and includes source
  references.
- **RAGAS evaluation:** measures faithfulness, answer relevancy, context
  precision, and context recall.
- **Threshold-based quality gate:** evaluation exits non-zero when a metric
  falls below its configured threshold.
- **FastAPI demo:** provides a browser interface and JSON API.
- **Usage caps:** per-IP and global daily counters limit public-demo spending.
- **Docker support:** runs the application and Qdrant as a reproducible stack.
- **Optional LangSmith tracing:** supports request inspection and debugging.

## Architecture

```text
User question
     |
     v
+---------------------+
| Query decomposition |
| 1 to 4 sub-queries  |
+---------------------+
     |
     v
+-----------------------------------+
| Retrieval for each sub-query      |
|                                   |
| Dense search -----+               |
|                   +-> score fusion|
| BM25 search ------+               |
|                         |         |
|                         v         |
|                cross-encoder      |
|                   reranking       |
+-----------------------------------+
     |
     v
Deduplicate and merge top passages
     |
     v
+---------------------+
| Grounded generation |
| answer + sources    |
+---------------------+
     |
     +------> Web or CLI result
     |
     `------> RAGAS evaluation
```

## Request lifecycle

1. `RagPipeline.answer()` receives a question.
2. The query decomposer decides whether the question contains multiple
   independent information needs.
3. Each resulting sub-question is sent to the hybrid retriever.
4. Dense and BM25 candidates are normalized and fused.
5. A sentence-transformers cross-encoder reranks the candidate set.
6. Results are deduplicated by chunk identifier.
7. The generator receives the final passages and produces a grounded answer.
8. The caller receives the original question, generated sub-questions, answer,
   and retrieved contexts.

## Evaluation lifecycle

1. `eval/eval_dataset.json` supplies labeled questions and ground truths.
2. The real RAG pipeline answers every evaluation question.
3. RAGAS compares questions, answers, contexts, and reference answers.
4. Scores are calculated for four independent metrics.
5. A timestamped JSON report is written to `eval/results/`.
6. The process exits with code `1` if any score misses its threshold.

This makes the evaluation command suitable for CI and release gates.

## Project structure

```text
rag-eval-pipeline/
|-- src/
|   |-- config.py
|   |-- ingestion/
|   |   |-- loader.py
|   |   `-- indexer.py
|   |-- retrieval/
|   |   |-- hybrid_search.py
|   |   `-- query_decomposition.py
|   `-- generation/
|       `-- rag_chain.py
|-- web/
|   |-- main.py
|   `-- static/
|       |-- index.html
|       |-- app.js
|       `-- style.css
|-- eval/
|   |-- eval_dataset.json
|   `-- run_ragas_eval.py
|-- tests/
|-- Dockerfile
|-- docker-compose.yml
|-- docker-compose.prod.yml
|-- pytest.ini
|-- requirements.txt
`-- .env.example
```

## Requirements

- Python 3.10 or newer
- Docker Desktop or another Docker installation for local Qdrant
- An OpenAI API key
- Optional: a LangSmith API key

The first reranking request downloads the configured sentence-transformers
model and may take longer than later requests.

## Installation

```bash
git clone https://github.com/iffat336/rag-eval-pipeline.git
cd rag-eval-pipeline

python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS or Linux
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create `.env`:

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# macOS or Linux
cp .env.example .env
```

Start Qdrant:

```bash
docker compose up -d
```

Check the service:

```bash
docker compose ps
```

## Configuration

Example `.env`:

```dotenv
OPENAI_API_KEY=your_openai_api_key

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=docs

LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=rag-eval-pipeline

PER_IP_DAILY_LIMIT=10
GLOBAL_DAILY_LIMIT=100
```

### Environment variables

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `OPENAI_API_KEY` | Yes | None | Embeddings, query decomposition, generation, and RAGAS model calls. |
| `QDRANT_URL` | No | `http://localhost:6333` | Qdrant server URL. |
| `QDRANT_API_KEY` | No | Blank | Authentication for a managed Qdrant instance. |
| `QDRANT_COLLECTION` | No | `docs` | Collection containing indexed chunks. |
| `LANGCHAIN_TRACING_V2` | No | Unset | Enables LangSmith tracing when set to `true`. |
| `LANGCHAIN_API_KEY` | No | Blank | Authenticates LangSmith tracing. |
| `LANGCHAIN_PROJECT` | No | `rag-eval-pipeline` in the example | Groups traces in LangSmith. |
| `PER_IP_DAILY_LIMIT` | No | `10` | Maximum daily demo questions from one IP address. |
| `GLOBAL_DAILY_LIMIT` | No | `100` | Maximum daily demo questions across all visitors. |

### Code-level retrieval settings

These values currently live in `src/config.py`:

| Setting | Value | Purpose |
|---|---:|---|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Creates vectors for chunks and queries. |
| `LLM_MODEL` | `gpt-4o-mini` | Handles decomposition and answer generation. |
| `CHUNK_SIZE` | `800` | Maximum chunk size used by document ingestion. |
| `CHUNK_OVERLAP` | `120` | Context overlap between neighboring chunks. |
| `DENSE_WEIGHT` | `0.6` | Dense contribution to hybrid score fusion. |
| `RETRIEVAL_TOP_K` | `20` | Candidate count collected before reranking. |
| `RERANK_TOP_K` | `5` | Final passage count sent to the generator. |

## Indexing documents

The loader recursively reads `.md` and `.txt` files. To index the default
corpus:

```bash
python -m src.ingestion.indexer data/docs
```

The command recreates the configured collection, chunks the source files,
generates embeddings, and stores them in Qdrant.

To use your own corpus:

```bash
python -m src.ingestion.indexer path/to/your/documents
```

Re-run indexing after changing the document set or chunking behavior.

## Asking questions

Run the pipeline from the command line:

```bash
python -m src.generation.rag_chain "How do authentication methods and rate limits differ?"
```

Programmatic use:

```python
from src.generation.rag_chain import RagPipeline

pipeline = RagPipeline(docs_dir="data/docs")
result = pipeline.answer("How are API keys revoked?")

print(result.answer)
print(result.sub_questions)

for document in result.contexts:
    print(document.metadata.get("source"))
```

## Running the web demo

Start the FastAPI server:

```bash
uvicorn web.main:app --reload
```

Open:

```text
http://localhost:8000
```

### API endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the chat interface. |
| `GET` | `/api/health` | Returns `{"status": "ok"}`. |
| `POST` | `/api/ask` | Runs the RAG pipeline for a question. |

Example request:

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"How do I rotate an API key?\"}"
```

The API rejects blank questions, questions longer than 500 characters, and
requests exceeding the configured daily limits.

The counters are in memory. They reset when the date changes or the process
restarts and are suitable for a single-instance portfolio deployment. Use
shared persistent rate limiting for a multi-instance production deployment.

## Running evaluations

Ensure Qdrant is running and the corpus is indexed, then run:

```bash
python -m eval.run_ragas_eval
```

The command:

- answers all labeled evaluation questions;
- calculates the RAGAS metrics;
- writes a timestamped report under `eval/results/`;
- prints the score and threshold summary;
- returns a failing exit code when quality is below the gate.

Current thresholds:

```python
THRESHOLDS = {
    "faithfulness": 0.80,
    "answer_relevancy": 0.80,
    "context_precision": 0.70,
    "context_recall": 0.70,
}
```

Evaluation calls external models and therefore consumes API credits.

## Testing

Run unit tests:

```bash
pytest
```

The tests focus on deterministic loader and query-decomposition behavior and
mock external dependencies. The RAGAS suite is intentionally separate because
it needs a live vector store and model credentials.

## Docker deployment

### Local development stack

```bash
docker compose up -d
```

### Production-style stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Index documents inside the running application container:

```bash
docker compose -f docker-compose.prod.yml exec app \
  python -m src.ingestion.indexer data/docs
```

Check health and logs:

```bash
curl http://127.0.0.1:8000/api/health
docker compose -f docker-compose.prod.yml logs -f app
```

The production Compose file is designed for use behind a reverse proxy such
as nginx or Caddy. Keep Qdrant private and terminate HTTPS at the proxy.

## Evaluation metrics

| Metric | Measures | Common failure indicated by a low score |
|---|---|---|
| Faithfulness | Whether generated claims are supported by retrieved context | The model is hallucinating or overextending the evidence. |
| Answer relevancy | Whether the response addresses the user's question | Retrieval or generation has drifted off topic. |
| Context precision | Whether useful passages rank above irrelevant passages | Candidate retrieval or reranking is noisy. |
| Context recall | Whether the retrieved context contains everything needed | Retrieval missed necessary information. |

Separating retrieval and generation metrics makes regressions easier to
diagnose than using one aggregate score.

## Design decisions

### Why hybrid retrieval?

Dense search captures semantic similarity, while BM25 is strong for exact
identifiers, product names, error codes, and uncommon terms. Combining both
reduces the weaknesses of either method alone.

### Why rerank after retrieval?

Cross-encoders provide stronger relevance judgments because they jointly read
the query and passage, but they are too expensive to run over the full corpus.
The pipeline retrieves a broad candidate set cheaply and reranks only that
smaller set.

### Why decompose queries?

A single vector often represents one part of a compound question better than
another. Separate retrieval for each sub-question improves coverage before
the results are merged and deduplicated.

### Why enforce thresholds?

Without stable evaluation data and pass/fail criteria, prompt and retrieval
changes are judged by a few handpicked examples. Thresholds make regressions
visible and automate the decision to reject a change.

## Troubleshooting

### `KeyError: 'OPENAI_API_KEY'`

Create `.env` in the repository root and set `OPENAI_API_KEY`. The
configuration module intentionally validates this at import time.

### Qdrant connection failure

```bash
docker compose ps
curl http://localhost:6333/readyz
```

Also confirm that `QDRANT_URL` matches the environment where the application
is running. A Docker container usually reaches Qdrant by service name rather
than `localhost`.

### Collection is empty

Run the indexer before asking questions:

```bash
python -m src.ingestion.indexer data/docs
```

### First request is slow

The reranker model is downloaded on first use. Later requests use the local
model cache.

### Evaluation scores vary

LLM-based metrics are probabilistic. Investigate meaningful repeated changes,
keep the evaluation set stable, and avoid treating tiny score differences as
conclusive.

## Security and cost controls

- Never commit `.env` or API credentials.
- Store CI keys in GitHub Actions secrets.
- Set API-provider spending limits.
- Keep Qdrant and internal services off the public internet.
- Use a persistent distributed rate limiter for multiple application replicas.
- Do not send confidential documents to third-party embedding or LLM services
  without appropriate authorization and data-handling agreements.

## License

No license file is currently included. Add one before redistribution or
external contribution.
