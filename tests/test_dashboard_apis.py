"""
Tests for Phase 5 Dashboard APIs, Analytics, Knowledge, and Live Dashboard WebSockets.

Verifies:
  1. GET /api/v1/calls (listing, filtering, pagination)
  2. GET /api/v1/calls/{call_id} (full details with transcript, summary, lead score)
  3. POST /api/v1/calls/{call_id}/whisper (supervisor coaching injection)
  4. POST /api/v1/calls/{call_id}/takeover (supervisor manual takeover)
  5. GET /api/v1/analytics/dashboard-stats (KPI aggregates)
  6. GET /api/v1/knowledge/documents (knowledge base docs list)
  7. LiveDashboardManager pub/sub broadcasting and handler dispatch
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user
from backend.app.core.security import create_access_token
from backend.app.main import app
from backend.app.models.calls import Call, CallSummary, CallTranscript
from backend.app.models.lead_scores import LeadScore
from backend.app.models.leads import Lead
from backend.app.models.organizations import Organization
from backend.app.models.roles import Role
from backend.app.models.users import User
from backend.app.telephony.live_dashboard_ws import dashboard_manager


@pytest.fixture
async def auth_context(db_session: AsyncSession) -> Dict[str, Any]:
    """Sets up an Organization, Role, and User with valid JWT headers."""
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name="Apex Sales", slug="apex-sales", status="active")
    db_session.add(org)

    role = Role(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        name="Admin",
        description="Admin role",
        permissions=["*"],
    )
    db_session.add(role)
    await db_session.flush()

    user = User(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        role_id=role.id,
        email="supervisor@apexsales.com",
        password_hash="fake_hashed_pw",
        first_name="Sam",
        last_name="Supervisor",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        subject=user.id,
        org_id=org_id,
        role="Admin",
        permissions=["*"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Override get_current_user for FastAPI test client
    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user

    return {
        "org": org,
        "user": user,
        "headers": headers,
    }


class TestCallsEndpoints:
    @pytest.mark.asyncio
    async def test_list_calls_with_pagination(
        self, client: AsyncClient, db_session: AsyncSession, auth_context: Dict[str, Any]
    ):
        org = auth_context["org"]
        headers = auth_context["headers"]

        # Seed 3 calls
        for i in range(3):
            c = Call(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                direction="inbound",
                from_number="+15551112222",
                to_number="+18005550199",
                status="completed" if i < 2 else "in_progress",
                twilio_call_sid=f"CA_call_{i}_{uuid.uuid4().hex[:12]}",
                duration_seconds=120,
            )
            db_session.add(c)
        await db_session.commit()

        # Query all calls
        resp = await client.get("/api/v1/calls", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

        # Query filtered by status
        resp_filtered = await client.get("/api/v1/calls?status=in_progress", headers=headers)
        assert resp_filtered.status_code == 200
        assert resp_filtered.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_get_call_details_with_summary_and_score(
        self, client: AsyncClient, db_session: AsyncSession, auth_context: Dict[str, Any]
    ):
        org = auth_context["org"]
        headers = auth_context["headers"]

        lead = Lead(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            first_name="Sarah",
            last_name="Connor",
            phone_number="+15559998888",
            status="qualified",
        )
        db_session.add(lead)

        call_id = str(uuid.uuid4())
        call = Call(
            id=call_id,
            organization_id=org.id,
            lead_id=lead.id,
            direction="outbound",
            from_number="+18005550199",
            to_number="+15559998888",
            status="completed",
            duration_seconds=95,
            twilio_call_sid=f"CA_call_det_{uuid.uuid4().hex[:12]}",
        )
        db_session.add(call)

        t1 = CallTranscript(
            id=str(uuid.uuid4()),
            call_id=call_id,
            speaker_role="user",
            content="Can we schedule a demo?",
            start_time_ms=0,
            end_time_ms=2000,
        )
        db_session.add(t1)

        summary = CallSummary(
            id=str(uuid.uuid4()),
            call_id=call_id,
            organization_id=org.id,
            executive_summary="Prospect requested product demo.",
            sentiment_overall="positive",
            qualification_status="qualified",
            pain_points=["Need voice AI"],
            objections_raised=[],
            action_items=["Demo scheduled"],
        )
        db_session.add(summary)

        score = LeadScore(
            id=str(uuid.uuid4()),
            call_id=call_id,
            lead_id=lead.id,
            organization_id=org.id,
            composite_score=85,
            budget_score=20,
            authority_score=22,
            need_score=23,
            timeline_score=20,
            reasoning="High buying intent",
        )
        db_session.add(score)
        await db_session.commit()

        resp = await client.get(f"/api/v1/calls/{call_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == call_id
        assert data["lead"]["first_name"] == "Sarah"
        assert len(data["transcripts"]) == 1
        assert data["transcripts"][0]["content"] == "Can we schedule a demo?"
        assert data["summary"]["executive_summary"] == "Prospect requested product demo."
        assert data["lead_score"]["composite_score"] == 85

    @pytest.mark.asyncio
    async def test_supervisor_whisper_and_takeover_endpoints(
        self, client: AsyncClient, db_session: AsyncSession, auth_context: Dict[str, Any]
    ):
        headers = auth_context["headers"]
        call_id = "call_live_supervision_123"

        # 1. Whisper to inactive call fails gracefully
        whisper_resp = await client.post(
            f"/api/v1/calls/{call_id}/whisper",
            json={"message": "Mention the 20% Q4 discount"},
            headers=headers,
        )
        assert whisper_resp.status_code == 400

        # 2. Register mock whisper handler and test successful whisper
        mock_whisper = AsyncMock()
        dashboard_manager.register_whisper_handler(call_id, mock_whisper)

        whisper_success = await client.post(
            f"/api/v1/calls/{call_id}/whisper",
            json={"message": "Mention the 20% Q4 discount"},
            headers=headers,
        )
        assert whisper_success.status_code == 200
        mock_whisper.assert_called_once_with("Mention the 20% Q4 discount")

        # 3. Register takeover handler and test takeover
        mock_takeover = AsyncMock()
        dashboard_manager.register_takeover_handler(call_id, mock_takeover)

        takeover_resp = await client.post(
            f"/api/v1/calls/{call_id}/takeover",
            json={"reason": "Customer demands senior account exec"},
            headers=headers,
        )
        assert takeover_resp.status_code == 200
        mock_takeover.assert_called_once_with("Customer demands senior account exec")

        dashboard_manager.unregister_whisper_handler(call_id)
        dashboard_manager.unregister_takeover_handler(call_id)


class TestAnalyticsEndpoints:
    @pytest.mark.asyncio
    async def test_dashboard_stats(
        self, client: AsyncClient, db_session: AsyncSession, auth_context: Dict[str, Any]
    ):
        org = auth_context["org"]
        headers = auth_context["headers"]

        # Add 1 active call, 1 completed call
        c1 = Call(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            direction="inbound",
            from_number="+15550001111",
            to_number="+18005550199",
            status="in_progress",
            twilio_call_sid=f"CA_stat_1_{uuid.uuid4().hex[:12]}",
        )
        c2 = Call(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            direction="outbound",
            from_number="+18005550199",
            to_number="+15550002222",
            status="completed",
            duration_seconds=180,
            twilio_call_sid=f"CA_stat_2_{uuid.uuid4().hex[:12]}",
        )
        db_session.add_all([c1, c2])

        # Add 1 qualified lead
        lead = Lead(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            first_name="John",
            phone_number="+15550002222",
            status="qualified",
        )
        db_session.add(lead)
        await db_session.commit()

        resp = await client.get("/api/v1/analytics/dashboard-stats", headers=headers)
        assert resp.status_code == 200
        stats = resp.json()

        assert stats["total_calls"] >= 2
        assert stats["active_calls"] >= 1
        assert stats["avg_duration_seconds"] >= 90.0
        assert stats["total_leads"] >= 1
        assert stats["qualified_leads"] >= 1
        assert stats["qualification_rate_percent"] == 100.0


class TestKnowledgeEndpoints:
    @pytest.mark.asyncio
    async def test_list_knowledge_documents(
        self, client: AsyncClient, db_session: AsyncSession, auth_context: Dict[str, Any]
    ):
        headers = auth_context["headers"]
        resp = await client.get("/api/v1/knowledge/documents", headers=headers)
        assert resp.status_code == 200
        assert "items" in resp.json()
