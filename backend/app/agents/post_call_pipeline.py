"""
End-to-End Post-Call Pipeline Orchestrator.

Triggered immediately after call termination (hang-up or status callback).
Coordinates:
  1. PostCallAnalysisAgent: transcript synthesis, BANT scoring, sentiment & intent.
  2. CommunicationAgent: immediate confirmation SMS/email if appointment was scheduled.
  3. n8n Automation Bridge: dispatches enriched CRM sync payload for external systems.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select

from backend.app.agents.communication_agent import CommunicationAgent
from backend.app.agents.post_call_analysis import PostCallAnalysisAgent
from backend.app.automation.n8n import trigger_n8n_workflow
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.appointments import Appointment
from backend.app.models.calls import Call
from backend.app.models.leads import Lead

logger = logging.getLogger("agents.post_call_pipeline")


async def run_post_call_pipeline(
    call_id: str,
    session_maker=None,
    post_call_agent: Optional[PostCallAnalysisAgent] = None,
    comm_agent: Optional[CommunicationAgent] = None,
    n8n_http_client=None,
) -> Dict[str, Any]:
    """
    Executes the complete post-call analysis, messaging, and CRM automation flow.
    """
    sm = session_maker or AsyncSessionLocal
    analysis_agent = post_call_agent or PostCallAnalysisAgent()
    messaging_agent = comm_agent or CommunicationAgent()

    logger.info("Starting post-call pipeline for Call %s", call_id)

    # 1. Post-Call Analysis & Intelligence Extraction
    async with sm() as db:
        analysis_result = await analysis_agent.analyze_call(call_id=call_id, db_session=db)

    # 2. Communication Follow-up (Appointment Confirmation SMS)
    sms_result = None
    async with sm() as db:
        msg_rec = await messaging_agent.send_appointment_confirmation(call_id=call_id, db_session=db)
        if msg_rec:
            sms_result = {
                "message_id": msg_rec.id,
                "recipient": msg_rec.recipient,
                "delivery_status": msg_rec.delivery_status,
            }

    # 3. n8n Workflow Automation (CRM Sync)
    n8n_result = None
    async with sm() as db:
        call_stmt = select(Call).where(Call.id == call_id)
        call = (await db.execute(call_stmt)).scalar_one_or_none()

        if call:
            lead_info = {}
            if call.lead_id:
                lead_stmt = select(Lead).where(Lead.id == call.lead_id)
                lead = (await db.execute(lead_stmt)).scalar_one_or_none()
                if lead:
                    lead_info = {
                        "id": lead.id,
                        "first_name": lead.first_name,
                        "last_name": lead.last_name,
                        "phone_number": lead.phone_number,
                        "email": lead.email,
                        "status": lead.status,
                    }

            # Check appointment
            appt_stmt = select(Appointment).where(
                Appointment.call_id == call_id,
                Appointment.status == "confirmed",
            )
            appt = (await db.execute(appt_stmt)).scalar_one_or_none()
            appt_info = None
            if appt:
                appt_info = {
                    "id": appt.id,
                    "title": appt.meeting_title,
                    "start_time": appt.start_time.isoformat(),
                    "end_time": appt.end_time.isoformat(),
                }

            workflow_payload = {
                "event": "call.completed",
                "call_id": call.id,
                "organization_id": call.organization_id,
                "direction": call.direction,
                "duration_seconds": call.duration_seconds,
                "lead": lead_info,
                "appointment": appt_info,
                "analysis": analysis_result.get("analysis", {}),
            }

            job = await trigger_n8n_workflow(
                organization_id=call.organization_id,
                workflow_name="call-completed-sync",
                payload=workflow_payload,
                db_session=db,
                call_id=call.id,
                http_client=n8n_http_client,
            )
            n8n_result = {
                "job_id": job.id,
                "status": job.status,
                "response_code": job.response_code,
            }

    logger.info("Post-call pipeline completed for Call %s", call_id)

    return {
        "call_id": call_id,
        "analysis": analysis_result,
        "sms_dispatched": sms_result,
        "n8n_job": n8n_result,
    }
