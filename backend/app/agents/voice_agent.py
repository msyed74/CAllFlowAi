import asyncio
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from backend.app.agents.openai_client import OpenAIRealtimeClient
from backend.app.agents.transcription_logger import CallTranscriptionLogger
from backend.app.agents.tool_dispatcher import ToolDispatcher, TOOL_DEFINITIONS
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.agent_runtime import AgentSession
from backend.app.models.calls import Call
from backend.app.models.leads import Lead
from backend.app.models.organizations import Organization
from backend.app.telephony.live_dashboard_ws import dashboard_manager
from backend.app.telephony.media_stream import TwilioMediaSession

logger = logging.getLogger("agents.voice_agent")


class VoiceAgentSession:
    """
    Coordinates real-time multimodal voice conversation between Twilio Media Streams
    and OpenAI Realtime API. Handles audio streaming, server-side VAD, barge-in,
    and transcription logging.
    """

    def __init__(
        self,
        twilio_session: TwilioMediaSession,
        openai_client: Optional[OpenAIRealtimeClient] = None,
        session_maker=None,
        qdrant_client=None,
        redis_client=None,
    ):
        self.twilio_session = twilio_session
        self.session_maker = session_maker or AsyncSessionLocal
        self.openai_client = openai_client or OpenAIRealtimeClient(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_REALTIME_MODEL,
        )
        self.qdrant_client = qdrant_client
        self.redis_client = redis_client

        self.call_id = twilio_session.call_id
        self.organization_id = twilio_session.organization_id
        self.lead_id: Optional[str] = None
        self.agent_session_id: Optional[str] = None
        self.transcription_logger: Optional[CallTranscriptionLogger] = None
        self.tool_dispatcher: Optional[ToolDispatcher] = None
        self.system_prompt: str = ""
        self.voice_persona: str = settings.OPENAI_DEFAULT_VOICE
        self.tools: List[Dict[str, Any]] = TOOL_DEFINITIONS
        self.is_active: bool = False

    async def initialize(self) -> None:
        """Loads tenant and lead context, creates agent session, and connects bridges."""
        if not self.call_id:
            logger.warning("VoiceAgentSession started without call_id.")
            return

        # 1. Initialize transcription logger
        self.transcription_logger = CallTranscriptionLogger(
            call_id=self.call_id,
            session_maker=self.session_maker,
        )

        # 2. Fetch Organization and Lead context
        org_name = "CallFlow AI"
        lead_name = "there"
        async with self.session_maker() as db:
            stmt = select(Call).where(Call.id == self.call_id)
            call = (await db.execute(stmt)).scalar_one_or_none()

            if call:
                org_stmt = select(Organization).where(Organization.id == call.organization_id)
                org = (await db.execute(org_stmt)).scalar_one_or_none()
                if org:
                    org_name = org.name
                    self.voice_persona = org.default_voice_id or settings.OPENAI_DEFAULT_VOICE

                if call.lead_id:
                    self.lead_id = call.lead_id
                    lead_stmt = select(Lead).where(Lead.id == call.lead_id)
                    lead = (await db.execute(lead_stmt)).scalar_one_or_none()
                    if lead and lead.first_name:
                        lead_name = lead.first_name

        # 3. Construct Contextual System Prompt with Mandatory AI Disclosure
        self.system_prompt = f"""You are Alex, a professional sales representative calling on behalf of {org_name}.
You are speaking live on a phone call with {lead_name}.

MANDATORY FIRST STATEMENT:
In your very first sentence, you MUST state clearly:
"Hello, this is an automated AI assistant calling on behalf of {org_name}. Am I speaking with {lead_name}?"

CORE CONVERSATIONAL PRINCIPLES:
1. Spoken Brevity: You are on a phone call. Keep every response under 2 sentences unless specifically asked for details. Never use markdown, bullet points, or lists.
2. Natural Cadence: Speak with warm, professional energy, and active listening cues ("Understood", "Certainly").
3. Grounding: Do not invent pricing or facts. Use search_knowledge_base to answer product questions.
4. Opt-Out / Compliance: If the caller says "stop calling" or asks to be removed, immediately apologize, confirm their number will be removed, and politely conclude the call."""

        # 4. Save AgentSession in database
        try:
            async with self.session_maker() as db:
                agent_session_rec = AgentSession(
                    call_id=self.call_id,
                    system_prompt_snapshot=self.system_prompt,
                    voice_persona=self.voice_persona,
                    active_tools=self.tools,
                    temperature=0.7,
                )
                db.add(agent_session_rec)
                await db.commit()
                await db.refresh(agent_session_rec)
                self.agent_session_id = agent_session_rec.id
        except Exception as e:
            logger.error(f"Failed to record AgentSession: {e}")

        # 4b. Initialize ToolDispatcher with context from this session
        self.tool_dispatcher = ToolDispatcher(
            org_id=self.organization_id,
            call_id=self.call_id,
            qdrant_client=self.qdrant_client,
            embed_fn=None,  # Uses embed_texts default (real API) unless overridden
            redis_client=self.redis_client,
            agent_session_id=self.agent_session_id,
        )

        # 5. Connect to OpenAI Realtime API
        await self.openai_client.connect()

        # 6. Configure Session
        await self.openai_client.update_session(
            instructions=self.system_prompt,
            voice=self.voice_persona,
            tools=self.tools,
            temperature=0.7,
        )

        # 7. Wire Up Event Callbacks
        self._wire_callbacks()
        self.is_active = True

        # 7b. Register Supervisor Whisper & Takeover Handlers
        async def on_whisper(coaching_text: str):
            if self.is_active and self.openai_client.is_connected:
                logger.info("Supervisor whisper received for Call %s: %s", self.call_id, coaching_text)
                await self.openai_client.send_event({
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [{
                            "type": "input_text",
                            "text": f"[SUPERVISOR COACHING INSTRUCTION - Follow this advice immediately]: {coaching_text}",
                        }],
                    },
                })
                await self.openai_client.create_response()

        async def on_takeover(reason: str):
            if self.is_active and self.tool_dispatcher:
                logger.info("Supervisor takeover triggered for Call %s: %s", self.call_id, reason)
                async with self.session_maker() as db:
                    await self.tool_dispatcher.execute(
                        tool_name="transfer_call_to_human",
                        tool_call_id=f"takeover_{self.call_id}",
                        args={"escalation_reason": reason, "urgency_level": "critical"},
                        db_session=db,
                        lead_id=self.lead_id,
                    )

        dashboard_manager.register_whisper_handler(self.call_id, on_whisper)
        dashboard_manager.register_takeover_handler(self.call_id, on_takeover)

        # Broadcast call.started to live dashboard
        await dashboard_manager.broadcast_to_org(self.organization_id, {
            "type": "call.started",
            "call_id": self.call_id,
            "lead_id": self.lead_id,
            "voice_persona": self.voice_persona,
        })

        # 8. Trigger Initial Greeting
        await self.openai_client.create_response()
        logger.info(f"Voice Agent initialized successfully for Call {self.call_id}")

    def _wire_callbacks(self) -> None:
        """Hooks up the bi-directional audio and event routing."""

        # Twilio Inbound Audio -> OpenAI
        async def on_twilio_audio(pcm16_chunk: bytes):
            if self.is_active and self.openai_client.is_connected:
                await self.openai_client.append_input_audio(pcm16_chunk)

        self.twilio_session.on_pcm16_audio_received = on_twilio_audio

        # OpenAI Outbound Audio -> Twilio Handset
        async def on_openai_audio(pcm16_chunk: bytes):
            if self.is_active and self.twilio_session.is_active:
                await self.twilio_session.send_audio_pcm24k(pcm16_chunk)

        self.openai_client.on_audio_delta = on_openai_audio

        # Server-Side VAD User Speech Started (Barge-in / Interruption)
        async def on_barge_in():
            if self.is_active:
                logger.debug("Barge-in: Purging Twilio audio and cancelling OpenAI response")
                # 1. Purge Twilio handset buffer immediately
                await self.twilio_session.send_clear()
                # 2. Cancel in-flight model response
                await self.openai_client.cancel_response()
                # 3. Flag transcript
                if self.transcription_logger:
                    self.transcription_logger.mark_last_assistant_turn_interrupted()

        self.openai_client.on_speech_started = on_barge_in

        # Transcription Logging & Live Dashboard Broadcast
        async def on_transcript_completed(role: str, text: str, start_ms: int, end_ms: int):
            if self.transcription_logger:
                await self.transcription_logger.log_utterance(
                    speaker_role=role,
                    content=text,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms,
                )
            # Broadcast real-time transcript turn to supervisor dashboard
            await dashboard_manager.broadcast_to_org(self.organization_id, {
                "type": "transcript.turn",
                "call_id": self.call_id,
                "speaker_role": role,
                "content": text,
                "start_time_ms": start_ms,
                "end_time_ms": end_ms,
            })

        self.openai_client.on_transcript_completed = on_transcript_completed

        # Tool Call Routing: OpenAI → ToolDispatcher → send_tool_result
        async def on_tool_call(tool_name: str, tool_call_id: str, args: Dict[str, Any]):
            if not self.is_active or not self.tool_dispatcher:
                return
            logger.info("Tool call requested: %s (id=%s)", tool_name, tool_call_id)
            try:
                async with self.session_maker() as db:
                    result_json = await self.tool_dispatcher.execute(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        args=args,
                        db_session=db,
                        lead_id=self.lead_id,
                    )
                await self.openai_client.send_tool_result(tool_call_id, result_json)
                logger.debug("Tool result sent for %s", tool_name)
            except Exception as e:
                logger.error("Tool call handler failed for '%s': %s", tool_name, e)
                # Send error payload so LLM can recover gracefully
                import json
                await self.openai_client.send_tool_result(
                    tool_call_id,
                    json.dumps({"error": f"Tool execution failed: {str(e)}"}),
                )

        self.openai_client.on_tool_call = on_tool_call

    async def close(self) -> None:
        """Gracefully disconnects voice agent session."""
        self.is_active = False
        dashboard_manager.unregister_whisper_handler(self.call_id)
        dashboard_manager.unregister_takeover_handler(self.call_id)
        await dashboard_manager.broadcast_to_org(self.organization_id, {
            "type": "call.ended",
            "call_id": self.call_id,
        })
        if self.openai_client.is_connected:
            await self.openai_client.disconnect()
        logger.info(f"Voice Agent closed for Call {self.call_id}")
