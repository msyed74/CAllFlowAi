"""
Scheduling tools for the AI Voice Agent.

Two tools are exposed to the LLM:
  - check_calendar_availability   → returns open time windows
  - book_appointment_slot         → creates Appointment record with Redis lock

Redis distributed lock prevents double-booking the same slot when concurrent
calls race to confirm the same time.  Lock TTL is 30 seconds.

Lock key format:  callflow:slot:{org_id}:{iso_datetime_utc}
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.appointments import Appointment
from backend.app.core.config import settings

logger = logging.getLogger("agents.tools.scheduling")

# Slot lock TTL in seconds – long enough to cover the booking transaction
SLOT_LOCK_TTL = 30

# Business hours window (UTC-based simplified; extend per org timezone in prod)
BUSINESS_HOUR_START = 9   # 09:00
BUSINESS_HOUR_END = 17    # 17:00
AVAILABLE_SLOT_DURATION_MINUTES = 30


async def check_calendar_availability(
    preferred_date: str,
    timezone_str: str = "UTC",
    db_session: Optional[AsyncSession] = None,
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return a list of available appointment time slots for the given date.

    In production this will integrate with Google Calendar / Calendly APIs.
    For now it generates slots based on business hours and checks the
    Appointment table for conflicts.

    Args:
        preferred_date: ISO-8601 date string (YYYY-MM-DD).
        timezone_str: IANA timezone string (e.g. "America/New_York").
        db_session: Active DB session for conflict checking.
        org_id: Organization UUID for tenant-scoped conflict check.

    Returns:
        Dict with `available_slots` list (ISO-8601 datetime strings) and
        `date` confirming the queried date.
    """
    try:
        target_date = datetime.strptime(preferred_date, "%Y-%m-%d").date()
    except ValueError:
        return {
            "error": f"Invalid date format '{preferred_date}'. Use YYYY-MM-DD.",
            "available_slots": [],
        }

    # Generate candidate slots within business hours
    candidate_slots = []
    for hour in range(BUSINESS_HOUR_START, BUSINESS_HOUR_END):
        for minute in [0, AVAILABLE_SLOT_DURATION_MINUTES]:
            slot_dt = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                hour,
                minute,
                tzinfo=timezone.utc,
            )
            candidate_slots.append(slot_dt)

    # Skip past slots
    now_utc = datetime.now(tz=timezone.utc)
    candidate_slots = [s for s in candidate_slots if s > now_utc]

    if not candidate_slots:
        return {
            "date": preferred_date,
            "available_slots": [],
            "message": "No future time slots available on the requested date.",
        }

    # Remove already-booked slots from DB
    booked_iso: set = set()
    if db_session and org_id:
        try:
            stmt = select(Appointment).where(
                Appointment.organization_id == org_id,
                Appointment.status == "confirmed",
            )
            result = await db_session.execute(stmt)
            existing = result.scalars().all()
            for appt in existing:
                if appt.start_time:
                    booked_iso.add(appt.start_time.isoformat())
        except Exception as e:
            logger.warning("Could not check existing appointments: %s", e)

    available = [
        s.isoformat()
        for s in candidate_slots
        if s.isoformat() not in booked_iso
    ]

    return {
        "date": preferred_date,
        "timezone": timezone_str,
        "available_slots": available[:8],  # Cap at 8 slots for voice readability
        "slot_duration_minutes": AVAILABLE_SLOT_DURATION_MINUTES,
    }


async def book_appointment_slot(
    start_time_iso: str,
    lead_id: str,
    call_id: str,
    org_id: str,
    meeting_topic: str,
    db_session: AsyncSession,
    redis_client=None,
) -> Dict[str, Any]:
    """
    Book a specific appointment slot with a distributed Redis lock to prevent
    concurrent double-booking.

    Args:
        start_time_iso: ISO-8601 datetime string for the appointment start.
        lead_id: Lead UUID to associate the appointment with.
        call_id: Call UUID for traceability.
        org_id: Organization UUID for multi-tenant scoping.
        meeting_topic: Description of the meeting purpose.
        db_session: Active async DB session.
        redis_client: Optional redis.asyncio client (skips lock in tests when None).

    Returns:
        Dict with `booked: True` and appointment details, or
        `booked: False` with `reason` when the slot is taken.
    """
    try:
        parsed_dt = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
    except ValueError:
        return {
            "booked": False,
            "reason": f"Invalid datetime format '{start_time_iso}'. Use ISO-8601.",
        }

    lock_key = f"callflow:slot:{org_id}:{parsed_dt.isoformat()}"
    appointment_id = str(uuid.uuid4())

    # Acquire distributed lock to prevent race conditions
    if redis_client is not None:
        acquired = await redis_client.set(
            lock_key,
            appointment_id,
            nx=True,  # Only set if not exists
            ex=SLOT_LOCK_TTL,
        )
        if not acquired:
            logger.warning("Slot %s already being booked (lock held)", lock_key)
            return {
                "booked": False,
                "reason": (
                    "That time slot is currently being confirmed by another booking. "
                    "Please choose a different time."
                ),
            }

    # Check for existing appointment in DB
    try:
        stmt = select(Appointment).where(
            Appointment.organization_id == org_id,
            Appointment.start_time == parsed_dt,
            Appointment.status == "confirmed",
        )
        result = await db_session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return {
                "booked": False,
                "reason": "That time slot is already booked.",
            }
    except Exception as e:
        logger.error("DB conflict check failed for slot booking: %s", e)

    # Create Appointment record
    try:
        end_dt = parsed_dt + timedelta(minutes=AVAILABLE_SLOT_DURATION_MINUTES)

        appointment = Appointment(
            id=appointment_id,
            organization_id=org_id,
            lead_id=lead_id,
            call_id=call_id,
            meeting_title=meeting_topic,
            start_time=parsed_dt,
            end_time=end_dt,
            timezone="UTC",
            status="confirmed",
            meeting_url=None,
            notes=f"Booked by AI Voice Agent during call {call_id}",
        )
        db_session.add(appointment)
        await db_session.commit()
        await db_session.refresh(appointment)

        logger.info(
            "Appointment booked: %s at %s for lead %s (org=%s)",
            appointment_id, start_time_iso, lead_id, org_id,
        )

        return {
            "booked": True,
            "appointment_id": appointment_id,
            "start_time": parsed_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "meeting_topic": meeting_topic,
            "confirmation": (
                f"Your appointment has been confirmed for "
                f"{parsed_dt.strftime('%A, %B %d at %I:%M %p UTC')}. "
                f"You will receive a confirmation shortly."
            ),
        }
    except Exception as e:
        logger.error("Failed to create appointment record: %s", e)
        await db_session.rollback()
        return {
            "booked": False,
            "reason": "An error occurred while saving your appointment. Please try again.",
        }
    finally:
        # Release the Redis lock after successful DB commit
        if redis_client is not None:
            try:
                stored_val = await redis_client.get(lock_key)
                if stored_val and stored_val.decode() == appointment_id:
                    await redis_client.delete(lock_key)
            except Exception as e:
                logger.warning("Failed to release Redis slot lock: %s", e)
