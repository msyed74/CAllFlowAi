"""
Calls API router.

Provides endpoints to list calls, inspect call details with transcripts and summaries,
and trigger real-time supervisor interventions (whisper, takeover).
"""

import logging
from typing import Annotated, Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user
from backend.app.core.database import get_db
from backend.app.models.appointments import Appointment
from backend.app.models.calls import Call, CallSummary, CallTranscript
from backend.app.models.lead_scores import LeadScore
from backend.app.models.leads import Lead
from backend.app.models.users import User
from backend.app.telephony.live_dashboard_ws import dashboard_manager
from backend.app.telephony.outbound_dialer import initiate_outbound_call

logger = logging.getLogger("api.v1.calls")

router = APIRouter(prefix="/calls", tags=["Calls Management"])


class OutboundCallRequest(BaseModel):
    lead_id: str
    force_bypass_tcpa: Optional[bool] = False


class WhisperRequest(BaseModel):
    message: str


class TakeoverRequest(BaseModel):
    reason: Optional[str] = "Supervisor manual takeover"


@router.get("", response_model=Dict[str, Any])
async def list_calls(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List calls for the authenticated user's organization."""
    org_id = current_user.organization_id
    query = select(Call).where(Call.organization_id == org_id)

    if status_filter:
        query = query.where(Call.status == status_filter.lower())

    query = query.order_by(Call.created_at.desc()).limit(limit).offset(offset)
    calls = (await db.execute(query)).scalars().all()

    # Get total count
    count_query = select(func.count(Call.id)).where(Call.organization_id == org_id)
    if status_filter:
        count_query = count_query.where(Call.status == status_filter.lower())
    total = (await db.execute(count_query)).scalar() or 0

    results = []
    for c in calls:
        results.append({
            "id": c.id,
            "direction": c.direction,
            "status": c.status,
            "from_number": c.from_number,
            "to_number": c.to_number,
            "duration_seconds": c.duration_seconds,
            "lead_id": c.lead_id,
            "campaign_id": c.campaign_id,
            "initiated_at": c.initiated_at.isoformat() if c.initiated_at else None,
            "ended_at": c.ended_at.isoformat() if c.ended_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": results,
    }


@router.get("/{call_id}", response_model=Dict[str, Any])
async def get_call_details(
    call_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Retrieve full call details including transcripts, summary, and lead score."""
    stmt = select(Call).where(
        Call.id == call_id,
        Call.organization_id == current_user.organization_id,
    )
    call = (await db.execute(stmt)).scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    # Transcripts
    t_stmt = (
        select(CallTranscript)
        .where(CallTranscript.call_id == call_id)
        .order_by(CallTranscript.start_time_ms.asc(), CallTranscript.created_at.asc())
    )
    transcripts = (await db.execute(t_stmt)).scalars().all()

    # Summary
    s_stmt = select(CallSummary).where(CallSummary.call_id == call_id)
    summary = (await db.execute(s_stmt)).scalar_one_or_none()

    # Lead Score
    score_stmt = select(LeadScore).where(LeadScore.call_id == call_id)
    lead_score = (await db.execute(score_stmt)).scalar_one_or_none()

    # Lead
    lead = None
    if call.lead_id:
        l_stmt = select(Lead).where(Lead.id == call.lead_id)
        lead = (await db.execute(l_stmt)).scalar_one_or_none()

    # Appointment
    appt_stmt = select(Appointment).where(Appointment.call_id == call_id)
    appt = (await db.execute(appt_stmt)).scalar_one_or_none()

    return {
        "id": call.id,
        "organization_id": call.organization_id,
        "lead_id": call.lead_id,
        "direction": call.direction,
        "status": call.status,
        "from_number": call.from_number,
        "to_number": call.to_number,
        "duration_seconds": call.duration_seconds,
        "created_at": call.created_at.isoformat() if call.created_at else None,
        "lead": {
            "id": lead.id,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "email": lead.email,
            "phone_number": lead.phone_number,
            "status": lead.status,
        } if lead else None,
        "transcripts": [
            {
                "id": t.id,
                "speaker_role": t.speaker_role,
                "content": t.content,
                "start_time_ms": t.start_time_ms,
                "end_time_ms": t.end_time_ms,
                "is_interrupted": t.is_interrupted,
            }
            for t in transcripts
        ],
        "summary": {
            "id": summary.id,
            "executive_summary": summary.executive_summary,
            "sentiment_overall": summary.sentiment_overall,
            "qualification_status": summary.qualification_status,
            "pain_points": summary.pain_points,
            "objections_raised": summary.objections_raised,
            "action_items": summary.action_items,
            "recommended_follow_up": summary.recommended_follow_up,
        } if summary else None,
        "lead_score": {
            "id": lead_score.id,
            "composite_score": lead_score.composite_score,
            "budget_score": lead_score.budget_score,
            "authority_score": lead_score.authority_score,
            "need_score": lead_score.need_score,
            "timeline_score": lead_score.timeline_score,
            "reasoning": lead_score.reasoning,
        } if lead_score else None,
        "appointment": {
            "id": appt.id,
            "meeting_title": appt.meeting_title,
            "start_time": appt.start_time.isoformat(),
            "end_time": appt.end_time.isoformat(),
            "status": appt.status,
        } if appt else None,
    }


@router.post("/{call_id}/whisper")
async def supervisor_whisper(
    call_id: str,
    payload: WhisperRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Injects a real-time supervisor whisper instruction into an active voice agent."""
    success = await dashboard_manager.inject_whisper(call_id, payload.message)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to inject whisper: call is not active or agent is not listening.",
        )
    return {"status": "delivered", "call_id": call_id}


@router.post("/{call_id}/takeover")
async def supervisor_takeover(
    call_id: str,
    payload: TakeoverRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Triggers an immediate supervisor takeover / human transfer for the active call."""
    success = await dashboard_manager.trigger_takeover(call_id, payload.reason or "Supervisor takeover")
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to trigger takeover: call is not currently active.",
        )
    return {"status": "transfer_initiated", "call_id": call_id}


@router.post("/outbound", response_model=Dict[str, Any])
async def trigger_outbound_call(
    payload: OutboundCallRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Initiates an outbound AI phone call to a lead with TCPA and DNC validation."""
    try:
        result = await initiate_outbound_call(
            lead_id=payload.lead_id,
            organization_id=current_user.organization_id,
            db_session=db,
            force_bypass_tcpa=payload.force_bypass_tcpa or False,
        )
        return result
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Outbound call initiation error: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
