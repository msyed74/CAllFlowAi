"""
Tool Dispatcher — central routing layer between the LLM and callable tools.

When OpenAI Realtime API fires `response.function_call_arguments.done`,
the VoiceAgentSession delegates to ToolDispatcher.execute().  The dispatcher:
  1. Routes the call to the correct tool function.
  2. Measures wall-clock execution time.
  3. Persists an AgentToolCall audit record.
  4. Returns a JSON string for send_tool_result().

TOOL_DEFINITIONS is the JSON schema list injected into `session.update` so
the LLM knows which tools are available and what arguments to pass.

Security:
  - Tool names are validated against an explicit allowlist.
  - All DB writes go through the injected session (never create new sessions here).
  - Exceptions are caught and returned as structured error payloads.
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.tools.crm import update_crm_lead
from backend.app.agents.tools.communication import send_followup_message
from backend.app.agents.tools.escalation import transfer_call_to_human
from backend.app.agents.tools.scheduling import (
    book_appointment_slot,
    check_calendar_availability,
)
from backend.app.models.agent_runtime import AgentToolCall

logger = logging.getLogger("agents.tool_dispatcher")

# ---------------------------------------------------------------------------
# OpenAI function-calling JSON schemas (injected into session.update)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_knowledge_base",
        "description": (
            "Search the company's knowledge base to answer product, pricing, "
            "policy, or frequently-asked questions. Use this before saying 'I don't know'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language question to look up.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional document category filter (e.g. 'pricing', 'faq').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "check_calendar_availability",
        "description": (
            "Retrieve available appointment slots for a given date. "
            "Call this before offering time options to the caller."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "preferred_date": {
                    "type": "string",
                    "description": "Target date in YYYY-MM-DD format.",
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone string, e.g. 'America/New_York'.",
                },
            },
            "required": ["preferred_date"],
        },
    },
    {
        "type": "function",
        "name": "book_appointment_slot",
        "description": (
            "Book an appointment after the caller has confirmed a specific time slot."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_time_iso": {
                    "type": "string",
                    "description": "ISO-8601 datetime string for the appointment start.",
                },
                "meeting_topic": {
                    "type": "string",
                    "description": "Short description of the meeting purpose.",
                },
            },
            "required": ["start_time_iso", "meeting_topic"],
        },
    },
    {
        "type": "function",
        "name": "update_crm_lead",
        "description": (
            "Update the CRM record for the lead with qualification data gathered "
            "during the conversation. Call after confirming key facts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lead_stage": {
                    "type": "string",
                    "description": (
                        "Qualification stage: awareness | interest | consideration | "
                        "intent | evaluation | purchase"
                    ),
                },
                "updated_fields": {
                    "type": "object",
                    "description": "Key-value pairs of lead data to persist (e.g. budget, company_size).",
                },
                "lead_score": {
                    "type": "integer",
                    "description": "Lead quality score 0-100.",
                },
            },
            "required": ["lead_stage", "updated_fields"],
        },
    },
    {
        "type": "function",
        "name": "transfer_call_to_human",
        "description": (
            "Transfer the call to a human agent. Use when: the caller explicitly requests "
            "a human, the topic is outside your scope, or an escalation is required."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "escalation_reason": {
                    "type": "string",
                    "description": "Brief reason for the transfer.",
                },
                "urgency_level": {
                    "type": "string",
                    "description": "One of: low | medium | high | critical",
                },
                "context_summary": {
                    "type": "string",
                    "description": "Short conversation summary for the receiving agent.",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "send_followup_message",
        "description": (
            "Send an immediate SMS or Email to the prospect with calendar details, "
            "product overview brochure, or representative contact card."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": ["sms", "email"],
                    "description": "Communication channel to use.",
                },
                "message_type": {
                    "type": "string",
                    "enum": ["appointment_confirmation", "product_brochure", "rep_contact_card"],
                    "description": "Type of collateral or confirmation message.",
                },
                "custom_note": {
                    "type": "string",
                    "description": "Optional custom note included with the message.",
                },
            },
            "required": ["channel", "message_type"],
        },
    },
]

# Allowlist — only these tool names can be dispatched
_ALLOWED_TOOLS = {t["name"] for t in TOOL_DEFINITIONS}


class ToolDispatcher:
    """
    Routes LLM tool-call requests to the correct async tool function,
    measures execution time, and persists audit records.
    """

    def __init__(
        self,
        org_id: str,
        call_id: str,
        qdrant_client=None,
        embed_fn=None,
        redis_client=None,
        agent_session_id: Optional[str] = None,
    ):
        self.org_id = org_id
        self.call_id = call_id
        self.qdrant_client = qdrant_client
        self.embed_fn = embed_fn
        self.redis_client = redis_client
        self.agent_session_id = agent_session_id

    async def execute(
        self,
        tool_name: str,
        tool_call_id: str,
        args: Dict[str, Any],
        db_session: AsyncSession,
        lead_id: Optional[str] = None,
    ) -> str:
        """
        Dispatch a tool call and return a JSON string result.

        Args:
            tool_name: Name of the tool to invoke.
            tool_call_id: OpenAI call_id for correlation.
            args: Parsed argument dict from the LLM.
            db_session: Active async DB session for tools that need DB access.
            lead_id: Active lead UUID (for booking and CRM tools).

        Returns:
            JSON string — passed directly to openai_client.send_tool_result().
        """
        if tool_name not in _ALLOWED_TOOLS:
            logger.warning("Rejected unknown tool call: '%s'", tool_name)
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        start_time = time.monotonic()
        result: Dict[str, Any] = {}
        error_msg: Optional[str] = None

        try:
            result = await self._dispatch(tool_name, args, db_session, lead_id)
        except Exception as e:
            logger.error("Tool '%s' raised an exception: %s", tool_name, e, exc_info=True)
            error_msg = str(e)
            result = {"error": f"Tool execution failed: {error_msg}"}

        execution_ms = int((time.monotonic() - start_time) * 1000)

        # Persist audit record (best-effort – never fail the tool call because of audit)
        if self.agent_session_id:
            try:
                record = AgentToolCall(
                    id=str(uuid.uuid4()),
                    agent_session_id=self.agent_session_id,
                    call_id=self.call_id,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    arguments=args,
                    response=result,
                    execution_time_ms=execution_ms,
                    is_successful=error_msg is None,
                    error_message=error_msg,
                )
                db_session.add(record)
                await db_session.commit()
            except Exception as audit_exc:
                logger.warning("Failed to persist AgentToolCall audit record: %s", audit_exc)
        else:
            logger.debug("Skipping AgentToolCall audit record: no agent_session_id available.")

        logger.info(
            "Tool '%s' executed in %dms — status=%s",
            tool_name,
            execution_ms,
            "error" if error_msg else "success",
        )

        return json.dumps(result)

    async def _dispatch(
        self,
        tool_name: str,
        args: Dict[str, Any],
        db_session: AsyncSession,
        lead_id: Optional[str],
    ) -> Dict[str, Any]:
        """Internal routing table."""

        if tool_name == "search_knowledge_base":
            from backend.app.agents.tools.knowledge import search_knowledge_base
            return await search_knowledge_base(
                query=args.get("query", ""),
                organization_id=self.org_id,
                qdrant_client=self.qdrant_client,
                embed_fn=self.embed_fn,
                category=args.get("category"),
            )

        elif tool_name == "check_calendar_availability":
            return await check_calendar_availability(
                preferred_date=args.get("preferred_date", ""),
                timezone_str=args.get("timezone", "UTC"),
                db_session=db_session,
                org_id=self.org_id,
            )

        elif tool_name == "book_appointment_slot":
            if not lead_id:
                return {"booked": False, "reason": "No lead_id available for this call."}
            return await book_appointment_slot(
                start_time_iso=args.get("start_time_iso", ""),
                lead_id=lead_id,
                call_id=self.call_id,
                org_id=self.org_id,
                meeting_topic=args.get("meeting_topic", "Appointment"),
                db_session=db_session,
                redis_client=self.redis_client,
            )

        elif tool_name == "update_crm_lead":
            if not lead_id:
                return {"updated": False, "reason": "No lead_id available for this call."}
            return await update_crm_lead(
                lead_id=lead_id,
                lead_stage=args.get("lead_stage", "interest"),
                updated_fields=args.get("updated_fields", {}),
                db_session=db_session,
                lead_score=args.get("lead_score"),
            )

        elif tool_name == "transfer_call_to_human":
            # Synchronous — no await needed
            return transfer_call_to_human(
                call_sid=self.call_id,
                escalation_reason=args.get("escalation_reason", "Caller requested human"),
                urgency_level=args.get("urgency_level", "medium"),
                context_summary=args.get("context_summary", ""),
            )

        elif tool_name == "send_followup_message":
            return await send_followup_message(
                channel=args.get("channel", "sms"),
                message_type=args.get("message_type", "appointment_confirmation"),
                call_id=self.call_id,
                org_id=self.org_id,
                lead_id=lead_id,
                db_session=db_session,
                custom_note=args.get("custom_note"),
            )

        else:
            return {"error": f"No handler registered for tool '{tool_name}'"}
