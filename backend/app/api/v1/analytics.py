"""
Analytics & Dashboard Metrics API router.

Provides aggregated KPIs for the supervisor and sales management console:
  - total_calls, active_calls, completed_calls
  - avg_duration_seconds
  - qualified_leads_count, qualification_rate
  - avg_lead_score
  - booked_appointments_count
"""

import logging
from typing import Annotated, Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user
from backend.app.core.database import get_db
from backend.app.models.appointments import Appointment
from backend.app.models.calls import Call, CallSummary
from backend.app.models.lead_scores import LeadScore
from backend.app.models.leads import Lead
from backend.app.models.users import User

logger = logging.getLogger("api.v1.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics & KPIs"])


@router.get("/dashboard-stats", response_model=Dict[str, Any])
async def get_dashboard_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Calculates operational and performance metrics for the organization."""
    org_id = current_user.organization_id

    # 1. Total Calls
    total_calls_stmt = select(func.count(Call.id)).where(Call.organization_id == org_id)
    total_calls = (await db.execute(total_calls_stmt)).scalar() or 0

    # 2. Active Calls
    active_calls_stmt = select(func.count(Call.id)).where(
        Call.organization_id == org_id,
        Call.status.in_(["in_progress", "ringing"]),
    )
    active_calls = (await db.execute(active_calls_stmt)).scalar() or 0

    # 3. Completed Calls & Avg Duration
    duration_stmt = select(func.avg(Call.duration_seconds)).where(
        Call.organization_id == org_id,
        Call.status == "completed",
    )
    avg_duration = round(float((await db.execute(duration_stmt)).scalar() or 0), 1)

    # 4. Total Leads & Qualified Count
    total_leads_stmt = select(func.count(Lead.id)).where(Lead.organization_id == org_id)
    total_leads = (await db.execute(total_leads_stmt)).scalar() or 0

    qualified_leads_stmt = select(func.count(Lead.id)).where(
        Lead.organization_id == org_id,
        Lead.status == "qualified",
    )
    qualified_leads = (await db.execute(qualified_leads_stmt)).scalar() or 0

    qualification_rate = round((qualified_leads / total_leads * 100), 1) if total_leads > 0 else 0.0

    # 5. Average BANT Composite Lead Score
    avg_score_stmt = select(func.avg(LeadScore.composite_score)).where(
        LeadScore.organization_id == org_id,
    )
    avg_lead_score = round(float((await db.execute(avg_score_stmt)).scalar() or 0), 1)

    # 6. Booked Appointments
    appts_stmt = select(func.count(Appointment.id)).where(
        Appointment.organization_id == org_id,
        Appointment.status == "confirmed",
    )
    total_appointments = (await db.execute(appts_stmt)).scalar() or 0

    return {
        "organization_id": org_id,
        "total_calls": total_calls,
        "active_calls": active_calls,
        "avg_duration_seconds": avg_duration,
        "total_leads": total_leads,
        "qualified_leads": qualified_leads,
        "qualification_rate_percent": qualification_rate,
        "avg_lead_score": avg_lead_score,
        "total_appointments_booked": total_appointments,
    }
