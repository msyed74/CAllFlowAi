"""
Document ingestion pipeline.

Handles the end-to-end flow of taking a raw text document, chunking it into
overlapping segments, embedding each chunk, and persisting them in both:
  - Qdrant (vector store) for semantic search
  - PostgreSQL (KnowledgeChunk ORM) for structured retrieval and audit

Chunking strategy:
  - Token-aware via tiktoken (cl100k_base encoding used by text-embedding-3-small)
  - Chunk size : 500 tokens
  - Overlap    : 50 tokens (prevents context loss at boundaries)
"""

import logging
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.knowledge import KnowledgeChunk
from backend.app.rag.qdrant_client import ensure_collection_exists, build_org_filter
from backend.app.core.config import settings

logger = logging.getLogger("rag.ingestion")

try:
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")

    def _tokenise(text: str) -> List[int]:
        return _enc.encode(text)

    def _detokenise(tokens: List[int]) -> str:
        return _enc.decode(tokens)

except ImportError:
    # Fallback: approximate token count as word-count (good enough for tests)
    logger.warning("tiktoken not available – using word-based chunking approximation.")

    def _tokenise(text: str) -> List[int]:
        return list(range(len(text.split())))

    def _detokenise(tokens: List[int]) -> str:
        # Not used in word-based fallback
        return ""


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[str]:
    """
    Split `text` into overlapping token-window chunks.

    Args:
        text: Raw document text.
        chunk_size: Maximum tokens per chunk.
        overlap: Token overlap between consecutive chunks.

    Returns:
        List of text chunks preserving original whitespace as best as possible.
    """
    if not text or not text.strip():
        return []

    try:
        tokens = _enc.encode(text)
        chunks: List[str] = []
        step = chunk_size - overlap
        for start in range(0, len(tokens), step):
            chunk_tokens = tokens[start : start + chunk_size]
            chunk_text_str = _enc.decode(chunk_tokens)
            if chunk_text_str.strip():
                chunks.append(chunk_text_str)
            if start + chunk_size >= len(tokens):
                break
        return chunks
    except Exception:
        # Word-based fallback when tiktoken encode/decode unavailable
        words = text.split()
        chunks = []
        step = max(1, chunk_size - overlap)
        for start in range(0, len(words), step):
            chunk = " ".join(words[start : start + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
            if start + chunk_size >= len(words):
                break
        return chunks


async def ingest_document(
    org_id: str,
    doc_id: str,
    text: str,
    title: str,
    db_session: AsyncSession,
    qdrant_client: AsyncQdrantClient,
    embed_fn: Optional[Callable[[List[str]], Coroutine[Any, Any, List[List[float]]]]] = None,
    collection_name: str = settings.QDRANT_COLLECTION_NAME,
    chunk_size: int = 500,
    overlap: int = 50,
) -> Dict[str, Any]:
    """
    Full ingestion pipeline for a single knowledge document.

    Steps:
      1. Chunk text into overlapping segments.
      2. Embed chunks via OpenAI text-embedding-3-small (or injected embed_fn).
      3. Upsert vectors to Qdrant with multi-tenant payload.
      4. Persist KnowledgeChunk records to PostgreSQL.

    Args:
        org_id: Organization UUID (multi-tenant isolation key).
        doc_id: Parent KnowledgeDocument UUID.
        text: Full document text to ingest.
        title: Document title for human-readable context.
        db_session: Active async SQLAlchemy session.
        qdrant_client: Async Qdrant client.
        embed_fn: Optional override for the embedding function (for tests).
        collection_name: Qdrant collection to upsert into.
        chunk_size: Token window per chunk.
        overlap: Overlap tokens between chunks.

    Returns:
        Dict with `chunks_ingested`, `doc_id`, and `collection`.
    """
    from backend.app.rag.embeddings import embed_texts

    _embed = embed_fn or embed_texts

    if not text or not text.strip():
        logger.warning("ingest_document called with empty text for doc %s", doc_id)
        return {"chunks_ingested": 0, "doc_id": doc_id, "collection": collection_name}

    # 1. Ensure collection exists
    await ensure_collection_exists(qdrant_client, collection_name)

    # 2. Chunk
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return {"chunks_ingested": 0, "doc_id": doc_id, "collection": collection_name}

    logger.info("Ingesting %d chunks for document '%s' (org=%s)", len(chunks), title, org_id)

    # 3. Embed all chunks
    vectors = await _embed(chunks)

    # 4. Upsert to Qdrant + persist to DB
    qdrant_points: List[PointStruct] = []
    db_chunks: List[KnowledgeChunk] = []

    for idx, (chunk_text_str, vector) in enumerate(zip(chunks, vectors)):
        chunk_id = str(uuid.uuid4())
        position = idx

        payload = {
            "organization_id": org_id,
            "document_id": doc_id,
            "chunk_index": position,
            "title": title,
            "content": chunk_text_str,
        }

        qdrant_points.append(
            PointStruct(id=chunk_id, vector=vector, payload=payload)
        )

        db_chunk = KnowledgeChunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=position,
            chunk_text=chunk_text_str,
            token_count=len(chunk_text_str.split()),  # Approximate
            qdrant_point_id=chunk_id,
        )
        db_chunks.append(db_chunk)

    # Batch upsert to Qdrant
    await qdrant_client.upsert(
        collection_name=collection_name,
        points=qdrant_points,
    )

    # Batch insert to PostgreSQL
    db_session.add_all(db_chunks)
    await db_session.commit()

    logger.info(
        "Ingestion complete: %d chunks for document '%s'", len(chunks), doc_id
    )

    return {
        "chunks_ingested": len(chunks),
        "doc_id": doc_id,
        "collection": collection_name,
    }
