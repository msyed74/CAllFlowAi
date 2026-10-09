"""
Communication Agent (Follow-Up Messaging & Delivery).

Handles automated dispatch of confirmation SMS, calendar invites, and follow-up
collateral via Twilio Messaging API and Email channels.
Persists every outgoing interaction to the `messages` table for compliance and tracking.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.appointments import Appointment
from backend.app.models.automation import Message
from backend.app.models.calls import Call
from backend.app.models.leads import Lead

logger = logging.getLogger("agents.communication_agent")


class CommunicationAgent:
    """
    Dispatches outbound communications (SMS, Email) and tracks delivery state
    in the database.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_phone_number: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.from_phone_number = from_phone_number or settings.TWILIO_DEFAULT_PHONE_NUMBER
        self._http_client = http_client

    async def _send_twilio_sms(
        self,
        to_number: str,
        body: str,
        from_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Low-level Twilio REST API SMS dispatch."""
        from_num = from_number or self.from_phone_number
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {
            "To": to_number,
            "From": from_num,
            "Body": body,
        }

        # If dummy placeholder credentials in dev/test, mock successful dispatch
        if "placeholder" in self.account_sid.lower() or "placeholder" in self.auth_token.lower():
            mock_sid = f"SM{uuid.uuid4().hex}"
            logger.info("Mock Twilio SMS dispatched to %s (SID: %s): %s", to_number, mock_sid, body)
            return {"sid": mock_sid, "status": "queued"}

        if self._http_client:
            resp = await self._http_client.post(
                url,
                data=data,
                auth=(self.account_sid, self.auth_token),
            )
        else:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    data=data,
                    auth=(self.account_sid, self.auth_token),
                )

        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Twilio SMS error {resp.status_code}: {resp.text}")

        return resp.json()

    async def send_sms(
        self,
        organization_id: str,
        recipient: str,
        content: str,
        db_session: AsyncSession,
        lead_id: Optional[str] = None,
        call_id: Optional[str] = None,
        sender_override: Optional[str] = None,
    ) -> Message:
        """
        Sends an SMS to the recipient and logs a Message record in the database.
        """
        msg_id = str(uuid.uuid4())
        sender = sender_override or self.from_phone_number
        provider_sid = None
        delivery_status = "sent"
        error_msg = None

        try:
            res = await self._send_twilio_sms(to_number=recipient, body=content, from_number=sender)
            provider_sid = res.get("sid")
            delivery_status = "sent" if res.get("status") in ("sent", "queued") else "failed"
        except Exception as e:
            logger.error("Failed to send SMS to %s: %s", recipient, e)
            delivery_status = "failed"
            error_msg = str(e)

        msg_rec = Message(
            id=msg_id,
            organization_id=organization_id,
            lead_id=lead_id,
            call_id=call_id,
            channel="sms",
            direction="outbound",
            sender=sender,
            recipient=recipient,
            content=content,
            external_provider_id=provider_sid,
            delivery_status=delivery_status,
            error_message=error_msg,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(msg_rec)
        await db_session.commit()
        await db_session.refresh(msg_rec)
        return msg_rec

    async def send_appointment_confirmation(
        self,
        call_id: str,
        db_session: AsyncSession,
    ) -> Optional[Message]:
        """
        Finds any confirmed appointment for the call and sends an immediate SMS confirmation.
        """
        appt_stmt = select(Appointment).where(
            Appointment.call_id == call_id,
            Appointment.status == "confirmed",
        )
        appt = (await db_session.execute(appt_stmt)).scalar_one_or_none()
        if not appt:
            logger.debug("No confirmed appointment found for call %s to send confirmation.", call_id)
            return None

        # Fetch lead for phone number
        lead_stmt = select(Lead).where(Lead.id == appt.lead_id)
        lead = (await db_session.execute(lead_stmt)).scalar_one_or_none()
        if not lead or not lead.phone_number:
            logger.warning("Lead %s has no valid phone number for appointment confirmation.", appt.lead_id)
            return None

        time_str = appt.start_time.strftime("%A, %B %d at %I:%M %p UTC")
        sms_text = (
            f"Hello {lead.first_name or 'there'}! Your appointment for '{appt.meeting_title}' "
            f"has been confirmed for {time_str}. If you need to reschedule, reply to this text."
        )

        return await self.send_sms(
            organization_id=appt.organization_id,
            recipient=lead.phone_number,
            content=sms_text,
            db_session=db_session,
            lead_id=lead.id,
            call_id=call_id,
        )
