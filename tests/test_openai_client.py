import base64
import json
import pytest
from backend.app.agents.openai_client import OpenAIRealtimeClient


class MockOpenAIWebSocket:
    """Mock WebSocket client protocol capturing outgoing messages."""
    def __init__(self):
        self.sent_messages = []
        self.is_closed = False

    async def send(self, data: str):
        self.sent_messages.append(data)

    async def close(self):
        self.is_closed = True


@pytest.mark.asyncio
async def test_openai_client_outgoing_events():
    client = OpenAIRealtimeClient(api_key="sk-test-key-12345")
    mock_ws = MockOpenAIWebSocket()
    client.ws = mock_ws
    client.is_connected = True

    # 1. Test update_session
    await client.update_session(
        instructions="You are an AI sales assistant.",
        voice="alloy",
        tools=[{"type": "function", "name": "test_tool"}],
    )
    assert len(mock_ws.sent_messages) == 1
    session_event = json.loads(mock_ws.sent_messages[0])
    assert session_event["type"] == "session.update"
    assert session_event["session"]["voice"] == "alloy"
    assert session_event["session"]["turn_detection"]["type"] == "server_vad"

    # 2. Test append_input_audio
    pcm_audio = bytes([0x01, 0x02] * 240)
    await client.append_input_audio(pcm_audio)
    assert len(mock_ws.sent_messages) == 2
    audio_event = json.loads(mock_ws.sent_messages[1])
    assert audio_event["type"] == "input_audio_buffer.append"
    assert base64.b64decode(audio_event["audio"]) == pcm_audio

    # 3. Test cancel_response (Barge-in)
    await client.cancel_response()
    assert len(mock_ws.sent_messages) == 3
    cancel_event = json.loads(mock_ws.sent_messages[2])
    assert cancel_event["type"] == "response.cancel"

    # 4. Test send_tool_result
    await client.send_tool_result("call_123", '{"status": "available"}')
    assert len(mock_ws.sent_messages) == 5  # tool_output + response.create
    tool_event = json.loads(mock_ws.sent_messages[3])
    assert tool_event["type"] == "conversation.item.create"
    assert tool_event["item"]["call_id"] == "call_123"


@pytest.mark.asyncio
async def test_openai_client_incoming_event_dispatch():
    client = OpenAIRealtimeClient(api_key="sk-test-key-12345")

    dispatched = {
        "audio_chunks": [],
        "speech_started": False,
        "transcripts": [],
        "tool_calls": [],
    }

    async def on_audio(chunk: bytes):
        dispatched["audio_chunks"].append(chunk)

    async def on_speech_start():
        dispatched["speech_started"] = True

    async def on_transcript(role: str, text: str, s: int, e: int):
        dispatched["transcripts"].append((role, text))

    async def on_tool(name: str, call_id: str, args: dict):
        dispatched["tool_calls"].append((name, call_id, args))

    client.on_audio_delta = on_audio
    client.on_speech_started = on_speech_start
    client.on_transcript_completed = on_transcript
    client.on_tool_call = on_tool

    # 1. Dispatch response.audio.delta
    test_audio = b"dummy_pcm16_sound"
    await client._handle_incoming_event({
        "type": "response.audio.delta",
        "delta": base64.b64encode(test_audio).decode("utf-8"),
    })
    assert len(dispatched["audio_chunks"]) == 1
    assert dispatched["audio_chunks"][0] == test_audio

    # 2. Dispatch input_audio_buffer.speech_started
    await client._handle_incoming_event({
        "type": "input_audio_buffer.speech_started",
    })
    assert dispatched["speech_started"] is True

    # 3. Dispatch response.audio_transcript.done
    await client._handle_incoming_event({
        "type": "response.audio_transcript.done",
        "transcript": "Hello, how can I help you?",
    })
    assert len(dispatched["transcripts"]) == 1
    assert dispatched["transcripts"][0] == ("assistant", "Hello, how can I help you?")

    # 4. Dispatch response.function_call_arguments.done
    await client._handle_incoming_event({
        "type": "response.function_call_arguments.done",
        "name": "check_calendar_availability",
        "call_id": "call_abc",
        "arguments": '{"preferred_date": "2026-10-10"}',
    })
    assert len(dispatched["tool_calls"]) == 1
    assert dispatched["tool_calls"][0] == ("check_calendar_availability", "call_abc", {"preferred_date": "2026-10-10"})
