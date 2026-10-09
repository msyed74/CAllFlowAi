"""
Knowledge Base API router.

Provides endpoints to list ingested knowledge documents and chunks,
and to upload/ingest new knowledge text into the Qdrant vector store.
"""

import logging
import uuid
from typing import Annotated, Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.knowledge import EmbeddingsMetadata, KnowledgeChunk, KnowledgeDocument
from backend.app.models.users import User
from backend.app.rag.ingestion import ingest_document
from backend.app.rag.qdrant_client import get_qdrant_client

logger = logging.getLogger("api.v1.knowledge")

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base Management"])


class IngestDocumentRequest(BaseModel):
    title: str
    content: str
    source_type: Optional[str] = "faq_manual"


@router.get("/documents", response_model=Dict[str, Any])
async def list_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all knowledge documents for the user's organization."""
    org_id = current_user.organization_id

    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.organization_id == org_id,
    ).order_by(KnowledgeDocument.created_at.desc())
    docs = (await db.execute(stmt)).scalars().all()

    items = []
    for d in docs:
        # Count chunks
        c_stmt = select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.document_id == d.id)
        chunk_count = (await db.execute(c_stmt)).scalar() or 0

        items.append({
            "id": d.id,
            "title": d.title,
            "source_type": d.source_type,
            "status": d.status,
            "total_chunks": chunk_count,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })

    return {"total": len(items), "items": items}


@router.post("/ingest", response_model=Dict[str, Any])
async def ingest_new_document(
    payload: IngestDocumentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Ingest a new text document into PostgreSQL and Qdrant vector index."""
    org_id = current_user.organization_id

    if not payload.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document content cannot be empty.",
        )

    # 1. Get or create EmbeddingsMetadata
    emb_stmt = select(EmbeddingsMetadata).where(
        EmbeddingsMetadata.qdrant_collection_name == settings.QDRANT_COLLECTION_NAME
    )
    emb_meta = (await db.execute(emb_stmt)).scalar_one_or_none()
    if not emb_meta:
        emb_meta = EmbeddingsMetadata(
            id=str(uuid.uuid4()),
            model_name=settings.OPENAI_EMBEDDING_MODEL,
            dimension=1536,
            distance_metric="Cosine",
            qdrant_collection_name=settings.QDRANT_COLLECTION_NAME,
        )
        db.add(emb_meta)
        await db.flush()

    # 2. Create KnowledgeDocument record
    doc_id = str(uuid.uuid4())
    doc = KnowledgeDocument(
        id=doc_id,
        organization_id=org_id,
        embeddings_metadata_id=emb_meta.id,
        title=payload.title,
        source_type=payload.source_type or "faq_manual",
        status="processing",
        total_chunks=0,
    )
    db.add(doc)
    await db.commit()

    # 3. Run Ingestion Pipeline
    try:
        qdrant = get_qdrant_client()
        result = await ingest_document(
            org_id=org_id,
            doc_id=doc_id,
            text=payload.content,
            title=payload.title,
            db_session=db,
            qdrant_client=qdrant,
            collection_name=settings.QDRANT_COLLECTION_NAME,
        )

        doc.status = "indexed"
        doc.total_chunks = result.get("chunks_ingested", 0)
        await db.commit()

        return {
            "document_id": doc_id,
            "title": payload.title,
            "status": "indexed",
            "chunks_ingested": doc.total_chunks,
        }
    except Exception as e:
        logger.error("Failed to ingest document %s: %s", doc_id, e)
        doc.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}",
        )
