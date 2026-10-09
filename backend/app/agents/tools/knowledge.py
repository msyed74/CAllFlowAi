"""
Knowledge Base search tool for the AI Voice Agent.

Called by the ToolDispatcher when the LLM invokes `search_knowledge_base`.
Returns the top-k relevant chunks from the tenant's knowledge base in Qdrant,
or a graceful fallback message when no high-confidence match is found.

Multi-tenancy: every query is filtered by `organization_id` payload so that
tenants can NEVER see each other's knowledge content.
"""

import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from backend.app.core.config import settings

logger = logging.getLogger("agents.tools.knowledge")

# Confidence threshold below which we prefer to say "I don't know"
MIN_SCORE_THRESHOLD = 0.65
# Number of candidate results to retrieve from Qdrant
TOP_K = 5


async def search_knowledge_base(
    query: str,
    organization_id: str,
    qdrant_client: AsyncQdrantClient,
    embed_fn: Callable[[List[str]], Coroutine[Any, Any, List[List[float]]]],
    category: Optional[str] = None,
    collection_name: str = settings.QDRANT_COLLECTION_NAME,
    top_k: int = TOP_K,
    min_score: float = MIN_SCORE_THRESHOLD,
) -> Dict[str, Any]:
    """
    Semantic vector search over the organisation's knowledge base.

    Args:
        query: Natural-language question from the voice conversation.
        organization_id: Tenant isolation key.
        qdrant_client: Async Qdrant client.
        embed_fn: Async callable that maps list[str] → list[list[float]].
        category: Optional payload filter for document category.
        collection_name: Qdrant collection name.
        top_k: Maximum number of results to return.
        min_score: Minimum cosine similarity score to accept.

    Returns:
        Dict with either:
          - `found: True` + `chunks` list when results exceed min_score.
          - `found: False` + `message` string when no match found.
    """
    if not query or not query.strip():
        return {
            "found": False,
            "message": "No query provided to search_knowledge_base.",
        }

    # 1. Embed the query
    try:
        query_vectors = await embed_fn([query.strip()])
        query_vector = query_vectors[0]
    except Exception as e:
        logger.error("Failed to embed search query '%s': %s", query, e)
        return {
            "found": False,
            "message": "Embedding service temporarily unavailable. I'll answer from memory.",
        }

    # 2. Build multi-tenant payload filter
    must_conditions = [
        FieldCondition(
            key="organization_id",
            match=MatchValue(value=organization_id),
        )
    ]
    if category:
        must_conditions.append(
            FieldCondition(
                key="category",
                match=MatchValue(value=category),
            )
        )

    search_filter = Filter(must=must_conditions)

    # 3. Execute vector search
    try:
        results = await qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=top_k,
            with_payload=True,
            score_threshold=min_score,
        )
    except Exception as e:
        logger.error("Qdrant search failed for org '%s': %s", organization_id, e)
        return {
            "found": False,
            "message": "Knowledge base search temporarily unavailable.",
        }

    # 4. Check confidence
    if not results or results[0].score < min_score:
        logger.debug(
            "No high-confidence chunks found for query '%s' (best score=%.3f)",
            query,
            results[0].score if results else 0.0,
        )
        return {
            "found": False,
            "message": (
                "I don't have specific information about that in my knowledge base. "
                "I'll note your question for the team to follow up."
            ),
        }

    # 5. Format results
    chunks = []
    for hit in results:
        payload = hit.payload or {}
        chunks.append(
            {
                "score": round(hit.score, 4),
                "content": payload.get("content", ""),
                "title": payload.get("title", ""),
                "chunk_index": payload.get("chunk_index", 0),
                "document_id": payload.get("document_id", ""),
            }
        )

    logger.info(
        "Knowledge search for org '%s' returned %d chunks (best score=%.3f)",
        organization_id,
        len(chunks),
        results[0].score,
    )

    return {
        "found": True,
        "query": query,
        "chunks": chunks,
        "top_score": round(results[0].score, 4),
    }
