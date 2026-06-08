"""FastAPI backend for the live demo: serves the chat UI and a rate-limited
question-answering endpoint backed by the RAG pipeline.

Two usage limits keep a public deployment from running up API costs:
  - per-IP daily cap (defends against any single visitor hammering the API)
  - global daily cap shared across all visitors (bounds total spend regardless
    of how traffic is distributed)

Both are simple in-memory counters keyed by date. That's sufficient for a
single-instance self-hosted deployment; restarting the process resets them,
which is an acceptable tradeoff for a portfolio demo (and arguably a feature —
it can't accumulate unbounded state).
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.generation.rag_chain import RagPipeline

PER_IP_DAILY_LIMIT = int(os.getenv("PER_IP_DAILY_LIMIT", "10"))
GLOBAL_DAILY_LIMIT = int(os.getenv("GLOBAL_DAILY_LIMIT", "100"))
MAX_QUESTION_LENGTH = 500

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="RAG Eval Pipeline — Live Demo")

_pipeline: RagPipeline | None = None
_usage = {"date": date.today().isoformat(), "global_count": 0, "per_ip": defaultdict(int)}


def _get_pipeline() -> RagPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RagPipeline(docs_dir="data/docs")
    return _pipeline


def _reset_usage_if_new_day() -> None:
    today = date.today().isoformat()
    if _usage["date"] != today:
        _usage["date"] = today
        _usage["global_count"] = 0
        _usage["per_ip"] = defaultdict(int)


def _check_and_record_usage(client_ip: str) -> None:
    _reset_usage_if_new_day()
    if _usage["global_count"] >= GLOBAL_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="This demo has reached its shared daily usage limit. Please check back tomorrow.",
        )
    if _usage["per_ip"][client_ip] >= PER_IP_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"You've reached the {PER_IP_DAILY_LIMIT}-question daily limit for this demo.",
        )
    _usage["global_count"] += 1
    _usage["per_ip"][client_ip] += 1


class AskRequest(BaseModel):
    question: str


class PassageOut(BaseModel):
    source: str
    text: str


class AskResponse(BaseModel):
    question: str
    answer: str
    sub_questions: list[str]
    contexts: list[PassageOut]
    remaining_today: int


@app.post("/api/ask", response_model=AskResponse)
def ask(payload: AskRequest, request: Request) -> AskResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Question is too long (max {MAX_QUESTION_LENGTH} characters).",
        )

    client_ip = request.client.host if request.client else "unknown"
    _check_and_record_usage(client_ip)

    result = _get_pipeline().answer(question)

    return AskResponse(
        question=result.question,
        answer=result.answer,
        sub_questions=result.sub_questions,
        contexts=[
            PassageOut(source=doc.metadata.get("source", "unknown"), text=doc.page_content)
            for doc in result.contexts
        ],
        remaining_today=max(0, PER_IP_DAILY_LIMIT - _usage["per_ip"][client_ip]),
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
