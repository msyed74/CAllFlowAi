from datetime import datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.agents.post_call_pipeline import run_post_call_pipeline
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.calls import Call
from backend.app.models.leads import Lead
from backend.app.models.organizations import Organization
from backend.app.telephony.security import verify_twilio_signature

router = APIRouter(prefix="/telephony", tags=["Telephony Webhooks"])


@router.post("/inbound")
async def handle_inbound_call(
    CallSid: Annotated[str, Form()],
    From: Annotated[str, Form()],
    To: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    _verified: Annotated[bool, Depends(verify_twilio_signature)] = True,
):
    """
    Twilio voice webhook for inbound calls.
    Resolves tenant, initializes call record, and returns TwiML with Media Stream connection.
    """
    # 1. Resolve Organization by To phone number (or fallback to first active org)
    org_stmt = select(Organization).where(Organization.twilio_phone_number == To)
    org = (await db.execute(org_stmt)).scalar_one_or_none()

    if not org:
        # Fallback to default active organization
        default_org_stmt = select(Organization).where(Organization.status == "active").limit(1)
        org = (await db.execute(default_org_stmt)).scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active organization found to route this inbound call",
        )

    # 2. Check if From number matches existing lead
    lead_stmt = select(Lead).where(
        Lead.organization_id == org.id,
        Lead.phone_number == From,
    )
    lead = (await db.execute(lead_stmt)).scalar_one_or_none()

    # 3. Create Call record
    call = Call(
        organization_id=org.id,
        lead_id=lead.id if lead else None,
        twilio_call_sid=CallSid,
        direction="inbound",
        from_number=From,
        to_number=To,
        status="ringing",
        initiated_at=datetime.now(timezone.utc),
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    # 4. Generate dynamic TwiML with bi-directional Media Stream
    media_stream_url = settings.TWILIO_MEDIA_STREAM_WS_URL
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{media_stream_url}">
            <Parameter name="organization_id" value="{org.id}" />
            <Parameter name="call_id" value="{call.id}" />
            <Parameter name="call_sid" value="{CallSid}" />
            <Parameter name="direction" value="inbound" />
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml_response, media_type="application/xml")


@router.post("/status-callback")
async def handle_status_callback(
    request: Request,
    CallSid: Annotated[str, Form()],
    CallStatus: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    CallDuration: Annotated[Optional[int], Form()] = None,
    _verified: Annotated[bool, Depends(verify_twilio_signature)] = True,
):
    """
    Twilio status callback webhook.
    Receives call state transitions (e.g., ringing, in-progress, completed, busy, no-answer).
    """
    stmt = select(Call).where(Call.twilio_call_sid == CallSid)
    call = (await db.execute(stmt)).scalar_one_or_none()

    if call:
        call.status = CallStatus.lower().replace("-", "_")
        if CallStatus in ("in-progress", "answered") and not call.answered_at:
            call.answered_at = datetime.now(timezone.utc)
        elif CallStatus in ("completed", "failed", "busy", "no-answer", "canceled"):
            call.ended_at = datetime.now(timezone.utc)
            if CallDuration is not None:
                call.duration_seconds = CallDuration
                call.billed_seconds = CallDuration
            # Trigger background post-call intelligence pipeline
            session_maker = getattr(request.app.state, "db_session_maker", None)
            enable_pipeline = getattr(request.app.state, "enable_post_call_pipeline", True)
            if enable_pipeline:
                background_tasks.add_task(run_post_call_pipeline, call.id, session_maker=session_maker)
        await db.commit()

    return Response(content="<Response/>", media_type="application/xml")


@router.post("/transfer-fallback")
async def handle_transfer_fallback():
    """TwiML fallback if live human agent transfer fails or times out."""
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">All of our specialists are currently busy assisting other clients. We have noted your request and a senior team member will call you back shortly. Goodbye.</Say>
    <Hangup/>
</Response>"""
    return Response(content=twiml, media_type="application/xml")
