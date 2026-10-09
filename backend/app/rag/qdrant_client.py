"""
Singleton async Qdrant client wrapper.

Provides a lazily-initialised QdrantClient that is shared for the lifetime
of the process.  All multi-tenant queries MUST pass an organization_id payload
filter so that knowledge isolation is enforced at the vector-store level.
"""

import logging
from typing import Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    PointStruct,
    ScoredPoint,
)
from qdrant_client.models import CollectionInfo

from backend.app.core.config import settings

logger = logging.getLogger("rag.qdrant_client")

# Module-level singleton – created on first call to get_qdrant_client()
_qdrant_client: Optional[AsyncQdrantClient] = None


def get_qdrant_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
    api_key: Optional[str] = None,
) -> AsyncQdrantClient:
    """
    Return the process-level AsyncQdrantClient singleton.

    Parameters override settings only when explicitly supplied – this lets
    tests inject a local / in-memory client without touching global config.
    """
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            host=host or settings.QDRANT_HOST,
            port=port or settings.QDRANT_PORT,
            api_key=api_key or settings.QDRANT_API_KEY,
            # 10-second connect timeout, 30-second read timeout
            timeout=30,
        )
        logger.info(
            "Qdrant AsyncQdrantClient initialised at %s:%s",
            host or settings.QDRANT_HOST,
            port or settings.QDRANT_PORT,
        )
    return _qdrant_client


def reset_qdrant_client() -> None:
    """
    Reset singleton – used by tests that inject a fresh client.
    """
    global _qdrant_client
    _qdrant_client = None


async def ensure_collection_exists(
    client: AsyncQdrantClient,
    collection_name: str,
    vector_size: int = 1536,
) -> bool:
    """
    Idempotent collection bootstrap.

    Creates the collection with cosine-distance vectors if it does not
    already exist.  Returns True if collection was created, False if it
    already existed.
    """
    try:
        existing = await client.get_collections()
        names = {c.name for c in existing.collections}
        if collection_name in names:
            logger.debug("Collection '%s' already exists.", collection_name)
            return False

        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s' (dim=%d).", collection_name, vector_size)
        return True
    except Exception as e:
        logger.error("Error ensuring Qdrant collection '%s': %s", collection_name, e)
        raise


def build_org_filter(organization_id: str) -> Filter:
    """
    Build a Qdrant payload filter that restricts results to a single tenant.
    All points must carry `organization_id` as a payload field.
    """
    return Filter(
        must=[
            FieldCondition(
                key="organization_id",
                match=MatchValue(value=organization_id),
            )
        ]
    )
