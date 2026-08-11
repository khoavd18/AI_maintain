"""Construction of the concrete Maintenance Copilot dependency graph."""

from __future__ import annotations

from functools import lru_cache

from src.application.analytics import get_asset_context_source
from src.config.settings import get_settings
from src.llm.provider_factory import create_llm_provider
from src.rag.adapters.asset_context import ProcessedDataAssetContextAdapter
from src.rag.copilot import CopilotGenerationConfig, MaintenanceCopilot
from src.rag.embeddings import LazySentenceTransformerEmbeddingProvider
from src.rag.hybrid_retriever import HybridRetrievalConfig, HybridRetriever
from src.rag.reranking import CrossEncoderReranker
from src.rag.retriever import QdrantRetriever, Retriever
from src.rag.sparse_search import QdrantBM25Retriever
from src.rag.vector_store import QdrantVectorStore


@lru_cache(maxsize=1)
def get_copilot_service() -> MaintenanceCopilot:
    """Build the default Copilot graph for API and CLI callers."""

    settings = get_settings()
    embedding_provider = LazySentenceTransformerEmbeddingProvider(
        model_name=settings.embedding_model_name,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        expected_dimensions=settings.embedding_dimensions,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
    )
    retriever: Retriever = QdrantRetriever(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        minimum_relevance_score=settings.rag_relevance_threshold,
    )
    retriever = HybridRetriever(
        dense_retriever=retriever,
        sparse_retriever=QdrantBM25Retriever(
            vector_store,
            max_chunks=settings.rag_sparse_max_chunks,
            refresh_interval_seconds=settings.rag_sparse_refresh_seconds,
        ),
        reranker=CrossEncoderReranker(
            settings.rag_reranker_model,
            device=settings.rag_reranker_device,
            batch_size=min(settings.embedding_batch_size, 64),
        ),
        config=HybridRetrievalConfig(
            dense_candidates=settings.rag_dense_candidates,
            sparse_candidates=settings.rag_sparse_candidates,
            fused_candidates=settings.rag_fused_candidates,
            final_top_k=settings.rag_final_top_k,
            dense_weight=settings.rag_dense_weight,
            sparse_weight=settings.rag_sparse_weight,
            retrieval_weight=settings.rag_retrieval_weight,
            reranker_weight=settings.rag_reranker_weight,
            metadata_weight=settings.rag_metadata_weight,
            relevance_threshold=settings.rag_relevance_threshold,
        ),
    )
    return MaintenanceCopilot(
        asset_context_provider=ProcessedDataAssetContextAdapter(get_asset_context_source()),
        retriever=retriever,
        llm_provider=create_llm_provider(settings),
        generation_config=CopilotGenerationConfig(
            enabled=settings.llm_enabled,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_context_chars=settings.llm_max_context_chars,
            min_relevant_documents=settings.llm_min_relevant_documents,
        ),
    )
