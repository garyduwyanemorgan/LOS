"""WebSocket handlers for real-time lagoon state and notification streaming."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from backend.core.config.settings import settings

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

HEARTBEAT_INTERVAL = 30  # seconds


# ── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections with subscription routing."""

    def __init__(self) -> None:
        # lagoon_id -> set of WebSocket connections
        self._lagoon_connections: dict[str, set[WebSocket]] = {}
        # user_id -> set of WebSocket connections (notifications)
        self._user_connections: dict[str, set[WebSocket]] = {}

    async def connect_lagoon(self, lagoon_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._lagoon_connections.setdefault(lagoon_id, set()).add(ws)
        logger.info("WS connected: lagoon=%s total=%d", lagoon_id,
                    len(self._lagoon_connections[lagoon_id]))

    async def connect_user(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._user_connections.setdefault(user_id, set()).add(ws)
        logger.info("WS connected: user=%s total=%d", user_id,
                    len(self._user_connections[user_id]))

    def disconnect_lagoon(self, lagoon_id: str, ws: WebSocket) -> None:
        conns = self._lagoon_connections.get(lagoon_id, set())
        conns.discard(ws)
        if not conns:
            self._lagoon_connections.pop(lagoon_id, None)

    def disconnect_user(self, user_id: str, ws: WebSocket) -> None:
        conns = self._user_connections.get(user_id, set())
        conns.discard(ws)
        if not conns:
            self._user_connections.pop(user_id, None)

    async def broadcast_to_lagoon(self, lagoon_id: str, message: dict[str, Any]) -> None:
        """Broadcast a JSON message to all connections for a lagoon."""
        conns = list(self._lagoon_connections.get(lagoon_id, set()))
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_lagoon(lagoon_id, ws)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> None:
        """Send a JSON message to all connections for a user."""
        conns = list(self._user_connections.get(user_id, set()))
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_user(user_id, ws)


# Global connection manager instance
manager = ConnectionManager()


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _authenticate_ws(token: str | None) -> dict[str, Any] | None:
    """Validate a JWT and return the user payload, or None if invalid."""
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


# ── Event stream ──────────────────────────────────────────────────────────────

@router.websocket("/ws/lagoon/{lagoon_id}/events")
async def lagoon_events_ws(
    websocket: WebSocket,
    lagoon_id: UUID,
    token: str | None = Query(default=None),
) -> None:
    """Stream domain events for a specific lagoon in real time.

    Authentication: pass JWT as `?token=<access_token>` query parameter.
    """
    user = await _authenticate_ws(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    lagoon_id_str = str(lagoon_id)
    await manager.connect_lagoon(lagoon_id_str, websocket)

    try:
        # Start Redis subscription in background
        redis_task = asyncio.create_task(
            _subscribe_lagoon_events(lagoon_id_str, websocket)
        )
        # Heartbeat loop
        while True:
            try:
                # Wait for client ping with timeout
                await asyncio.wait_for(websocket.receive_text(), timeout=HEARTBEAT_INTERVAL)
            except TimeoutError:
                # Send server heartbeat
                await websocket.send_text(
                    json.dumps({"type": "heartbeat", "ts": datetime.now(UTC).isoformat()})
                )
            except WebSocketDisconnect:
                break
    finally:
        redis_task.cancel()
        manager.disconnect_lagoon(lagoon_id_str, websocket)
        logger.info("WS disconnected: lagoon=%s", lagoon_id_str)


@router.websocket("/ws/lagoon/{lagoon_id}/state")
async def lagoon_state_ws(
    websocket: WebSocket,
    lagoon_id: UUID,
    token: str | None = Query(default=None),
) -> None:
    """Stream live system state updates for a lagoon.

    Pushes state snapshot every time any loop publishes an update.
    Also sends initial state on connect.
    """
    user = await _authenticate_ws(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    lagoon_id_str = str(lagoon_id)
    await manager.connect_lagoon(lagoon_id_str, websocket)

    try:
        # Send initial state
        state = await _get_current_state(lagoon_id_str)
        await websocket.send_text(json.dumps({"type": "state", "data": state}, default=str))

        redis_task = asyncio.create_task(
            _subscribe_state_updates(lagoon_id_str, websocket)
        )

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=HEARTBEAT_INTERVAL)
            except TimeoutError:
                # Push fresh state as heartbeat
                state = await _get_current_state(lagoon_id_str)
                await websocket.send_text(
                    json.dumps({"type": "state_refresh", "data": state}, default=str)
                )
            except WebSocketDisconnect:
                break
    finally:
        redis_task.cancel()
        manager.disconnect_lagoon(lagoon_id_str, websocket)


@router.websocket("/ws/notifications")
async def user_notifications_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Stream personal notifications for the authenticated user.

    Receives alerts, recommendation reviews, and system messages.
    """
    user = await _authenticate_ws(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = user.get("sub", "unknown")
    await manager.connect_user(user_id, websocket)

    try:
        # Welcome message
        await websocket.send_text(
            json.dumps({
                "type": "connected",
                "user_id": user_id,
                "ts": datetime.now(UTC).isoformat(),
            })
        )

        redis_task = asyncio.create_task(
            _subscribe_user_notifications(user_id, websocket)
        )

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=HEARTBEAT_INTERVAL)
            except TimeoutError:
                await websocket.send_text(
                    json.dumps({"type": "heartbeat", "ts": datetime.now(UTC).isoformat()})
                )
            except WebSocketDisconnect:
                break
    finally:
        redis_task.cancel()
        manager.disconnect_user(user_id, websocket)
        logger.info("WS disconnected: user=%s", user_id)


# ── Redis subscription helpers ────────────────────────────────────────────────

async def _subscribe_lagoon_events(lagoon_id: str, ws: WebSocket) -> None:
    """Subscribe to Redis pub/sub channel for lagoon events and forward to WS."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL)
        channel = f"los:events:{lagoon_id}"
        async with r.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await ws.send_text(
                            json.dumps({"type": "event", "data": data}, default=str)
                        )
                    except Exception as exc:
                        logger.debug("WS send failed: %s", exc)
                        break
        await r.aclose()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error("Redis subscription error (lagoon events): %s", exc)


async def _subscribe_state_updates(lagoon_id: str, ws: WebSocket) -> None:
    """Subscribe to Redis pub/sub channel for state updates."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL)
        channel = f"los:state:{lagoon_id}"
        async with r.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await ws.send_text(
                            json.dumps({"type": "state_update", "data": data}, default=str)
                        )
                    except Exception:
                        break
        await r.aclose()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error("Redis subscription error (state): %s", exc)


async def _subscribe_user_notifications(user_id: str, ws: WebSocket) -> None:
    """Subscribe to user-specific notification channel."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL)
        channel = f"los:notifications:{user_id}"
        async with r.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await ws.send_text(
                            json.dumps({"type": "notification", "data": data}, default=str)
                        )
                    except Exception:
                        break
        await r.aclose()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error("Redis subscription error (notifications): %s", exc)


async def _get_current_state(lagoon_id: str) -> dict[str, Any]:
    """Fetch current lagoon state from shared memory."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=3.0)
        raw = await r.get(f"los:state:{lagoon_id}:snapshot")
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.debug("Could not fetch state snapshot: %s", exc)
    return {"lagoon_id": lagoon_id, "status": "state_unavailable"}
