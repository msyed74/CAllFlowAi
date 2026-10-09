import asyncio
from contextlib import asynccontextmanager
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.openai_client import OpenAIRealtimeClient
from backend.app.agents.voice_agent import VoiceAgentSession
from backend.app.models.agent_runtime import AgentSession
from backend.app.models.calls import Call, CallTranscript
from backend.app.models.leads import Lead
from backend.app.models.organizations import Organization
from backend.app.telephony.media_stream import TwilioMediaSession


class MockOpenAIClient(OpenAIRealtimeClient):
    """Subclass of OpenAIRealtimeClient that simulates server events in memory."""
    def __init__(self):
        super().__init__(api_key="sk-test-mock")
        self.sent_events = []
        self.connected = False

    async def connect(self):
        self.connected = True
        self.is_connected = True

    async def disconnect(self):
        self.connected = False
        self.is_connected = False

    async def send_event(self, event):
        self.sent_events.append(event)


class MockTwilioSession:
    """Mock TwilioMediaSession tracking audio and clear events."""
    def __init__(self, call_id: str, organization_id: str):
        self.call_id = call_id
        self.organization_id = organization_id
        self.is_active = True
        self.sent_pcm_audio = []
        self.clear_count = 0
        self.on_pcm16_audio_received = None

    async def send_audio_pcm24k(self, pcm16_audio: bytes):
        self.sent_pcm_audio.append(pcm16_audio)

    async def send_clear(self):
        self.clear_count += 1


@pytest.mark.asyncio
async def test_voice_agent_session_orchestration(db_session: AsyncSession):
    # 1. Seed Organization, Lead, and Call
    org = Organization(
        name="Apex Solutions",
        slug="apex-solutions",
        default_voice_id="shimmer",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()

    lead = Lead(
        organization_id=org.id,
        first_name="Jordan",
        last_name="Belfort",
        phone_number="+14155553344",
        status="new",
    )
    db_session.add(lead)
    await db_session.flush()

    call = Call(
        organization_id=org.id,
        lead_id=lead.id,
        twilio_call_sid="CA_agent_orchestration_001",
        direction="outbound",
        from_number="+18005550199",
        to_number="+14155553344",
        status="in_progress",
    )
    db_session.add(call)
    await db_session.commit()

    # 2. Setup Agent Session with mocked bridges
    twilio_mock = MockTwilioSession(call_id=call.id, organization_id=org.id)
    openai_mock = MockOpenAIClient()

    @asynccontextmanager
    async def session_maker():
        yield db_session

    agent_session = VoiceAgentSession(
        twilio_session=twilio_mock,
        openai_client=openai_mock,
        session_maker=session_maker,
    )

    # 3. Initialize Agent
    await agent_session.initialize()
    assert agent_session.is_active is True
    assert openai_mock.is_connected is True

    # Check Legal AI Disclosure Prompt
    assert "automated AI assistant calling on behalf of Apex Solutions" in agent_session.system_prompt
    assert "Jordan" in agent_session.system_prompt

    # Check AgentSession database record
    stmt = select(AgentSession).where(AgentSession.call_id == call.id)
    db_agent_session = (await db_session.execute(stmt)).scalar_one()
    assert db_agent_session.voice_persona == "shimmer"
    assert "Jordan" in db_agent_session.system_prompt_snapshot

    # 4. Test Inbound Audio Routing: Twilio -> OpenAI
    test_pcm = b"simulated_24k_audio_from_twilio"
    await twilio_mock.on_pcm16_audio_received(test_pcm)
    assert any(e.get("type") == "input_audio_buffer.append" for e in openai_mock.sent_events)

    # 5. Test Outbound Audio Routing: OpenAI -> Twilio
    ai_pcm = b"simulated_24k_speech_from_openai"
    await openai_mock.on_audio_delta(ai_pcm)
    assert len(twilio_mock.sent_pcm_audio) == 1
    assert twilio_mock.sent_pcm_audio[0] == ai_pcm

    # 6. Test Assistant Utterance Logging
    await openai_mock.on_transcript_completed("assistant", "Hello, I am Alex from Apex.", 0, 1500)
    assert len(agent_session.transcription_logger.entries) == 1

    # 7. Test User Barge-in / Speech Started
    await openai_mock.on_speech_started()
    # Verify Twilio buffer cleared
    assert twilio_mock.clear_count == 1
    # Verify OpenAI model cancellation requested
    assert any(e.get("type") == "response.cancel" for e in openai_mock.sent_events)
    # Verify assistant turn marked as interrupted
    assert agent_session.transcription_logger.entries[0].is_interrupted is True

    # 8. Test User Utterance Logging
    await openai_mock.on_transcript_completed("user", "Wait, how much does it cost?", 1600, 3000)
    assert len(agent_session.transcription_logger.entries) == 2

    # Check formatted transcript
    full_transcript = agent_session.transcription_logger.get_full_formatted_transcript()
    assert "Assistant: Hello, I am Alex from Apex. [Interrupted]" in full_transcript
    assert "User: Wait, how much does it cost?" in full_transcript

    # Check DB persistence in call_transcripts table
    t_stmt = select(CallTranscript).where(CallTranscript.call_id == call.id)
    db_transcripts = (await db_session.execute(t_stmt)).scalars().all()
    assert len(db_transcripts) >= 2

    # 9. Teardown
    await agent_session.close()
    assert agent_session.is_active is False
    assert openai_mock.is_connected is False
