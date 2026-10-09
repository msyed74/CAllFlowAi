"""
Phase 4 Tests: Post-Call Intelligence, Lead Scoring, Communication, and Workflow Automation.

Tests verify:
  1. PostCallAnalysisAgent structured output, BANT scoring, and DB persistence.
  2. Resilient fallback handling when LLM returns invalid or error output.
  3. CommunicationAgent SMS dispatch, appointment confirmation, and Message DB persistence.
  4. send_followup_message tool execution via ToolDispatcher.
  5. n8n workflow bridge execution and AutomationJob tracking.
  6. End-to-end run_post_call_pipeline orchestration.
  7. Telephony status-callback webhook triggering background analysis on call completion.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.communication_agent import CommunicationAgent
from backend.app.agents.post_call_analysis import (
    BANTLeadScoreSchema,
    PostCallAnalysisAgent,
    PostCallAnalysisResult,
    SentimentAnalysisSchema,
)
from backend.app.agents.post_call_pipeline import run_post_call_pipeline
from backend.app.agents.tool_dispatcher import ToolDispatcher
from backend.app.automation.n8n import trigger_n8n_workflow
from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.models.appointments import Appointment
from backend.app.models.automation import AutomationJob, Message
from backend.app.models.calls import Call, CallSummary, CallTranscript
from backend.app.models.lead_scores import LeadScore
from backend.app.models.leads import Lead
from backend.app.models.organizations import Organization
from tests.conftest import TestAsyncSessionLocal, test_engine


# ---------------------------------------------------------------------------
# Test Fixtures & Mock Generators
# ---------------------------------------------------------------------------

@pytest.fixture
async def db():
    """Fresh in-memory SQLite database for each test function."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestAsyncSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_mock_llm_response(composite_score: int = 85, qualification_status: str = "qualified") -> str:
    """Generates valid JSON matching PostCallAnalysisResult schema."""
    data = {
        "executive_summary": (
            "The prospect is the VP of Operations at an enterprise logistics firm looking to automate "
            "inbound support calls. They have an allocated budget of $25,000 and target a rollout next quarter."
        ),
        "lead_score": {
            "composite_score": composite_score,
            "budget_score": 22,
            "authority_score": 24,
            "need_score": 20,
            "timeline_score": 19,
            "rationale": "High decision authority with allocated quarterly budget and urgent need for call automation.",
        },
        "pain_points": [
            "Current call center has high wait times during peak hours",
            "Agents spend 40% of time answering repetitive FAQ questions",
        ],
        "objections_raised": [
            "Concerned about AI latency on VoIP phone lines",
        ],
        "sentiment_analysis": {
            "overall": "positive",
            "sentiment_trajectory": "improved",
        },
        "action_items": [
            "Send technical latency benchmark whitepaper",
            "Confirm scheduled product demo with sales engineering team",
        ],
        "suggested_follow_up": "Hi Jane, thrilled to connect today! Attached is the latency report we discussed.",
        "qualification_status": qualification_status,
    }
    return json.dumps(data)


# ---------------------------------------------------------------------------
# 1. PostCallAnalysisAgent Tests
# ---------------------------------------------------------------------------

class TestPostCallAnalysisAgent:
    @pytest.mark.asyncio
    async def test_successful_call_analysis_and_persistence(self, db: AsyncSession):
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Acme Logistics", slug="acme-logistics", status="active")
        db.add(org)

        lead_id = str(uuid.uuid4())
        lead = Lead(
            id=lead_id,
            organization_id=org_id,
            first_name="Jane",
            last_name="Doe",
            phone_number="+15551234567",
            status="contacted",
            custom_fields={},
        )
        db.add(lead)

        call_id = str(uuid.uuid4())
        call = Call(
            id=call_id,
            organization_id=org_id,
            lead_id=lead_id,
            direction="inbound",
            from_number="+15551234567",
            to_number="+18005550199",
            status="completed",
            twilio_call_sid=f"CA{call_id.replace('-', '')[:32]}",
        )
        db.add(call)

        # Add transcripts
        t1 = CallTranscript(
            id=str(uuid.uuid4()),
            call_id=call_id,
            speaker_role="assistant",
            content="Hello! This is CallFlow AI. How can I help your business today?",
            start_time_ms=0,
            end_time_ms=3000,
        )
        t2 = CallTranscript(
            id=str(uuid.uuid4()),
            call_id=call_id,
            speaker_role="user",
            content="We want to automate 5,000 inbound customer calls a month. We have budget allocated.",
            start_time_ms=3500,
            end_time_ms=7500,
        )
        db.add_all([t1, t2])
        await db.commit()

        # Mock LLM function
        mock_llm = AsyncMock(return_value=_make_mock_llm_response(composite_score=88, qualification_status="qualified"))
        agent = PostCallAnalysisAgent(llm_client_fn=mock_llm)

        result = await agent.analyze_call(call_id=call_id, db_session=db)

        assert result["call_id"] == call_id
        assert result["organization_id"] == org_id
        assert result["lead_id"] == lead_id
        assert result["analysis"]["lead_score"]["composite_score"] == 88
        assert result["analysis"]["qualification_status"] == "qualified"

        # Verify CallSummary persisted in DB
        summary_stmt = select(CallSummary).where(CallSummary.call_id == call_id)
        summary = (await db.execute(summary_stmt)).scalar_one_or_none()
        assert summary is not None
        assert "enterprise logistics firm" in summary.executive_summary
        assert summary.sentiment_overall == "positive"
        assert len(summary.pain_points) == 2
        assert len(summary.objections_raised) == 1

        # Verify LeadScore persisted in DB
        score_stmt = select(LeadScore).where(LeadScore.call_id == call_id)
        lead_score = (await db.execute(score_stmt)).scalar_one_or_none()
        assert lead_score is not None
        assert lead_score.composite_score == 88
        assert lead_score.budget_score == 22
        assert lead_score.authority_score == 24

        # Verify Lead updated in DB
        lead_stmt = select(Lead).where(Lead.id == lead_id)
        updated_lead = (await db.execute(lead_stmt)).scalar_one_or_none()
        assert updated_lead is not None
        assert updated_lead.status == "qualified"
        assert updated_lead.custom_fields.get("latest_lead_score") == 88

    @pytest.mark.asyncio
    async def test_llm_failure_resilient_fallback(self, db: AsyncSession):
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Test Corp", slug="test-corp", status="active")
        db.add(org)

        call_id = str(uuid.uuid4())
        call = Call(
            id=call_id,
            organization_id=org_id,
            direction="outbound",
            from_number="+18005550199",
            to_number="+15559876543",
            status="completed",
            twilio_call_sid=f"CA{call_id.replace('-', '')[:32]}",
        )
        db.add(call)
        await db.commit()

        # LLM raises exception
        async def failing_llm(*args, **kwargs):
            raise RuntimeError("OpenAI rate limit error 429")

        agent = PostCallAnalysisAgent(llm_client_fn=failing_llm)
        result = await agent.analyze_call(call_id=call_id, db_session=db)

        assert result["call_id"] == call_id
        # Fallback summary should still be saved
        summary_stmt = select(CallSummary).where(CallSummary.call_id == call_id)
        summary = (await db.execute(summary_stmt)).scalar_one_or_none()
        assert summary is not None
        assert "fallback" in summary.executive_summary.lower() or "error" in summary.executive_summary.lower()


# ---------------------------------------------------------------------------
# 2. CommunicationAgent Tests
# ---------------------------------------------------------------------------

class TestCommunicationAgent:
    @pytest.mark.asyncio
    async def test_send_sms_records_message(self, db: AsyncSession):
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Test Org", slug="test-org", status="active")
        db.add(org)
        await db.commit()

        comm_agent = CommunicationAgent(
            account_sid="ACplaceholder",
            auth_token="placeholder_token",
            from_phone_number="+18005550199",
        )

        msg = await comm_agent.send_sms(
            organization_id=org_id,
            recipient="+15551234567",
            content="Hello from CallFlow AI test!",
            db_session=db,
        )

        assert msg.id is not None
        assert msg.channel == "sms"
        assert msg.direction == "outbound"
        assert msg.delivery_status == "sent"
        assert msg.content == "Hello from CallFlow AI test!"

        # Verify DB persistence
        stmt = select(Message).where(Message.id == msg.id)
        saved = (await db.execute(stmt)).scalar_one_or_none()
        assert saved is not None

    @pytest.mark.asyncio
    async def test_send_appointment_confirmation(self, db: AsyncSession):
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Test Org", slug="test-org-2", status="active")
        db.add(org)

        lead_id = str(uuid.uuid4())
        lead = Lead(
            id=lead_id,
            organization_id=org_id,
            first_name="Alice",
            phone_number="+15559876543",
            status="qualified",
        )
        db.add(lead)

        call_id = str(uuid.uuid4())
        call = Call(
            id=call_id,
            organization_id=org_id,
            lead_id=lead_id,
            direction="inbound",
            from_number="+15559876543",
            to_number="+18005550199",
            status="completed",
            twilio_call_sid=f"CA{call_id.replace('-', '')[:32]}",
        )
        db.add(call)

        start_time = datetime.now(timezone.utc) + timedelta(days=2)
        appt = Appointment(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            lead_id=lead_id,
            call_id=call_id,
            meeting_title="Sales Strategy Call",
            start_time=start_time,
            end_time=start_time + timedelta(minutes=30),
            timezone="UTC",
            status="confirmed",
        )
        db.add(appt)
        await db.commit()

        comm_agent = CommunicationAgent()
        msg = await comm_agent.send_appointment_confirmation(call_id=call_id, db_session=db)

        assert msg is not None
        assert msg.recipient == "+15559876543"
        assert "Alice" in msg.content
        assert "Sales Strategy Call" in msg.content


# ---------------------------------------------------------------------------
# 3. send_followup_message Tool & ToolDispatcher Integration Tests
# ---------------------------------------------------------------------------

class TestSendFollowupMessageTool:
    @pytest.mark.asyncio
    async def test_followup_tool_dispatched_successfully(self, db: AsyncSession):
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Test Org", slug="test-org-3", status="active")
        db.add(org)

        lead_id = str(uuid.uuid4())
        lead = Lead(
            id=lead_id,
            organization_id=org_id,
            first_name="Bob",
            phone_number="+15554443322",
            status="contacted",
        )
        db.add(lead)

        call_id = str(uuid.uuid4())
        call = Call(
            id=call_id,
            organization_id=org_id,
            lead_id=lead_id,
            direction="outbound",
            from_number="+18005550199",
            to_number="+15554443322",
            status="in_progress",
            twilio_call_sid=f"CA{call_id.replace('-', '')[:32]}",
        )
        db.add(call)
        await db.commit()

        dispatcher = ToolDispatcher(org_id=org_id, call_id=call_id)

        result_json = await dispatcher.execute(
            tool_name="send_followup_message",
            tool_call_id="call_msg_123",
            args={
                "channel": "sms",
                "message_type": "product_brochure",
                "custom_note": "As promised during our call",
            },
            db_session=db,
            lead_id=lead_id,
        )

        res = json.loads(result_json)
        assert res["sent"] is True
        assert res["channel"] == "sms"
        assert res["recipient"] == "+15554443322"
        assert "message_id" in res


# ---------------------------------------------------------------------------
# 4. n8n Automation Bridge Tests
# ---------------------------------------------------------------------------

class TestN8nAutomationBridge:
    @pytest.mark.asyncio
    async def test_trigger_n8n_workflow_success(self, db: AsyncSession):
        org_id = str(uuid.uuid4())
        mock_http = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "workflow_execution_id": "exec_999"}'
        mock_http.post = AsyncMock(return_value=mock_resp)

        job = await trigger_n8n_workflow(
            organization_id=org_id,
            workflow_name="call-completed-sync",
            payload={"call_id": "call_123", "score": 90},
            db_session=db,
            call_id="call_123",
            http_client=mock_http,
        )

        assert job.id is not None
        assert job.status == "success"
        assert job.response_code == 200
        assert "exec_999" in job.response_body

    @pytest.mark.asyncio
    async def test_trigger_n8n_workflow_unreachable_fails_gracefully(self, db: AsyncSession):
        org_id = str(uuid.uuid4())
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=Exception("Connection refused to n8n"))

        job = await trigger_n8n_workflow(
            organization_id=org_id,
            workflow_name="call-completed-sync",
            payload={"call_id": "call_123"},
            db_session=db,
            call_id="call_123",
            http_client=mock_http,
        )

        assert job.id is not None
        assert job.status == "failed"
        assert job.retry_count == 1
        assert "Connection refused" in job.response_body


# ---------------------------------------------------------------------------
# 5. End-to-End run_post_call_pipeline Orchestration Tests
# ---------------------------------------------------------------------------

class TestPostCallPipelineOrchestrator:
    @pytest.mark.asyncio
    async def test_full_pipeline_orchestration(self):
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with TestAsyncSessionLocal() as db:
            org_id = str(uuid.uuid4())
            org = Organization(id=org_id, name="Delta AI", slug="delta-ai", status="active")
            db.add(org)

            lead_id = str(uuid.uuid4())
            lead = Lead(
                id=lead_id,
                organization_id=org_id,
                first_name="Charles",
                last_name="Xavier",
                phone_number="+15557778899",
                email="charles@xavier.edu",
                status="contacted",
            )
            db.add(lead)

            call_id = str(uuid.uuid4())
            call = Call(
                id=call_id,
                organization_id=org_id,
                lead_id=lead_id,
                direction="inbound",
                from_number="+15557778899",
                to_number="+18005550199",
                duration_seconds=185,
                status="completed",
                twilio_call_sid=f"CA{call_id.replace('-', '')[:32]}",
            )
            db.add(call)

            start_time = datetime.now(timezone.utc) + timedelta(days=1)
            appt = Appointment(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                lead_id=lead_id,
                call_id=call_id,
                meeting_title="Product Architecture Review",
                start_time=start_time,
                end_time=start_time + timedelta(minutes=45),
                status="confirmed",
            )
            db.add(appt)
            await db.commit()

        # Mock LLM and mock n8n HTTP client
        mock_llm = AsyncMock(return_value=_make_mock_llm_response(composite_score=92))
        analysis_agent = PostCallAnalysisAgent(llm_client_fn=mock_llm)

        mock_n8n_http = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "queued"}'
        mock_n8n_http.post = AsyncMock(return_value=mock_resp)

        pipeline_result = await run_post_call_pipeline(
            call_id=call_id,
            session_maker=TestAsyncSessionLocal,
            post_call_agent=analysis_agent,
            n8n_http_client=mock_n8n_http,
        )

        assert pipeline_result["call_id"] == call_id
        assert pipeline_result["analysis"]["analysis"]["lead_score"]["composite_score"] == 92
        assert pipeline_result["sms_dispatched"] is not None
        assert pipeline_result["sms_dispatched"]["recipient"] == "+15557778899"
        assert pipeline_result["n8n_job"]["status"] == "success"

        # Verify DB state
        async with TestAsyncSessionLocal() as db:
            summary = (await db.execute(select(CallSummary).where(CallSummary.call_id == call_id))).scalar_one_or_none()
            assert summary is not None

            lead_score = (await db.execute(select(LeadScore).where(LeadScore.call_id == call_id))).scalar_one_or_none()
            assert lead_score is not None
            assert lead_score.composite_score == 92

            job = (await db.execute(select(AutomationJob).where(AutomationJob.call_id == call_id))).scalar_one_or_none()
            assert job is not None
            assert job.workflow_name == "call-completed-sync"

        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# 6. Status Callback Webhook Integration Tests
# ---------------------------------------------------------------------------

class TestStatusCallbackTrigger:
    @pytest.mark.asyncio
    async def test_status_callback_completed_triggers_pipeline(self, client: AsyncClient, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Test Org", slug="test-org-sc", status="active")
        db_session.add(org)

        call_id = str(uuid.uuid4())
        call = Call(
            id=call_id,
            organization_id=org_id,
            direction="inbound",
            from_number="+15551112233",
            to_number="+18005550199",
            status="in_progress",
            twilio_call_sid="CAstatuscallback1234567890abcdef",
        )
        db_session.add(call)
        await db_session.commit()

        # Enable pipeline for this test and patch run_post_call_pipeline
        app.state.enable_post_call_pipeline = True
        try:
            with patch("backend.app.telephony.webhooks.run_post_call_pipeline", new_callable=AsyncMock) as mock_pipeline:
                payload = {
                    "CallSid": "CAstatuscallback1234567890abcdef",
                    "CallStatus": "completed",
                    "CallDuration": 120,
                }
                response = await client.post("/api/v1/telephony/status-callback", data=payload)
                assert response.status_code == 200

                # Verify background task was scheduled with call_id
                mock_pipeline.assert_called_once()
                assert mock_pipeline.call_args[0][0] == call_id
        finally:
            app.state.enable_post_call_pipeline = False
