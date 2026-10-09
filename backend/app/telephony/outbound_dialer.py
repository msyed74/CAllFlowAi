"""
Outbound Telephony Dialing Engine with TCPA Compliance.

Handles:
  1. TCPA calling time window validation (8:00 AM - 9:00 PM local recipient time).
  2. Do-Not-Call (DNC) opt-out verification.
  3. Twilio outbound call initiation bridging into bi-directional Media Streams.
"""

import logging
import uuid
from datetime import datetime, timezone, time
from typing import Any, Dict, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.calls import Call
from backend.app.models.leads import Lead
from backend.app.models.organizations import Organization

logger = logging.getLogger("telephony.outbound_dialer")

# Approximate US Area Code Timezone Mapping (Sample for TCPA compliance verification)
_PACIFIC_AREA_CODES = {"206", "213", "310", "415", "503", "619", "702", "818", "916", "949"}
_MOUNTAIN_AREA_CODES = {"303", "480", "505", "520", "602", "719", "801", "970"}
_CENTRAL_AREA_CODES = {"210", "214", "312", "512", "612", "713", "816", "832", "901"}


def get_recipient_timezone_offset(phone_number: str) -> int:
    """Returns approximate UTC hour offset for US E.164 phone numbers."""
    cleaned = phone_number.replace("+1", "").replace("+", "").replace("-", "").replace(" ", "")
    area_code = cleaned[:3] if len(cleaned) >= 3 else ""

    if area_code in _PACIFIC_AREA_CODES:
        return -8
    elif area_code in _MOUNTAIN_AREA_CODES:
        return -7
    elif area_code in _CENTRAL_AREA_CODES:
        return -6
    # Default Eastern / UTC-5 for US
    return -5


def is_within_tcpa_calling_window(phone_number: str, check_time: Optional[datetime] = None) -> bool:
    """
    TCPA mandates calls occur only between 8:00 AM and 9:00 PM in the recipient's local time.
    """
    now_utc = check_time or datetime.now(timezone.utc)
    offset_hours = get_recipient_timezone_offset(phone_number)
    local_hour = (now_utc.hour + offset_hours) % 24

    # 8 AM to 9 PM (8 <= hour < 21)
    return 8 <= local_hour < 21


async def initiate_outbound_call(
    lead_id: str,
    organization_id: str,
    db_session: AsyncSession,
    twilio_client=None,
    force_bypass_tcpa: bool = False,
) -> Dict[str, Any]:
    """
    Validates regulatory requirements and dispatches an outbound call via Twilio.
    """
    # 1. Fetch Lead
    lead_stmt = select(Lead).where(Lead.id == lead_id, Lead.organization_id == organization_id)
    lead = (await db_session.execute(lead_stmt)).scalar_one_or_none()
    if not lead or not lead.phone_number:
        raise ValueError(f"Lead {lead_id} not found or has no phone number.")

    # 2. Check DNC (Do-Not-Call) Opt-Out
    if lead.status in ("do_not_contact", "do_not_call"):
        raise PermissionError(
            f"Lead {lead.phone_number} is on the Do-Not-Call (DNC) list. Outbound dialing blocked."
        )

    # 3. Check TCPA Calling Hours
    if not force_bypass_tcpa and not is_within_tcpa_calling_window(lead.phone_number):
        raise PermissionError(
            f"Current time is outside federal TCPA calling hours (8:00 AM - 9:00 PM) for recipient timezone."
        )

    # 4. Fetch Organization Twilio Phone Number
    org_stmt = select(Organization).where(Organization.id == organization_id)
    org = (await db_session.execute(org_stmt)).scalar_one_or_none()
    from_number = org.twilio_phone_number if org and org.twilio_phone_number else settings.TWILIO_DEFAULT_PHONE_NUMBER

    call_id = str(uuid.uuid4())
    mock_sid = f"CAoutbound_{uuid.uuid4().hex[:24]}"

    # 5. Build TwiML with Media Stream connection
    twiml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{settings.TWILIO_MEDIA_STREAM_WS_URL}">
            <Parameter name="organization_id" value="{organization_id}" />
            <Parameter name="call_id" value="{call_id}" />
            <Parameter name="direction" value="outbound" />
            <Parameter name="lead_id" value="{lead.id}" />
        </Stream>
    </Connect>
</Response>"""

    # 6. Dispatch via Twilio REST API or test mock
    sid = mock_sid
    if twilio_client:
        res = await twilio_client.calls.create(
            to=lead.phone_number,
            from_=from_number,
            twiml=twiml_payload,
        )
        sid = res.sid
    elif "placeholder" not in settings.TWILIO_ACCOUNT_SID.lower() and "placeholder" not in settings.TWILIO_AUTH_TOKEN.lower():
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls.json"
        data = {
            "To": lead.phone_number,
            "From": from_number,
            "Twiml": twiml_payload,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, data=data, auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
            if resp.status_code in (200, 201):
                sid = resp.json().get("sid", mock_sid)
            else:
                raise RuntimeError(f"Twilio Outbound Call Error {resp.status_code}: {resp.text}")

    # 7. Persist Call Record
    call = Call(
        id=call_id,
        organization_id=organization_id,
        lead_id=lead.id,
        direction="outbound",
        from_number=from_number,
        to_number=lead.phone_number,
        status="initiated",
        twilio_call_sid=sid,
        initiated_at=datetime.now(timezone.utc),
    )
    db_session.add(call)

    lead.status = "contacted"
    await db_session.commit()
    await db_session.refresh(call)

    logger.info("Outbound call %s initiated to %s (SID: %s)", call_id, lead.phone_number, sid)

    return {
        "call_id": call.id,
        "twilio_call_sid": call.twilio_call_sid,
        "direction": "outbound",
        "to_number": lead.phone_number,
        "from_number": from_number,
        "status": "initiated",
    }
