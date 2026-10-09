"""
CRM update tool for the AI Voice Agent.

Called by the ToolDispatcher when the LLM invokes `update_crm_lead`.
Updates the Lead record's qualification stage, status, lead score, and
arbitrary custom_fields extracted during the conversation.

Design decision: custom_fields is stored as JSONB on the Lead model.
We merge (not replace) the incoming dict to preserve any pre-existing fields
that weren't touched during this call.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.leads import Lead

logger = logging.getLogger("agents.tools.crm")

# Recognised lead status values (enforced to prevent garbage data)
VALID_STATUSES = {
    "new",
    "contacted",
    "qualified",
    "unqualified",
    "negotiation",
    "won",
    "lost",
    "do_not_contact",
}

# Recognised qualification stages
VALID_STAGES = {
    "awareness",
    "interest",
    "consideration",
    "intent",
    "evaluation",
    "purchase",
}


async def update_crm_lead(
    lead_id: str,
    lead_stage: str,
    updated_fields: Dict[str, Any],
    db_session: AsyncSession,
    lead_score: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Update a Lead record with qualification data collected during the call.

    Args:
        lead_id: Lead UUID.
        lead_stage: New qualification stage (maps to Lead.status).
        updated_fields: Dict of key/value pairs to merge into Lead.custom_fields.
        db_session: Active async DB session.
        lead_score: Optional 0-100 score override.

    Returns:
        Dict with `updated: True` and summary of changes, or
        `updated: False` with `reason` on failure.
    """
    if not lead_id:
        return {"updated": False, "reason": "lead_id is required."}

    # Normalise and validate stage
    normalised_stage = lead_stage.lower().strip() if lead_stage else ""
    if normalised_stage not in VALID_STAGES:
        logger.warning(
            "Unknown lead stage '%s' for lead %s – falling back to 'interest'",
            lead_stage,
            lead_id,
        )
        normalised_stage = "interest"

    # Map stage to a status value
    stage_to_status = {
        "awareness": "contacted",
        "interest": "contacted",
        "consideration": "qualified",
        "intent": "qualified",
        "evaluation": "negotiation",
        "purchase": "won",
    }
    new_status = stage_to_status.get(normalised_stage, "contacted")

    try:
        stmt = select(Lead).where(Lead.id == lead_id)
        result = await db_session.execute(stmt)
        lead = result.scalar_one_or_none()

        if not lead:
            return {"updated": False, "reason": f"Lead {lead_id} not found."}

        # Merge custom_fields (preserve existing keys not in updated_fields)
        existing_custom = lead.custom_fields or {}
        merged_custom = {**existing_custom, **updated_fields}

        lead.status = new_status
        lead.custom_fields = merged_custom

        if lead_score is not None:
            clamped_score = max(0, min(100, int(lead_score)))
            # Lead score is tracked separately in lead_scores table (Phase 4)
            # Store it in custom_fields for now as a convenience snapshot
            merged_custom["_latest_lead_score"] = clamped_score
            lead.custom_fields = merged_custom

        await db_session.commit()
        await db_session.refresh(lead)

        logger.info(
            "Lead %s updated: stage=%s, status=%s, fields=%s",
            lead_id,
            normalised_stage,
            new_status,
            list(updated_fields.keys()),
        )

        return {
            "updated": True,
            "lead_id": lead_id,
            "new_status": new_status,
            "qualification_stage": normalised_stage,
            "updated_field_keys": list(updated_fields.keys()),
            "lead_score": lead_score,
        }

    except Exception as e:
        logger.error("Failed to update CRM lead %s: %s", lead_id, e)
        await db_session.rollback()
        return {
            "updated": False,
            "reason": f"Database error while updating lead: {str(e)}",
        }
