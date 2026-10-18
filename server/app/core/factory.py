"""Composition root: nơi duy nhất đọc app.config.settings."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from google import genai
from openai import AsyncOpenAI

from app.config import Settings, settings
from app.core.embedding.gemini_embedder import GeminiEmbedder
from app.core.generation.answer_generator import AnswerGenerator
from app.core.generation.context_builder import ContextBuilder
from app.core.generation.query_rewriter import QueryRewriter
from app.core.ingestion.chunker import StructuredChunker
from app.core.ingestion.pdf_loader import PyMuPDFLoader
from app.core.ingestion.pipeline import IngestionPipeline
from app.core.ingestion.tokenizer import HFTokenCounter
from app.core.ingestion.worker import IngestionWorker
from app.core.interfaces import Embedder, Retriever
from app.core.llm.openai_provider import OpenAIProvider
from app.core.rag_service import RAGService
from app.core.retrieval.dense import PgVectorRetriever
from app.core.retrieval.fusion import ReciprocalRankFusion
from app.core.retrieval.hybrid import HybridRetriever
from app.core.retrieval.sparse import ParadeDBBM25Retriever
from app.core.storage.chunk_repository import PgChunkRepository
from app.core.storage.document_repository import PgDocumentRepository
from app.db.session import AsyncSessionLocal


@lru_cache(maxsize=None)
def _token_counter(model_id: str) -> HFTokenCounter:
    return HFTokenCounter(model_id)


@lru_cache(maxsize=None)
def _genai_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


@lru_cache(maxsize=None)
def _openai_client(base_url: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def build_llm(s: Settings = settings) -> OpenAIProvider:
    return OpenAIProvider(
        _openai_client(s.llm_base_url, s.llm_api_key),
        s.llm_model,
        reasoning_effort=s.llm_reasoning_effort or None,
    )


def build_embedder(
    s: Settings = settings, max_retries: int | None = None
) -> GeminiEmbedder:
    return GeminiEmbedder(
        _genai_client(s.gemini_api_key),
        model=s.embedding_model,
        dimension=s.embedding_dim,
        batch_size=s.embedding_batch_size,
        max_retries=max_retries or s.embedding_max_retries,
        query_task=s.embedding_query_task,
    )


def build_retriever(
    mode: Literal["dense", "sparse", "hybrid"],
    s: Settings = settings,
    *,
    embedder: Embedder | None = None,
) -> Retriever:
    dense = PgVectorRetriever(
        AsyncSessionLocal,
        embedder or build_embedder(s),
        ef_search=s.hnsw_ef_search,
    )
    sparse = ParadeDBBM25Retriever(AsyncSessionLocal)
    if mode == "dense":
        return dense
    if mode == "sparse":
        return sparse
    if mode == "hybrid":
        fusion = ReciprocalRankFusion(
            k=s.retrieval_rrf_k,
            weights={
                "dense": s.retrieval_dense_weight,
                "sparse": s.retrieval_sparse_weight,
            },
        )
        return HybridRetriever(
            dense,
            sparse,
            fusion,
            dense_k=s.retrieval_dense_k,
            sparse_k=s.retrieval_sparse_k,
        )
    raise ValueError(f"Unknown retrieval mode: {mode}")


def build_ingestion_pipeline(s: Settings = settings) -> IngestionPipeline:
    chunker = StructuredChunker(
        _token_counter(s.chunk_tokenizer),
        target_tokens=s.chunk_target_tokens,
        overlap_tokens=s.chunk_overlap_tokens,
        max_tokens=s.chunk_max_tokens,
        min_tokens=s.chunk_min_tokens,
        include_references=s.chunk_include_references,
    )
    return IngestionPipeline(
        loader=PyMuPDFLoader(),
        chunker=chunker,
        embedder=build_embedder(s),
        documents=PgDocumentRepository(AsyncSessionLocal),
        chunks=PgChunkRepository(AsyncSessionLocal),
    )


def build_rag_service(
    *,
    mode: Literal["dense", "sparse", "hybrid"] = "hybrid",
    s: Settings = settings,
    query_max_retries: int | None = None,
) -> RAGService:
    # embedder phía query retry ít hơn: user không phải chờ hàng phút khi 429
    embedder = build_embedder(s, max_retries=query_max_retries)
    return RAGService(
        retriever=build_retriever(mode, s, embedder=embedder),
        context_builder=ContextBuilder(
            PgChunkRepository(AsyncSessionLocal),
            _token_counter(s.chunk_tokenizer),
            window=s.context_window,
            max_tokens=s.context_max_tokens,
        ),
        generator=AnswerGenerator(build_llm(s)),
        candidates=s.retrieval_candidates,
        top_n=s.retrieval_top_n,
        min_dense_score=s.retrieval_min_dense_score or None,
    )


def build_query_rewriter(s: Settings = settings) -> QueryRewriter:
    return QueryRewriter(build_llm(s), timeout_s=s.query_rewrite_timeout_s)


def build_ingest_worker(s: Settings = settings) -> IngestionWorker:
    return IngestionWorker(
        build_ingestion_pipeline(s),
        PgDocumentRepository(AsyncSessionLocal),
        lambda d: s.document_file_path(d.user_id, d.name),
        concurrency=s.ingest_concurrency,
        poll_interval_s=s.ingest_poll_interval_s,
        max_attempts=s.ingest_max_attempts,
        stale_after_s=s.ingest_stale_after_s,
    )


@dataclass(frozen=True, slots=True)
class ApiServices:
    rag: RAGService
    rewriter: QueryRewriter


def build_api_services(s: Settings = settings) -> ApiServices:
    """Gọi một lần trong lifespan; mọi object đều stateless."""
    return ApiServices(
        rag=build_rag_service(
            s=s,
            query_max_retries=s.embedding_query_max_retries,
        ),
        rewriter=build_query_rewriter(s),
    )
