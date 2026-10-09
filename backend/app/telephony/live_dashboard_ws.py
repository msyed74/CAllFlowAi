"""
Live Dashboard WebSocket & Supervisor Hub.

Provides real-time bi-directional streaming between active call sessions and
supervisor front-end dashboards (`/ws/live-dashboard/{org_id}`).
Broadcasts:
  - call.started, call.ended, call.updated
  - transcript.turn (speaker_role, text, start_ms, end_ms, is_interrupted)
  - supervisor.whisper (injected coaching guidance)
  - supervisor.takeover (manual human transfer triggered from UI)
  - sentiment.delta
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("telephony.live_dashboard_ws")

router = APIRouter(tags=["Live Dashboard WebSocket"])


class LiveDashboardManager:
    """
    Manages active supervisor WebSocket connections grouped by organization_id.
    Thread-safe and async-safe pub/sub hub.
    """

    def __init__(self):
        # org_id -> set of active WebSockets
        self._connections: Dict[str, Set[WebSocket]] = {}
        # call_id -> active VoiceAgentSession or callback
        self._whisper_handlers: Dict[str, Any] = {}
        self._takeover_handlers: Dict[str, Any] = {}

    async def connect(self, org_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if org_id not in self._connections:
            self._connections[org_id] = set()
        self._connections[org_id].add(websocket)
        logger.info("Supervisor WebSocket connected to org %s (Total: %d)", org_id, len(self._connections[org_id]))

    def disconnect(self, org_id: str, websocket: WebSocket) -> None:
        if org_id in self._connections:
            self._connections[org_id].discard(websocket)
            if not self._connections[org_id]:
                del self._connections[org_id]
        logger.info("Supervisor WebSocket disconnected from org %s", org_id)

    async def broadcast_to_org(self, org_id: str, message: Dict[str, Any]) -> None:
        """Broadcasts JSON payload to all connected supervisors in the organization."""
        if org_id not in self._connections:
            return

        payload_str = json.dumps(message)
        dead_sockets: List[WebSocket] = []

        for ws in self._connections[org_id]:
            try:
                await ws.send_text(payload_str)
            except Exception as e:
                logger.warning("Error broadcasting to supervisor WebSocket: %s", e)
                dead_sockets.append(ws)

        for ws in dead_sockets:
            self.disconnect(org_id, ws)

    def register_whisper_handler(self, call_id: str, handler: Any) -> None:
        """Registers a callback for supervisor whisper injection on a specific call."""
        self._whisper_handlers[call_id] = handler

    def unregister_whisper_handler(self, call_id: str) -> None:
        self._whisper_handlers.pop(call_id, None)

    async def inject_whisper(self, call_id: str, message: str) -> bool:
        """Delivers a coaching whisper prompt into the running agent."""
        handler = self._whisper_handlers.get(call_id)
        if handler:
            try:
                await handler(message)
                return True
            except Exception as e:
                logger.error("Failed to inject whisper into call %s: %s", call_id, e)
        return False

    def register_takeover_handler(self, call_id: str, handler: Any) -> None:
        self._takeover_handlers[call_id] = handler

    def unregister_takeover_handler(self, call_id: str) -> None:
        self._takeover_handlers.pop(call_id, None)

    async def trigger_takeover(self, call_id: str, reason: str = "Supervisor takeover") -> bool:
        handler = self._takeover_handlers.get(call_id)
        if handler:
            try:
                await handler(reason)
                return True
            except Exception as e:
                logger.error("Failed to trigger takeover for call %s: %s", call_id, e)
        return False


# Global manager singleton
dashboard_manager = LiveDashboardManager()


@router.websocket("/ws/live-dashboard/{org_id}")
async def live_dashboard_endpoint(websocket: WebSocket, org_id: str):
    """
    Supervisor real-time streaming endpoint for an organization.
    """
    await dashboard_manager.connect(org_id, websocket)

    # Send initial connection confirmation
    await websocket.send_text(json.dumps({
        "type": "connection.ready",
        "org_id": org_id,
        "message": "Connected to CallFlow AI Real-time Operations Stream",
    }))

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
            except Exception:
                continue

            event_type = data.get("type")

            # 1. Supervisor Whisper
            if event_type == "supervisor.whisper":
                call_id = data.get("call_id")
                whisper_text = data.get("message", "")
                if call_id and whisper_text:
                    success = await dashboard_manager.inject_whisper(call_id, whisper_text)
                    await websocket.send_text(json.dumps({
                        "type": "supervisor.whisper_ack",
                        "call_id": call_id,
                        "success": success,
                    }))

            # 2. Supervisor Takeover
            elif event_type == "supervisor.takeover":
                call_id = data.get("call_id")
                reason = data.get("reason", "Supervisor requested immediate human takeover")
                if call_id:
                    success = await dashboard_manager.trigger_takeover(call_id, reason)
                    await websocket.send_text(json.dumps({
                        "type": "supervisor.takeover_ack",
                        "call_id": call_id,
                        "success": success,
                    }))

            # 3. Ping / Heartbeat
            elif event_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        dashboard_manager.disconnect(org_id, websocket)
    except Exception as e:
        logger.error("Error in supervisor live dashboard WebSocket: %s", e)
        dashboard_manager.disconnect(org_id, websocket)
