"""Run: python -m uvicorn api.app:app --app-dir "project 2/src"."""
from contextlib import asynccontextmanager
import json
import logging
import base64
import hashlib
import math
import os
import secrets
import subprocess
from pathlib import Path
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from dotenv import load_dotenv

PROJECT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT / ".env")
load_dotenv(PROJECT.parent / ".env")

from generation.service import Answer, MODEL, GENERATION_PROVIDER, SYSTEM, abstention, generate_answer
from generation.questions import prepare_question
from indexing.chunking import chunk_records
from indexing.corpus import load_corpus
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from retrieval.service import RetrievalService
from retrieval.qdrant import QdrantRetriever
from retrieval.semantic import SentenceTransformerEmbedder

LOGGER = logging.getLogger("uvicorn.error")
MIN_RETRIEVAL_SCORE = float(os.getenv("MIN_RETRIEVAL_SCORE", "0"))
RETRIEVAL_BACKEND = os.getenv("RETRIEVAL_BACKEND", "qdrant").strip().lower()
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip()
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "").strip()
if not math.isfinite(MIN_RETRIEVAL_SCORE) or MIN_RETRIEVAL_SCORE < 0:
    raise ValueError("MIN_RETRIEVAL_SCORE must be finite and nonnegative")


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=4)

    @field_validator("history")
    @classmethod
    def bounded_history(cls, value):
        if sum(len(t.content) for t in value) > 6000:
            raise ValueError("conversation context is too long")
        return value


def _build_retriever(*, use_qdrant: bool) -> tuple[RetrievalService, str]:
    if not use_qdrant:
        chunks = chunk_records(load_corpus(PROJECT / "data/processed/corpus.jsonl"))
        return RetrievalService(chunks), "bm25"
    if not all((QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION)):
        LOGGER.warning(
            "Qdrant configuration is incomplete; using the committed-corpus "
            "BM25 fallback."
        )
        chunks = chunk_records(load_corpus(PROJECT / "data/processed/corpus.jsonl"))
        return RetrievalService(chunks), "bm25"
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=20)
    collection = client.get_collection(QDRANT_COLLECTION)
    vector_size = collection.config.params.vectors.size
    if vector_size != 384:
        raise RuntimeError(
            f"Qdrant collection {QDRANT_COLLECTION!r} has vector size "
            f"{vector_size}, expected 384"
        )
    embedder = SentenceTransformerEmbedder(os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    qdrant = QdrantRetriever(client, collection=QDRANT_COLLECTION, embedder=embedder)
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
        method = app.state.retrieval_method
        backend = "qdrant" if method == "hybrid" else "local"
        threshold = MIN_RETRIEVAL_SCORE
        index_hash = getattr(app.state.retriever, "index_sha256", None)
        if not isinstance(index_hash, str):
            index_hash = None
        calibration_id = None
        if path := os.getenv("CALIBRATION_FILE", ""):
            calibration = json.loads(Path(path).read_text(encoding="utf-8"))
            expected_hash = hashlib.sha256((PROJECT / "data/processed/corpus.jsonl").read_bytes()).hexdigest()
            threshold = calibration["selected_threshold"]
            if (calibration.get("backend") != backend or calibration.get("method") != method
                    or calibration.get("corpus_sha256") != expected_hash
                    or index_hash is None or calibration.get("index_sha256") != index_hash
                    or isinstance(threshold, bool) or not isinstance(threshold, (int, float))
                    or not math.isfinite(threshold) or threshold < 0):
                raise ValueError("Calibration does not match the active backend/corpus")
            calibration_id = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        try:
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT,
                                               stderr=subprocess.DEVNULL, timeout=3).decode().strip()
        except (OSError, subprocess.SubprocessError):
            revision = os.getenv("APP_REVISION", "unknown")
        app.state.threshold = threshold
        app.state.configuration = {
            "generation_provider": GENERATION_PROVIDER, "model": MODEL,
            "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "none") if GENERATION_PROVIDER == "openai" else None,
            "retrieval_backend": backend, "retrieval_method": method,
            "embedding_revision": os.getenv("EMBEDDING_REVISION") if backend == "qdrant" else None,
            "collection": QDRANT_COLLECTION if backend == "qdrant" else None,
            "min_retrieval_score": threshold, "calibration_sha256": calibration_id,
            "prompt_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
            "corpus_sha256": hashlib.sha256((PROJECT / "data/processed/corpus.jsonl").read_bytes()).hexdigest(),
            "index_sha256": index_hash,
            "revision": revision,
            "source_sha256": {str(p.relative_to(PROJECT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((PROJECT / "src").rglob("*.py"))},
            "rewrite": os.getenv("QUESTION_REWRITING", "true").lower() == "true",
            "top_k": 10, "context_chars": 12000, "max_output_tokens": 640,
        }
        yield

    app = FastAPI(title="The Librarian", version="1.0", lifespan=lifespan)

    @app.middleware("http")
    async def protect_demo(request: Request, call_next):
        password = os.getenv("DEMO_PASSWORD", "")
        if password and request.url.path != "/health":
            expected = "Basic " + base64.b64encode(f"librarian:{password}".encode()).decode()
            if not secrets.compare_digest(request.headers.get("authorization", "").encode(), expected.encode()):
                return Response("Accès réservé au projet.", status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="The Librarian"'})
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(Path(__file__).with_name("index.html"), headers={"Cache-Control": "no-cache"})

    @app.get("/health")
    def health(request: Request):
        return {"status": "ok", "model": MODEL,
                "paid_calls_allowed": os.getenv("ALLOW_PAID_CALLS", "").lower() == "true",
                "configuration": request.app.state.configuration}

    @app.post("/ask", response_model=Answer)
    def ask(body: Question, request: Request):
        if GENERATION_PROVIDER in {"openai", "groq"} and os.getenv("ALLOW_PAID_CALLS", "").lower() != "true":
            raise HTTPException(503, "Les appels au modèle payant sont désactivés pour préserver le crédit.")
        if not request.app.state.generation_lock.acquire(blocking=False):
            raise HTTPException(429, "Une question est déjà en cours. Réessayez après sa réponse.", headers={"Retry-After": "5"})
        started = perf_counter()
        try:
            if request.app.state.configuration["rewrite"]:
                plan, rewrite_usage = prepare_question(body.question, [t.model_dump() for t in body.history])
                queries, clarification = plan.queries, plan.clarification
            else:
                queries, clarification, rewrite_usage = [body.question], "", {}
            rewritten = perf_counter()
            passages = []
            if not clarification:
                batches = []
                try:
                    for query in queries:
                        batches.append(request.app.state.retriever.retrieve(
                            query, method=request.app.state.retrieval_method, top_k=10))
                except (OSError, ResponseHandlingException, UnexpectedResponse) as exc:
                    raise HTTPException(503, "Les archives sont temporairement indisponibles. Réessayez.") from exc
                except (ValueError, RuntimeError) as exc:
                    raise HTTPException(502, "Les archives ont renvoyé des passages invalides.") from exc
                # Round-robin preserves evidence from each subquestion without mixing score scales.
                seen = {}
                for row in zip(*[batch + [None] * (10 - len(batch)) for batch in batches]):
                    for passage in row:
                        if passage is not None:
                            if passage.chunk_id not in seen:
                                seen[passage.chunk_id] = len(passages)
                                passages.append(passage)
                            elif passage.score > passages[seen[passage.chunk_id]].score:
                                passages[seen[passage.chunk_id]] = passage
                passages = passages[:10]
            threshold = request.app.state.threshold
            had_passages = bool(passages)
            if threshold > 0:
                passages = [passage for passage in passages if passage.score >= threshold]
            retrieved = perf_counter()
            try:
                if clarification:
                    answer = abstention("clarification", clarification)
                elif had_passages and not passages:
                    answer = abstention("below_threshold", "Les passages trouvés sont insuffisants pour répondre de façon fiable.")
                else:
                    answer = generate_answer(body.question, passages, search_queries=queries)
            except TimeoutError as exc:
                raise HTTPException(504, str(exc)) from exc
            except ConnectionError as exc:
                raise HTTPException(503, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(502, "Le service de génération a renvoyé une réponse illisible.") from exc
            finished = perf_counter()
            answer.retrieval_queries = queries
            answer.configuration = request.app.state.configuration
            answer.usage.setdefault("prompt_tokens", 0)
            answer.usage.setdefault("completion_tokens", 0)
            answer.usage.update(rewrite_usage)
            answer.timings_ms = {
                "rewrite": round((rewritten - started) * 1000, 2),
                "retrieval": round((retrieved - rewritten) * 1000, 2),
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
