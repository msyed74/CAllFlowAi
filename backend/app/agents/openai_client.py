import asyncio
import base64
import json
import logging
from typing import Any, Callable, Dict, List, Optional
import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger("agents.openai_client")


class OpenAIRealtimeClient:
    """
    Asynchronous WebSocket client communicating with the OpenAI Realtime API.
    Streams bi-directional 24kHz PCM16 audio, server-side VAD, transcripts, and function calls.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-realtime-preview-2024-10-01",
        base_ws_url: str = "wss://api.openai.com/v1/realtime",
    ):
        self.api_key = api_key
        self.model = model
        self.base_ws_url = base_ws_url
        self.ws: Optional[WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self.is_connected: bool = False

        # Event Callbacks
        self.on_audio_delta: Optional[Callable[[bytes], asyncio.Future]] = None
        self.on_speech_started: Optional[Callable[[], asyncio.Future]] = None
        self.on_speech_stopped: Optional[Callable[[], asyncio.Future]] = None
        self.on_transcript_completed: Optional[Callable[[str, str, int, int], asyncio.Future]] = None
        self.on_tool_call: Optional[Callable[[str, str, Dict[str, Any]], asyncio.Future]] = None
        self.on_error: Optional[Callable[[str], asyncio.Future]] = None

    async def connect(self) -> None:
        """Establishes authenticated WebSocket connection to OpenAI Realtime API."""
        url = f"{self.base_ws_url}?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        try:
            self.ws = await websockets.connect(url, extra_headers=headers)
            self.is_connected = True
            self._receive_task = asyncio.create_task(self._listen_loop())
            logger.info("Connected to OpenAI Realtime WebSocket.")
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}")
            self.is_connected = False
            raise

    async def disconnect(self) -> None:
        """Gracefully terminates connection and stops listener task."""
        self.is_connected = False
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
            self.ws = None
        logger.info("Disconnected from OpenAI Realtime API.")

    async def send_event(self, event: Dict[str, Any]) -> None:
        """Dispatches JSON protocol message to OpenAI."""
        if not self.ws or not self.is_connected:
            return
        await self.ws.send(json.dumps(event))

    async def update_session(
        self,
        instructions: str,
        voice: str = "alloy",
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        vad_silence_threshold_ms: int = 500,
        vad_prefix_padding_ms: int = 300,
    ) -> None:
        """Configures session persona, modalities, tools, and server-side VAD."""
        event = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": instructions,
                "voice": voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": vad_prefix_padding_ms,
                    "silence_duration_ms": vad_silence_threshold_ms,
                },
                "tools": tools or [],
                "tool_choice": "auto",
                "temperature": temperature,
            },
        }
        await self.send_event(event)

    async def append_input_audio(self, pcm16_audio: bytes) -> None:
        """Streams chunk of 24kHz PCM16 audio to OpenAI input audio buffer."""
        payload_b64 = base64.b64encode(pcm16_audio).decode("utf-8")
        event = {
            "type": "input_audio_buffer.append",
            "audio": payload_b64,
        }
        await self.send_event(event)

    async def cancel_response(self) -> None:
        """Cancels current in-flight assistant response upon user barge-in."""
        event = {
            "type": "response.cancel",
        }
        await self.send_event(event)

    async def create_response(self) -> None:
        """Explicitly requests assistant response generation."""
        event = {
            "type": "response.create",
        }
        await self.send_event(event)

    async def send_tool_result(self, tool_call_id: str, output: str) -> None:
        """Returns tool call execution result and requests continuing assistant speech."""
        tool_output_event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": tool_call_id,
                "output": output,
            },
        }
        await self.send_event(tool_output_event)
        await self.send_event({"type": "response.create"})

    async def _listen_loop(self) -> None:
        """Event listener loop dispatching incoming OpenAI events to handlers."""
        try:
            async for raw_message in self.ws:
                event = json.loads(raw_message)
                await self._handle_incoming_event(event)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in OpenAI Realtime receive loop: {e}")
            if self.on_error:
                await self.on_error(str(e))

    async def _handle_incoming_event(self, event: Dict[str, Any]) -> None:
        event_type = event.get("type", "")

        # 1. Output Audio Streaming (PCM16 24kHz)
        if event_type == "response.audio.delta":
            delta_b64 = event.get("delta", "")
            if delta_b64 and self.on_audio_delta:
                audio_bytes = base64.b64decode(delta_b64)
                await self.on_audio_delta(audio_bytes)

        # 2. Server-side VAD Barge-in / Speech Start
        elif event_type == "input_audio_buffer.speech_started":
            logger.debug("OpenAI VAD: User speech started (Barge-in trigger)")
            if self.on_speech_started:
                await self.on_speech_started()

        # 3. User Speech Stopped
        elif event_type == "input_audio_buffer.speech_stopped":
            logger.debug("OpenAI VAD: User speech stopped")
            if self.on_speech_stopped:
                await self.on_speech_stopped()

        # 4. User Speech Transcription Completed
        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event.get("transcript", "").strip()
            item_id = event.get("item_id", "")
            if transcript and self.on_transcript_completed:
                await self.on_transcript_completed("user", transcript, 0, 0)

        # 5. Assistant Output Transcript Completed
        elif event_type == "response.audio_transcript.done":
            transcript = event.get("transcript", "").strip()
            if transcript and self.on_transcript_completed:
                await self.on_transcript_completed("assistant", transcript, 0, 0)

        # 6. Function / Tool Call Request
        elif event_type == "response.function_call_arguments.done":
            tool_name = event.get("name", "")
            call_id = event.get("call_id", "")
            raw_args = event.get("arguments", "{}")
            try:
                parsed_args = json.loads(raw_args)
            except Exception:
                parsed_args = {}

            logger.info(f"OpenAI function call requested: {tool_name}({parsed_args})")
            if self.on_tool_call:
                await self.on_tool_call(tool_name, call_id, parsed_args)

        # 7. Error Handling
        elif event_type == "error":
            err_msg = event.get("error", {}).get("message", "Unknown OpenAI Realtime error")
            logger.error(f"OpenAI Realtime API Error: {err_msg}")
            if self.on_error:
                await self.on_error(err_msg)
