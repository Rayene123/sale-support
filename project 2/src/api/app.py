"""Run: python -m uvicorn api.app:app --app-dir "project 2/src"."""
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv

PROJECT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT / ".env")

from generation.service import Answer, MODEL, generate_answer
from indexing.chunking import chunk_records
from indexing.corpus import load_corpus
from qdrant_client import QdrantClient
from retrieval.service import RetrievalService
from retrieval.qdrant import QdrantRetriever
from retrieval.semantic import SentenceTransformerEmbedder

LOGGER = logging.getLogger("uvicorn.error")
MIN_RETRIEVAL_SCORE = float(os.getenv("MIN_RETRIEVAL_SCORE", "0"))
RETRIEVAL_BACKEND = os.getenv("RETRIEVAL_BACKEND", "qdrant").strip().lower()
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip()
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "").strip()


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)


def _build_retriever(*, use_qdrant: bool) -> tuple[RetrievalService, str]:
    if not use_qdrant:
        chunks = chunk_records(load_corpus(PROJECT / "data/processed/corpus.jsonl"))
        return RetrievalService(chunks), "bm25"
    if not all((QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION)):
        raise RuntimeError(
            "RETRIEVAL_BACKEND=qdrant requires QDRANT_URL, QDRANT_API_KEY, "
            "and QDRANT_COLLECTION in project 2/.env"
        )
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=20)
    collection = client.get_collection(QDRANT_COLLECTION)
    vector_size = collection.config.params.vectors.size
    if vector_size != 384:
        raise RuntimeError(
            f"Qdrant collection {QDRANT_COLLECTION!r} has vector size "
            f"{vector_size}, expected 384"
        )
    embedder = SentenceTransformerEmbedder()
    qdrant = QdrantRetriever(client, QDRANT_COLLECTION, embedder=embedder)
    chunks = qdrant.load_chunks()
    return RetrievalService(chunks, semantic_retriever=qdrant), "hybrid"


def create_app(retriever=None, *, use_qdrant: bool | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        if retriever is not None:
            app.state.retriever = retriever
            app.state.retrieval_method = "bm25"
        else:
            enabled = (
                RETRIEVAL_BACKEND == "qdrant"
                if use_qdrant is None
                else use_qdrant
            )
            app.state.retriever, app.state.retrieval_method = _build_retriever(
                use_qdrant=enabled
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
            passages = request.app.state.retriever.retrieve(
                body.question,
                method=request.app.state.retrieval_method,
                top_k=10,
            )
            if MIN_RETRIEVAL_SCORE > 0:
                passages = [passage for passage in passages if passage.score >= MIN_RETRIEVAL_SCORE]
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
