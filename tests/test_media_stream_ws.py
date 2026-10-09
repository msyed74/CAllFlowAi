import base64
import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.calls import Call, CallEvent
from backend.app.models.organizations import Organization
from backend.app.telephony.media_stream import TwilioMediaSession


class MockWebSocket:
    """Mock WebSocket simulating Twilio Media Stream connection."""
    def __init__(self):
        self.sent_messages = []
        self.is_closed = False

    async def accept(self):
        pass

    async def send_text(self, text: str):
        self.sent_messages.append(text)

    async def close(self):
        self.is_closed = True


@pytest.mark.asyncio
async def test_twilio_media_session_lifecycle(db_session: AsyncSession):
    # 1. Seed Organization and Call in DB
    org = Organization(
        name="Media Stream Test Org",
        slug="media-stream-test-org",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()

    call = Call(
        organization_id=org.id,
        twilio_call_sid="CA_stream_lifecycle_001",
        direction="inbound",
        from_number="+14155551122",
        to_number="+18005550100",
        status="ringing",
    )
    db_session.add(call)
    await db_session.commit()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_maker():
        yield db_session

    mock_ws = MockWebSocket()
    session = TwilioMediaSession(mock_ws, session_maker=session_maker)

    # 2. Test handle_start
    start_payload = {
        "event": "start",
        "sequenceNumber": "1",
        "start": {
            "streamSid": "MZ_stream_test_999",
            "accountSid": "AC_test_account",
            "callSid": "CA_stream_lifecycle_001",
            "tracks": ["inbound"],
            "customParameters": {
                "organization_id": org.id,
                "call_id": call.id,
            },
        },
    }
    await session.handle_start(start_payload)
    assert session.is_active is True
    assert session.stream_sid == "MZ_stream_test_999"

    # Check Call status updated to in_progress
    stmt = select(Call).where(Call.twilio_call_sid == "CA_stream_lifecycle_001")
    call_in_progress = (await db_session.execute(stmt)).scalar_one()
    assert call_in_progress.status == "in_progress"
    assert call_in_progress.answered_at is not None

    # Check CallEvent created
    evt_stmt = select(CallEvent).where(CallEvent.call_id == call.id)
    events = (await db_session.execute(evt_stmt)).scalars().all()
    assert len(events) >= 1
    assert events[0].event_type == "media_stream_started"

    # 3. Test handle_media with callback verification
    received_pcm_chunks = []

    async def pcm_audio_listener(pcm_chunk: bytes):
        received_pcm_chunks.append(pcm_chunk)

    session.on_pcm16_audio_received = pcm_audio_listener

    # Push 160-byte mu-law audio chunk from Twilio
    raw_mulaw = bytes([0x7E] * 160)
    media_payload = {
        "event": "media",
        "sequenceNumber": "2",
        "streamSid": "MZ_stream_test_999",
        "media": {
            "track": "inbound",
            "chunk": "1",
            "timestamp": "20",
            "payload": base64.b64encode(raw_mulaw).decode("utf-8"),
        },
    }
    await session.handle_media(media_payload)

    # Verify audio was transcoded and dispatched (160 mu-law bytes -> 960 PCM16 24kHz bytes)
    assert len(received_pcm_chunks) == 1
    assert len(received_pcm_chunks[0]) == 960

    # 4. Test send_audio_pcm24k (Outbound audio from AI -> Twilio)
    ai_pcm16_24k = bytes([0x10, 0x00] * 480)  # 480 samples = 960 bytes = 20ms
    await session.send_audio_pcm24k(ai_pcm16_24k)

    # Verify outbound frame sent to Twilio WebSocket
    assert len(mock_ws.sent_messages) == 1
    sent_data = json.loads(mock_ws.sent_messages[0])
    assert sent_data["event"] == "media"
    assert sent_data["streamSid"] == "MZ_stream_test_999"
    decoded_egress_audio = base64.b64decode(sent_data["media"]["payload"])
    assert len(decoded_egress_audio) == 160

    # 5. Test send_mark
    await session.send_mark("turn_1_finished")
    assert len(mock_ws.sent_messages) == 2
    mark_data = json.loads(mock_ws.sent_messages[1])
    assert mark_data["event"] == "mark"
    assert mark_data["mark"]["name"] == "turn_1_finished"

    # 6. Test send_clear (Barge-in / interruption)
    await session.send_clear()
    assert len(mock_ws.sent_messages) == 3
    clear_data = json.loads(mock_ws.sent_messages[2])
    assert clear_data["event"] == "clear"

    # 7. Test handle_stop
    stop_payload = {
        "event": "stop",
        "sequenceNumber": "5",
        "streamSid": "MZ_stream_test_999",
        "stop": {
            "accountSid": "AC_test_account",
            "callSid": "CA_stream_lifecycle_001",
        },
    }
    await session.handle_stop(stop_payload)
    assert session.is_active is False

    # Check Call status updated to completed
    await db_session.refresh(call_in_progress)
    assert call_in_progress.status == "completed"
    assert call_in_progress.ended_at is not None
