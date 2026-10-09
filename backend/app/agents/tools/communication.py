"""
Communication tool for the AI Voice Agent.

Called by the ToolDispatcher when the LLM invokes `send_followup_message`.
Dispatches an immediate SMS or Email to the lead and persists the message record.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.communication_agent import CommunicationAgent
from backend.app.models.calls import Call
from backend.app.models.leads import Lead

logger = logging.getLogger("agents.tools.communication")


async def send_followup_message(
    channel: str,
    message_type: str,
    call_id: str,
    org_id: str,
    lead_id: Optional[str],
    db_session: AsyncSession,
    custom_note: Optional[str] = None,
    communication_agent: Optional[CommunicationAgent] = None,
) -> Dict[str, Any]:
    """
    Executes the send_followup_message tool call.
    """
    comm_agent = communication_agent or CommunicationAgent()

    if not lead_id:
        return {
            "sent": False,
            "error": "No lead_id associated with this call to send follow-up.",
        }

    # Fetch Lead
    lead_stmt = select(Lead).where(Lead.id == lead_id)
    lead = (await db_session.execute(lead_stmt)).scalar_one_or_none()
    if not lead:
        return {
            "sent": False,
            "error": f"Lead {lead_id} not found.",
        }

    recipient = lead.phone_number if channel.lower() == "sms" else lead.email
    if not recipient:
        return {
            "sent": False,
            "error": f"Lead has no {channel.upper()} address configured.",
        }

    # Compose message text based on message_type
    first_name = lead.first_name or "there"
    if message_type == "product_brochure":
        body = f"Hi {first_name}, here is the overview brochure you requested: https://callflow.ai/overview. Let us know if you have questions!"
    elif message_type == "rep_contact_card":
        body = f"Hi {first_name}, here is our direct team contact card: Alex / CallFlow AI (alex@callflow.ai). We look forward to speaking again."
    elif message_type == "appointment_confirmation":
        body = f"Hi {first_name}, your meeting has been noted. We will send calendar details shortly."
    else:
        body = f"Hi {first_name}, thank you for speaking with CallFlow AI."

    if custom_note:
        body += f" Note: {custom_note}"

    msg_rec = await comm_agent.send_sms(
        organization_id=org_id,
        recipient=recipient,
        content=body,
        db_session=db_session,
        lead_id=lead.id,
        call_id=call_id,
    )

    return {
        "sent": msg_rec.delivery_status in ("sent", "delivered", "queued"),
        "channel": channel,
        "message_type": message_type,
        "recipient": recipient,
        "delivery_status": msg_rec.delivery_status,
        "message_id": msg_rec.id,
    }
