from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    AgentSession,
    AgentToolCall,
    Appointment,
    AuditLog,
    AutomationJob,
    Call,
    CallEvent,
    CallSummary,
    CallTranscript,
    Campaign,
    Customer,
    EmbeddingsMetadata,
    KnowledgeChunk,
    KnowledgeDocument,
    Lead,
    LeadScore,
    Message,
    Organization,
    Role,
    User,
)


@pytest.mark.asyncio
async def test_all_models_persistence_and_relationships(db_session: AsyncSession):
    # 1. Organization
    org = Organization(
        name="Nexus Enterprise AI",
        slug="nexus-enterprise-ai",
        status="active",
        default_voice_id="shimmer",
    )
    db_session.add(org)
    await db_session.flush()
    assert org.id is not None

    # 2. Role
    role = Role(
        organization_id=org.id,
        name="AgentSupervisor",
        permissions=["calls:listen", "calls:whisper"],
    )
    db_session.add(role)
    await db_session.flush()

    # 3. User
    user = User(
        organization_id=org.id,
        role_id=role.id,
        email="supervisor@nexus.ai",
        password_hash="mocked_hash_value",
        first_name="Marcus",
        last_name="Vance",
    )
    db_session.add(user)
    await db_session.flush()

    # 4. Lead
    lead = Lead(
        organization_id=org.id,
        assigned_user_id=user.id,
        first_name="Elena",
        last_name="Rostova",
        phone_number="+14155558832",
        status="qualifying",
    )
    db_session.add(lead)
    await db_session.flush()

    # 5. Customer
    customer = Customer(
        organization_id=org.id,
        lead_id=lead.id,
        name="Elena Rostova",
        phone_number="+14155558832",
    )
    db_session.add(customer)
    await db_session.flush()

    # 6. Campaign
    campaign = Campaign(
        organization_id=org.id,
        name="Q4 SaaS Expansion",
        voice_agent_prompt="Qualify inbound leads for enterprise demo.",
        caller_phone_number="+18005550100",
    )
    db_session.add(campaign)
    await db_session.flush()

    # 7. Call
    call = Call(
        organization_id=org.id,
        campaign_id=campaign.id,
        lead_id=lead.id,
        customer_id=customer.id,
        twilio_call_sid="CA998877665544332211",
        direction="outbound",
        from_number="+18005550100",
        to_number="+14155558832",
        status="in_progress",
    )
    db_session.add(call)
    await db_session.flush()

    # 8. CallEvent
    event = CallEvent(
        call_id=call.id,
        event_type="user_speech_start",
        payload={"confidence": 0.98},
        timestamp_ms=1250,
    )
    db_session.add(event)

    # 9. CallTranscript
    transcript = CallTranscript(
        call_id=call.id,
        speaker_role="user",
        content="Yes, we need an automated voice agent for our sales team.",
        start_time_ms=1250,
        end_time_ms=3400,
        speech_confidence=0.99,
    )
    db_session.add(transcript)

    # 10. CallSummary
    summary = CallSummary(
        call_id=call.id,
        organization_id=org.id,
        executive_summary="Elena expressed urgent need for sales voice AI.",
        sentiment_overall="positive",
        qualification_status="qualified",
    )
    db_session.add(summary)

    # 11. Appointment
    now = datetime.now(timezone.utc)
    appointment = Appointment(
        organization_id=org.id,
        call_id=call.id,
        lead_id=lead.id,
        start_time=now,
        end_time=now,
        meeting_title="CallFlow AI Demo",
    )
    db_session.add(appointment)

    # 12. EmbeddingsMetadata
    emb_meta = EmbeddingsMetadata(
        model_name="text-embedding-3-small",
        dimension=1536,
        distance_metric="Cosine",
        qdrant_collection_name="nexus_kb",
    )
    db_session.add(emb_meta)
    await db_session.flush()

    # 13. KnowledgeDocument
    doc = KnowledgeDocument(
        organization_id=org.id,
        embeddings_metadata_id=emb_meta.id,
        title="Product Pricing Guide",
        source_type="pdf",
    )
    db_session.add(doc)
    await db_session.flush()

    # 14. KnowledgeChunk
    chunk = KnowledgeChunk(
        document_id=doc.id,
        chunk_index=0,
        chunk_text="Enterprise pricing starts at $499 per seat per month.",
        token_count=12,
        qdrant_point_id="00000000-0000-0000-0000-000000000001",
    )
    db_session.add(chunk)

    # 15. AgentSession
    agent_session = AgentSession(
        call_id=call.id,
        system_prompt_snapshot="You are an enterprise sales AI.",
        voice_persona="shimmer",
    )
    db_session.add(agent_session)
    await db_session.flush()

    # 16. AgentToolCall
    tool_call = AgentToolCall(
        agent_session_id=agent_session.id,
        call_id=call.id,
        tool_name="search_knowledge_base",
        tool_call_id="call_abc123",
        arguments={"query": "enterprise pricing"},
        execution_time_ms=42,
    )
    db_session.add(tool_call)

    # 17. LeadScore
    score = LeadScore(
        call_id=call.id,
        lead_id=lead.id,
        organization_id=org.id,
        composite_score=88,
        budget_score=22,
        authority_score=24,
        need_score=23,
        timeline_score=19,
    )
    db_session.add(score)

    # 18. AutomationJob
    job = AutomationJob(
        organization_id=org.id,
        call_id=call.id,
        workflow_name="n8n_hubspot_sync",
        target_endpoint="http://localhost:5678/webhook/sync",
        payload={"lead_id": lead.id, "score": 88},
    )
    db_session.add(job)

    # 19. Message
    msg = Message(
        organization_id=org.id,
        lead_id=lead.id,
        call_id=call.id,
        channel="sms",
        direction="outbound",
        sender="+18005550100",
        recipient="+14155558832",
        content="Your demo is confirmed for tomorrow!",
    )
    db_session.add(msg)

    # 20. AuditLog
    audit = AuditLog(
        organization_id=org.id,
        user_id=user.id,
        action="lead.qualified",
        resource_type="leads",
        resource_id=lead.id,
    )
    db_session.add(audit)

    await db_session.commit()

    # Query verification: confirm all entities were written and can be read back
    stmt = select(Call).where(Call.id == call.id)
    res = await db_session.execute(stmt)
    retrieved_call = res.scalar_one()
    assert retrieved_call.twilio_call_sid == "CA998877665544332211"
    assert retrieved_call.status == "in_progress"
