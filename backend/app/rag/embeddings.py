"""
OpenAI Embeddings helper.

Wraps the openai async client to produce text-embedding-3-small vectors
(1536 dimensions).  The embed_texts() function is designed to be easily
mocked in unit tests by passing a custom callable via the embed_fn parameter
in dependent modules.
"""

import logging
from typing import List, Optional

import httpx

from backend.app.core.config import settings

logger = logging.getLogger("rag.embeddings")

EMBEDDING_DIMENSION = 1536
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_BATCH_SIZE = 100  # OpenAI allows up to 2048 items per call


async def embed_texts(
    texts: List[str],
    api_key: Optional[str] = None,
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> List[List[float]]:
    """
    Generate embeddings for a list of text strings using the OpenAI Embeddings API.

    Args:
        texts: List of strings to embed.  Empty strings are replaced with a
               single space to satisfy the API's requirement for non-empty input.
        api_key: Override API key (defaults to settings.OPENAI_API_KEY).
        model: Embedding model name.

    Returns:
        List of float vectors in the same order as the input.
    """
    if not texts:
        return []

    key = api_key or settings.OPENAI_API_KEY
    sanitised = [t.strip() or " " for t in texts]
    results: List[List[float]] = []

    # Process in batches to stay within API limits
    for i in range(0, len(sanitised), EMBEDDING_BATCH_SIZE):
        batch = sanitised[i : i + EMBEDDING_BATCH_SIZE]
        vectors = await _call_embeddings_api(batch, key, model)
        results.extend(vectors)

    return results


async def _call_embeddings_api(
    texts: List[str],
    api_key: str,
    model: str,
) -> List[List[float]]:
    """
    Low-level HTTP call to OpenAI Embeddings endpoint.
    Uses httpx directly so this module has no hard runtime dependency on the
    openai SDK (easier to mock in test environments).
    """
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": texts}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        raise RuntimeError(
            f"OpenAI Embeddings API error {response.status_code}: {response.text}"
        )

    data = response.json()
    # data["data"] is a list sorted by index
    sorted_items = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in sorted_items]


async def embed_single(
    text: str,
    api_key: Optional[str] = None,
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> List[float]:
    """Convenience wrapper to embed a single string."""
    vectors = await embed_texts([text], api_key=api_key, model=model)
    return vectors[0]
