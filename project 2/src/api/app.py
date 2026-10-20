"""Run: python -m uvicorn api.app:app --app-dir "project 2/src"."""
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from generation.service import Answer, MODEL, generate_answer
from indexing.chunking import chunk_records
from indexing.corpus import load_corpus
from retrieval.service import RetrievalService

PROJECT = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger("uvicorn.error")


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)


def create_app(retriever=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.retriever = retriever if retriever is not None else RetrievalService(
            chunk_records(load_corpus(PROJECT / "data/processed/corpus.jsonl"))
        )
        app.state.generation_lock = Lock()
        yield

    app = FastAPI(title="The Librarian", version="1.0", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(Path(__file__).with_name("index.html"))

    @app.get("/health")
    def health():
        return {"status": "ok", "model": MODEL}

    @app.post("/ask", response_model=Answer)
    def ask(body: Question, request: Request):
        if not request.app.state.generation_lock.acquire(blocking=False):
            raise HTTPException(429, "Une question est déjà en cours. Réessayez après sa réponse.", headers={"Retry-After": "5"})
        started = perf_counter()
        try:
            passages = request.app.state.retriever.retrieve(body.question, method="bm25", top_k=10)
            retrieved = perf_counter()
            try:
                answer = generate_answer(body.question, passages)
            except TimeoutError as exc:
                raise HTTPException(504, str(exc)) from exc
            except ConnectionError as exc:
                raise HTTPException(503, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(502, "Le modèle local a renvoyé une réponse illisible.") from exc
            finished = perf_counter()
            answer.timings_ms = {
                "retrieval": round((retrieved - started) * 1000, 2),
                "generation": round((finished - retrieved) * 1000, 2),
                "total": round((finished - started) * 1000, 2),
            }
            LOGGER.info(json.dumps({"event": "answer", "model": MODEL, "abstain": answer.abstain,
                "reason": answer.reason, "citations": len(answer.citations),
                "timings_ms": answer.timings_ms, "usage": answer.usage}))
            return answer
        except HTTPException as exc:
            LOGGER.warning(json.dumps({"event": "answer_error", "status": exc.status_code,
                "model": MODEL, "total_ms": round((perf_counter() - started) * 1000, 2)}))
            raise
        finally:
            request.app.state.generation_lock.release()

    return app


app = create_app()
