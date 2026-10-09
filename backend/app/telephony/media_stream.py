import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.calls import Call, CallEvent
from backend.app.telephony.jitter_buffer import AudioJitterBuffer
from backend.app.telephony.transcoder import (
    mulaw_8k_to_pcm16_24k,
    pcm16_24k_to_mulaw_8k,
)

logger = logging.getLogger("telephony.media_stream")

ws_router = APIRouter(tags=["Telephony WebSocket"])


class TwilioMediaSession:
    """
    Manages an active bi-directional Twilio Media Stream WebSocket session.
    Transcodes audio in real time between Twilio (mu-law 8kHz) and AI (PCM16 24kHz).
    """

    def __init__(self, websocket: WebSocket, session_maker=None, enable_voice_agent: bool = True):
        self.websocket = websocket
        self.session_maker = session_maker or AsyncSessionLocal
        self.enable_voice_agent = enable_voice_agent
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.call_id: Optional[str] = None
        self.organization_id: Optional[str] = None
        self.is_active: bool = False
        self.agent_session: Optional[Any] = None

        # Inbound and outbound buffers
        self.inbound_buffer = AudioJitterBuffer(frame_size=160)  # 20ms mu-law
        self.outbound_buffer = AudioJitterBuffer(frame_size=160)

        # Callbacks for speech processing (e.g., OpenAI Realtime bridge)
        self.on_pcm16_audio_received: Optional[Callable[[bytes], asyncio.Future]] = None
        self.on_barge_in_detected: Optional[Callable[[], asyncio.Future]] = None

    async def handle_start(self, data: dict) -> None:
        """Processes the Twilio 'start' metadata event."""
        start_info = data.get("start", {})
        self.stream_sid = start_info.get("streamSid")
        self.call_sid = start_info.get("callSid")
        custom_params = start_info.get("customParameters", {})
        self.call_id = custom_params.get("call_id")
        self.organization_id = custom_params.get("organization_id")
        self.is_active = True

        logger.info(
            f"Twilio Media Stream started: streamSid={self.stream_sid}, "
            f"callSid={self.call_sid}, callId={self.call_id}"
        )

        # Update Call record to 'in_progress'
        if self.call_sid:
            async with self.session_maker() as db:
                stmt = select(Call).where(Call.twilio_call_sid == self.call_sid)
                call = (await db.execute(stmt)).scalar_one_or_none()
                if call:
                    call.status = "in_progress"
                    if not call.answered_at:
                        call.answered_at = datetime.now(timezone.utc)
                    
                    # Record media stream start event
                    event = CallEvent(
                        call_id=call.id,
                        event_type="media_stream_started",
                        payload={"stream_sid": self.stream_sid},
                        timestamp_ms=0,
                    )
                    db.add(event)
                    await db.commit()

        # Connect Voice Agent if active and credentials configured
        if self.enable_voice_agent and not settings.OPENAI_API_KEY.startswith("sk-placeholder"):
            from backend.app.agents.voice_agent import VoiceAgentSession
            self.agent_session = VoiceAgentSession(self, session_maker=self.session_maker)
            asyncio.create_task(self.agent_session.initialize())

    async def handle_media(self, data: dict) -> None:
        """Processes an incoming 20ms G.711 mu-law audio packet from Twilio."""
        media_info = data.get("media", {})
        payload_b64 = media_info.get("payload", "")
        if not payload_b64:
            return

        try:
            raw_mulaw = base64.b64decode(payload_b64)
            # Push into inbound buffer
            await self.inbound_buffer.push(raw_mulaw)

            # Pop ready frames and transcode to PCM16 24kHz for AI consumption
            frames = await self.inbound_buffer.pop_all_frames()
            for frame in frames:
                pcm16_24k = mulaw_8k_to_pcm16_24k(frame)
                if self.on_pcm16_audio_received:
                    await self.on_pcm16_audio_received(pcm16_24k)
        except Exception as e:
            logger.error(f"Error processing inbound audio frame: {e}")

    async def send_audio_pcm24k(self, pcm16_24k_audio: bytes) -> None:
        """
        Translates AI PCM16 24kHz audio to G.711 mu-law 8kHz, packetizes into
        20ms (160 bytes) chunks, and streams to Twilio handset.
        """
        if not self.is_active or not self.stream_sid:
            return

        # 1. Transcode 24kHz PCM16 -> 8kHz mu-law
        mulaw_audio = pcm16_24k_to_mulaw_8k(pcm16_24k_audio)
        await self.outbound_buffer.push(mulaw_audio)

        # 2. Pop complete 20ms frames (160 bytes each) and emit
        frames = await self.outbound_buffer.pop_all_frames()
        for frame in frames:
            payload_b64 = base64.b64encode(frame).decode("utf-8")
            media_msg = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {
                    "payload": payload_b64,
                },
            }
            await self.websocket.send_text(json.dumps(media_msg))

    async def send_clear(self) -> None:
        """
        Purges Twilio's audio playback buffer immediately upon barge-in / user interruption.
        """
        if not self.is_active or not self.stream_sid:
            return

        await self.outbound_buffer.clear()
        clear_msg = {
            "event": "clear",
            "streamSid": self.stream_sid,
        }
        await self.websocket.send_text(json.dumps(clear_msg))
        logger.debug(f"Emitted Twilio clear event on stream {self.stream_sid}")

    async def send_mark(self, mark_name: str) -> None:
        """Emits an audio mark to track when specific speech segments finish playing."""
        if not self.is_active or not self.stream_sid:
            return

        mark_msg = {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {
                "name": mark_name,
            },
        }
        await self.websocket.send_text(json.dumps(mark_msg))

    async def handle_stop(self, data: dict) -> None:
        """Handles Twilio 'stop' event when the phone call terminates."""
        self.is_active = False
        logger.info(f"Twilio Media Stream stopped: streamSid={self.stream_sid}")

        if self.agent_session:
            await self.agent_session.close()

        if self.call_sid:
            async with self.session_maker() as db:
                stmt = select(Call).where(Call.twilio_call_sid == self.call_sid)
                call = (await db.execute(stmt)).scalar_one_or_none()
                if call:
                    call.status = "completed"
                    call.ended_at = datetime.now(timezone.utc)
                    if call.answered_at:
                        duration = int((call.ended_at - call.answered_at).total_seconds())
                        call.duration_seconds = max(0, duration)
                        call.billed_seconds = max(0, duration)
                    await db.commit()


@ws_router.websocket("/ws/media-stream")
async def media_stream_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint receiving Twilio Bidirectional Media Streams.
    Handles 'connected', 'start', 'media', 'mark', 'clear', and 'stop' events.
    """
    await websocket.accept()
    session_maker = getattr(websocket.app.state, "db_session_maker", AsyncSessionLocal)
    enable_voice_agent = getattr(websocket.app.state, "enable_voice_agent", True)
    session = TwilioMediaSession(
        websocket,
        session_maker=session_maker,
        enable_voice_agent=enable_voice_agent,
    )

    try:
        while True:
            text_data = await websocket.receive_text()
            data = json.loads(text_data)
            event_type = data.get("event")

            if event_type == "connected":
                logger.info("Twilio Media Stream protocol handshake connected.")
            elif event_type == "start":
                await session.handle_start(data)
            elif event_type == "media":
                await session.handle_media(data)
            elif event_type == "mark":
                logger.debug(f"Twilio mark played: {data.get('mark', {}).get('name')}")
            elif event_type == "clear":
                logger.debug("Twilio stream buffer cleared.")
            elif event_type == "stop":
                await session.handle_stop(data)
                break
    except WebSocketDisconnect:
        logger.info(f"Twilio Media Stream disconnected: streamSid={session.stream_sid}")
    except Exception as e:
        logger.error(f"Error in media stream WebSocket: {e}")
    finally:
        session.is_active = False
