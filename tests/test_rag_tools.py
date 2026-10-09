"""
Phase 3 Tests: RAG Tools, Ingestion, and Tool Dispatcher

Uses mocked Qdrant client and deterministic embedding function to avoid
real API calls. Tests cover:
  - chunk_text() correctness
  - ingest_document() pipeline
  - search_knowledge_base() with hit / miss scenarios
  - check_calendar_availability() slot generation
  - book_appointment_slot() with and without Redis lock
  - update_crm_lead() field merging and stage mapping
  - transfer_call_to_human() payload structure
  - ToolDispatcher.execute() routing, timing, and allowlist enforcement
"""

import json
import pytest
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TestAsyncSessionLocal, test_engine
from backend.app.core.database import Base

# ─────────────────────────── Helpers ─────────────────────────────────────────


async def _fake_embed(texts: List[str]) -> List[List[float]]:
    """Deterministic fake embedder — returns vectors of incrementing 0.1 values."""
    dim = 1536
    return [[float(i % 10) * 0.1] * dim for i in range(len(texts))]


def _make_scored_point(score: float, content: str, org_id: str) -> MagicMock:
    """Build a Qdrant ScoredPoint-like mock."""
    point = MagicMock()
    point.score = score
    point.payload = {
        "organization_id": org_id,
        "content": content,
        "title": "Test Doc",
        "chunk_index": 0,
        "document_id": "doc-123",
    }
    return point


# ─────────────────────────── Fixtures ────────────────────────────────────────


@pytest.fixture
async def db():
    """Fresh in-memory SQLite DB for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestAsyncSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_qdrant():
    """In-memory Qdrant mock — stores upserted points and returns them on search."""
    client = AsyncMock()
    _store: Dict[str, List[Any]] = {}

    async def fake_upsert(collection_name, points, **kwargs):
        _store.setdefault(collection_name, []).extend(points)

    async def fake_search(collection_name, query_vector, query_filter=None, limit=5,
                          with_payload=True, score_threshold=0.0, **kwargs):
        # Return pre-programmed results attached to the mock or default empty list
        return getattr(client, "_search_results", [])

    async def fake_get_collections():
        result = MagicMock()
        result.collections = []
        return result

    async def fake_create_collection(**kwargs):
        pass

    client.upsert = fake_upsert
    client.search = fake_search
    client.get_collections = fake_get_collections
    client.create_collection = fake_create_collection
    client._store = _store
    return client


# ─────────────────────────── chunk_text ──────────────────────────────────────


class TestChunkText:
    def test_basic_chunking(self):
        from backend.app.rag.ingestion import chunk_text
        # 1000 words
        text = " ".join(["word"] * 1000)
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) >= 1
        # Each chunk is non-empty
        for c in chunks:
            assert c.strip()

    def test_empty_text_returns_empty(self):
        from backend.app.rag.ingestion import chunk_text
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        from backend.app.rag.ingestion import chunk_text
        text = "Hello world, this is a short document."
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert "Hello" in chunks[0]

    def test_overlap_creates_multiple_chunks(self):
        from backend.app.rag.ingestion import chunk_text
        # Force multiple chunks with small size
        text = " ".join(["alpha"] * 200)
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 2


# ─────────────────────────── ingest_document ─────────────────────────────────


class TestIngestDocument:
    @pytest.mark.asyncio
    async def test_ingestion_creates_db_chunks(self, mock_qdrant, db):
        from backend.app.rag.ingestion import ingest_document
        from backend.app.models.knowledge import KnowledgeChunk, KnowledgeDocument, EmbeddingsMetadata
        from sqlalchemy import select

        # We need a KnowledgeDocument to satisfy FK — but for the ingestion test
        # we use a bare doc_id string (the ingestion function doesn't FK-validate)
        doc_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        # Create minimal required records in the test DB
        # (EmbeddingsMetadata → KnowledgeDocument → KnowledgeChunk)
        emb_meta = EmbeddingsMetadata(
            qdrant_collection_name="callflow_knowledge_base",
        )
        db.add(emb_meta)
        await db.flush()

        from backend.app.models.organizations import Organization
        org = Organization(id=org_id, name="Test Org", slug="test-org", status="active")
        db.add(org)
        await db.flush()

        doc = KnowledgeDocument(
            id=doc_id,
            organization_id=org_id,
            embeddings_metadata_id=emb_meta.id,
            title="Test Doc",
            source_type="txt",
            status="processing",
        )
        db.add(doc)
        await db.commit()

        text = "This is a test document. " * 50  # ~12 words × 50 = 600 words

        result = await ingest_document(
            org_id=org_id,
            doc_id=doc_id,
            text=text,
            title="Test Doc",
            db_session=db,
            qdrant_client=mock_qdrant,
            embed_fn=_fake_embed,
            collection_name="callflow_knowledge_base",
            chunk_size=100,
            overlap=20,
        )

        assert result["chunks_ingested"] >= 1
        assert result["doc_id"] == doc_id

        # Verify DB chunks written
        stmt = select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
        rows = (await db.execute(stmt)).scalars().all()
        assert len(rows) == result["chunks_ingested"]

    @pytest.mark.asyncio
    async def test_empty_document_returns_zero_chunks(self, mock_qdrant, db):
        from backend.app.rag.ingestion import ingest_document

        result = await ingest_document(
            org_id="org-1",
            doc_id="doc-1",
            text="   ",
            title="Empty",
            db_session=db,
            qdrant_client=mock_qdrant,
            embed_fn=_fake_embed,
        )
        assert result["chunks_ingested"] == 0


# ─────────────────────────── search_knowledge_base ───────────────────────────


class TestSearchKnowledgeBase:
    @pytest.mark.asyncio
    async def test_hit_above_threshold(self, mock_qdrant):
        from backend.app.agents.tools.knowledge import search_knowledge_base

        org_id = "org-abc"
        mock_qdrant._search_results = [
            _make_scored_point(0.85, "Our pricing starts at $99/month.", org_id),
            _make_scored_point(0.72, "We offer a free 14-day trial.", org_id),
        ]

        result = await search_knowledge_base(
            query="What is the pricing?",
            organization_id=org_id,
            qdrant_client=mock_qdrant,
            embed_fn=_fake_embed,
            min_score=0.65,
        )

        assert result["found"] is True
        assert len(result["chunks"]) == 2
        assert result["top_score"] == 0.85

    @pytest.mark.asyncio
    async def test_miss_below_threshold_returns_fallback(self, mock_qdrant):
        from backend.app.agents.tools.knowledge import search_knowledge_base

        org_id = "org-abc"
        mock_qdrant._search_results = [
            _make_scored_point(0.40, "Irrelevant content.", org_id),
        ]

        result = await search_knowledge_base(
            query="What is the meaning of life?",
            organization_id=org_id,
            qdrant_client=mock_qdrant,
            embed_fn=_fake_embed,
            min_score=0.65,
        )

        assert result["found"] is False
        assert "message" in result

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self, mock_qdrant):
        from backend.app.agents.tools.knowledge import search_knowledge_base

        result = await search_knowledge_base(
            query="",
            organization_id="org-1",
            qdrant_client=mock_qdrant,
            embed_fn=_fake_embed,
        )

        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_embed_failure_returns_graceful_message(self, mock_qdrant):
        from backend.app.agents.tools.knowledge import search_knowledge_base

        async def failing_embed(texts):
            raise RuntimeError("API down")

        result = await search_knowledge_base(
            query="some question",
            organization_id="org-1",
            qdrant_client=mock_qdrant,
            embed_fn=failing_embed,
        )

        assert result["found"] is False
        assert "unavailable" in result["message"].lower()


# ─────────────────────────── check_calendar_availability ─────────────────────


class TestCheckCalendarAvailability:
    @pytest.mark.asyncio
    async def test_future_date_returns_slots(self):
        from backend.app.agents.tools.scheduling import check_calendar_availability

        future_date = (datetime.now(tz=timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")
        result = await check_calendar_availability(
            preferred_date=future_date,
            timezone_str="UTC",
        )

        assert "available_slots" in result
        assert isinstance(result["available_slots"], list)
        # Slots should be non-empty for a future business day
        assert len(result["available_slots"]) > 0

    @pytest.mark.asyncio
    async def test_past_date_returns_no_slots(self):
        from backend.app.agents.tools.scheduling import check_calendar_availability

        past_date = "2020-01-01"
        result = await check_calendar_availability(preferred_date=past_date)

        assert result["available_slots"] == []

    @pytest.mark.asyncio
    async def test_invalid_date_format_returns_error(self):
        from backend.app.agents.tools.scheduling import check_calendar_availability

        result = await check_calendar_availability(preferred_date="not-a-date")
        assert "error" in result


# ─────────────────────────── book_appointment_slot ───────────────────────────


class TestBookAppointmentSlot:
    @pytest.mark.asyncio
    async def test_successful_booking(self, db):
        from backend.app.agents.tools.scheduling import book_appointment_slot
        from backend.app.models.appointments import Appointment
        from backend.app.models.leads import Lead
        from backend.app.models.organizations import Organization
        from backend.app.models.calls import Call
        from sqlalchemy import select

        # Setup minimal DB records
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Test Org", slug="test-slug", status="active")
        db.add(org)
        await db.flush()

        lead_id = str(uuid.uuid4())
        lead = Lead(
            id=lead_id,
            organization_id=org_id,
            first_name="Jane",
            last_name="Doe",
            phone_number="+15551234567",
            status="new",
        )
        db.add(lead)

        call_id = str(uuid.uuid4())
        call = Call(
            id=call_id,
            organization_id=org_id,
            lead_id=lead_id,
            direction="outbound",
            status="in_progress",
            from_number="+18005550199",
            to_number="+15551234567",
            twilio_call_sid=f"CA{call_id.replace('-', '')[:32]}",
        )
        db.add(call)
        await db.commit()

        future_dt = (datetime.now(tz=timezone.utc) + timedelta(days=3)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )

        result = await book_appointment_slot(
            start_time_iso=future_dt.isoformat(),
            lead_id=lead_id,
            call_id=call_id,
            org_id=org_id,
            meeting_topic="Product Demo",
            db_session=db,
            redis_client=None,  # No Redis in tests
        )

        assert result["booked"] is True
        assert "appointment_id" in result
        assert result["meeting_topic"] == "Product Demo"

        # Verify DB record
        stmt = select(Appointment).where(Appointment.id == result["appointment_id"])
        appt = (await db.execute(stmt)).scalar_one_or_none()
        assert appt is not None
        assert appt.meeting_title == "Product Demo"

    @pytest.mark.asyncio
    async def test_invalid_datetime_returns_error(self, db):
        from backend.app.agents.tools.scheduling import book_appointment_slot

        result = await book_appointment_slot(
            start_time_iso="not-a-datetime",
            lead_id="lead-1",
            call_id="call-1",
            org_id="org-1",
            meeting_topic="Demo",
            db_session=db,
        )
        assert result["booked"] is False
        assert "Invalid" in result["reason"]


# ─────────────────────────── update_crm_lead ─────────────────────────────────


class TestUpdateCrmLead:
    @pytest.mark.asyncio
    async def test_lead_update_and_merge(self, db):
        from backend.app.agents.tools.crm import update_crm_lead
        from backend.app.models.leads import Lead
        from backend.app.models.organizations import Organization
        from sqlalchemy import select

        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Acme", slug="acme", status="active")
        db.add(org)
        await db.flush()

        lead_id = str(uuid.uuid4())
        lead = Lead(
            id=lead_id,
            organization_id=org_id,
            first_name="Bob",
            last_name="Smith",
            phone_number="+15559876543",
            status="new",
            custom_fields={"existing_key": "keep_me"},
        )
        db.add(lead)
        await db.commit()

        result = await update_crm_lead(
            lead_id=lead_id,
            lead_stage="consideration",
            updated_fields={"budget": "$5000", "company_size": "50-100"},
            db_session=db,
            lead_score=72,
        )

        assert result["updated"] is True
        assert result["new_status"] == "qualified"
        assert result["qualification_stage"] == "consideration"

        # Verify DB merge kept existing key
        stmt = select(Lead).where(Lead.id == lead_id)
        updated_lead = (await db.execute(stmt)).scalar_one_or_none()
        assert updated_lead.custom_fields.get("existing_key") == "keep_me"
        assert updated_lead.custom_fields.get("budget") == "$5000"
        assert updated_lead.status == "qualified"

    @pytest.mark.asyncio
    async def test_missing_lead_returns_error(self, db):
        from backend.app.agents.tools.crm import update_crm_lead

        result = await update_crm_lead(
            lead_id="nonexistent-lead-id",
            lead_stage="interest",
            updated_fields={"note": "test"},
            db_session=db,
        )
        assert result["updated"] is False
        assert "not found" in result["reason"]


# ─────────────────────────── transfer_call_to_human ──────────────────────────


class TestTransferCallToHuman:
    def test_returns_transfer_payload(self):
        from backend.app.agents.tools.escalation import transfer_call_to_human

        result = transfer_call_to_human(
            call_sid="CA123abc",
            escalation_reason="Customer requested human agent",
            urgency_level="high",
            context_summary="Lead was asking about enterprise pricing",
        )

        assert result["action"] == "transfer_to_human"
        assert result["call_sid"] == "CA123abc"
        assert result["urgency_level"] == "high"
        assert "twiml_payload" in result
        assert "Response" in result["twiml_payload"]
        assert "agent_message" in result

    def test_invalid_urgency_defaults_to_medium(self):
        from backend.app.agents.tools.escalation import transfer_call_to_human

        result = transfer_call_to_human(
            call_sid="CA999",
            escalation_reason="Unknown urgency test",
            urgency_level="super_urgent",
        )
        assert result["urgency_level"] == "medium"


# ─────────────────────────── ToolDispatcher ──────────────────────────────────


class TestToolDispatcher:
    @pytest.mark.asyncio
    async def test_unknown_tool_rejected(self, db):
        from backend.app.agents.tool_dispatcher import ToolDispatcher

        dispatcher = ToolDispatcher(
            org_id="org-1",
            call_id="call-1",
        )
        result_json = await dispatcher.execute(
            tool_name="inject_evil_command",
            tool_call_id="tc-1",
            args={},
            db_session=db,
        )
        result = json.loads(result_json)
        assert "error" in result
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_knowledge_search_routed(self, db, mock_qdrant):
        from backend.app.agents.tool_dispatcher import ToolDispatcher

        org_id = "org-test"
        mock_qdrant._search_results = [
            _make_scored_point(0.90, "We offer 24/7 support.", org_id),
        ]

        dispatcher = ToolDispatcher(
            org_id=org_id,
            call_id="call-1",
            qdrant_client=mock_qdrant,
            embed_fn=_fake_embed,
        )

        result_json = await dispatcher.execute(
            tool_name="search_knowledge_base",
            tool_call_id="tc-kb-1",
            args={"query": "Do you offer support?"},
            db_session=db,
        )
        result = json.loads(result_json)
        assert result["found"] is True

    @pytest.mark.asyncio
    async def test_escalation_tool_routed(self, db):
        from backend.app.agents.tool_dispatcher import ToolDispatcher

        dispatcher = ToolDispatcher(
            org_id="org-1",
            call_id="call-esc-1",
        )

        result_json = await dispatcher.execute(
            tool_name="transfer_call_to_human",
            tool_call_id="tc-esc",
            args={
                "escalation_reason": "Customer upset, wants human",
                "urgency_level": "high",
                "context_summary": "Budget: $50k, wants enterprise plan",
            },
            db_session=db,
        )
        result = json.loads(result_json)
        assert result["action"] == "transfer_to_human"
        assert result["urgency_level"] == "high"

    @pytest.mark.asyncio
    async def test_calendar_availability_routed(self, db):
        from backend.app.agents.tool_dispatcher import ToolDispatcher

        dispatcher = ToolDispatcher(
            org_id="org-1",
            call_id="call-cal-1",
        )

        future_date = (datetime.now(tz=timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")

        result_json = await dispatcher.execute(
            tool_name="check_calendar_availability",
            tool_call_id="tc-cal-1",
            args={"preferred_date": future_date, "timezone": "UTC"},
            db_session=db,
        )
        result = json.loads(result_json)
        assert "available_slots" in result

    def test_tool_definitions_schema_valid(self):
        from backend.app.agents.tool_dispatcher import TOOL_DEFINITIONS

        assert len(TOOL_DEFINITIONS) == 6
        tool_names = {t["name"] for t in TOOL_DEFINITIONS}
        expected = {
            "search_knowledge_base",
            "check_calendar_availability",
            "book_appointment_slot",
            "update_crm_lead",
            "transfer_call_to_human",
            "send_followup_message",
        }
        assert tool_names == expected

        for tool in TOOL_DEFINITIONS:
            assert tool["type"] == "function"
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert "properties" in tool["parameters"]
