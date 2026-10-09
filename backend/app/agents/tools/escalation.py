"""
Human escalation / call transfer tool for the AI Voice Agent.

Called by the ToolDispatcher when the LLM invokes `transfer_call_to_human`.
Returns a structured TwiML payload that the telephony layer can use to
perform a warm transfer.

Note: Actual Twilio API call to redirect the live call is handled in Phase 6
(Call Control).  This tool prepares the payload and marks the intent; the
telephony layer watches for escalation events and acts on them.

Urgency levels:
  - "low"      → queue for next available agent
  - "medium"   → priority queue
  - "high"     → immediate supervisor page + priority queue
  - "critical" → emergency escalation (potential safety issue)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("agents.tools.escalation")

VALID_URGENCY_LEVELS = {"low", "medium", "high", "critical"}

# Default transfer number – overridden per org in Phase 6
DEFAULT_TRANSFER_NUMBER = "+18005550100"


def transfer_call_to_human(
    call_sid: str,
    escalation_reason: str,
    urgency_level: str = "medium",
    context_summary: str = "",
) -> Dict[str, Any]:
    """
    Prepare a human transfer payload for the telephony layer.

    This function is intentionally synchronous – it does not touch the
    database or make network calls.  The ToolDispatcher and VoiceAgentSession
    interpret the returned `action: "transfer_to_human"` and hand off to the
    telephony module.

    Args:
        call_sid: Twilio Call SID of the active call.
        escalation_reason: Human-readable reason for escalation.
        urgency_level: One of "low", "medium", "high", "critical".
        context_summary: Brief summary of conversation so far for the human agent.

    Returns:
        Dict with escalation instructions for the telephony layer.
    """
    normalised_urgency = urgency_level.lower().strip()
    if normalised_urgency not in VALID_URGENCY_LEVELS:
        logger.warning(
            "Unknown urgency level '%s' – defaulting to 'medium'", urgency_level
        )
        normalised_urgency = "medium"

    timestamp = datetime.now(tz=timezone.utc).isoformat()

    # TwiML template for warm transfer (Phase 6 will execute this)
    twiml_payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Say voice=\"Polly.Joanna\">"
        "Please hold while I transfer you to one of our team members."
        "</Say>"
        "<Dial timeout=\"30\" action=\"/telephony/transfer-fallback\">"
        f"<Number>{DEFAULT_TRANSFER_NUMBER}</Number>"
        "</Dial>"
        "</Response>"
    )

    result = {
        "action": "transfer_to_human",
        "call_sid": call_sid,
        "escalation_reason": escalation_reason,
        "urgency_level": normalised_urgency,
        "context_summary": context_summary,
        "twiml_payload": twiml_payload,
        "transfer_number": DEFAULT_TRANSFER_NUMBER,
        "timestamp": timestamp,
        "agent_message": (
            "I'm going to transfer you to one of our team members right now. "
            "Please stay on the line."
        ),
    }

    logger.info(
        "Escalation requested for call %s: reason='%s', urgency=%s",
        call_sid,
        escalation_reason,
        normalised_urgency,
    )

    return result
