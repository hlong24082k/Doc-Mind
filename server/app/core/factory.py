"""Composition root: nơi duy nhất đọc app.config.settings."""

from functools import lru_cache
from typing import Literal

from google import genai

from app.config import Settings, settings
from app.core.embedding.gemini_embedder import GeminiEmbedder
from app.core.generation.answer_generator import AnswerGenerator
from app.core.generation.context_builder import ContextBuilder
from app.core.ingestion.chunker import StructuredChunker
from app.core.ingestion.pdf_loader import PyMuPDFLoader
from app.core.ingestion.pipeline import IngestionPipeline
from app.core.ingestion.tokenizer import HFTokenCounter
from app.core.interfaces import Reranker, Retriever
from app.core.llm.gemini_provider import GeminiProvider
from app.core.rag_service import RAGService
from app.core.rerank.laya_reranker import LayaReranker
from app.core.rerank.noop_reranker import NoOpReranker
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
def _laya(model_id: str, dtype: str) -> LayaReranker:
    return LayaReranker(model_id, dtype=dtype)


@lru_cache(maxsize=None)
def _genai_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def build_embedder(s: Settings = settings) -> GeminiEmbedder:
    return GeminiEmbedder(
        _genai_client(s.gemini_api_key),
        model=s.embedding_model,
        dimension=s.embedding_dim,
        batch_size=s.embedding_batch_size,
        max_retries=s.embedding_max_retries,
        query_task=s.embedding_query_task,
    )


def build_retriever(
    mode: Literal["dense", "sparse", "hybrid"], s: Settings = settings
) -> Retriever:
    dense = PgVectorRetriever(
        AsyncSessionLocal, build_embedder(s), ef_search=s.hnsw_ef_search
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


def build_reranker(name: str | None = None, s: Settings = settings) -> Reranker:
    name = (name or s.reranker).lower()
    if name == "laya":
        return _laya(s.laya_model, s.laya_dtype)
    if name == "none":
        return NoOpReranker()
    raise ValueError(f"Unknown reranker: {name}")


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
    reranker: str | None = None,
    s: Settings = settings,
) -> RAGService:
    reranker_name = (reranker or s.reranker).lower()
    return RAGService(
        retriever=build_retriever(mode, s),
        reranker=build_reranker(reranker_name, s),
        context_builder=ContextBuilder(
            PgChunkRepository(AsyncSessionLocal),
            _token_counter(s.chunk_tokenizer),
            window=s.context_window,
            max_tokens=s.context_max_tokens,
        ),
        generator=AnswerGenerator(GeminiProvider(s.gemini_model)),
        candidates=s.retrieval_candidates,
        top_n=s.rerank_top_n,
        min_score=None if reranker_name == "none" else s.rerank_min_score,
        min_dense_score=s.retrieval_min_dense_score or None,
    )
