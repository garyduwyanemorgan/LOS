"""LOS Event Bus — Redis Streams implementation.

Uses Redis Streams for durable, ordered, replayable event delivery.
Each scientific loop priority level gets its own stream.
Consumer groups enable at-least-once delivery with acknowledgement.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import redis.asyncio as aioredis

from backend.core.config.settings import settings as _settings
from backend.event_bus.models import EventPriority, LOSEvent

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

logger = logging.getLogger(__name__)

# Stream names per priority tier
STREAM_NAMES: dict[str, str] = {
    EventPriority.CRITICAL.value: "los:events:critical",
    EventPriority.HIGH.value: "los:events:high",
    EventPriority.NORMAL.value: "los:events:normal",
    EventPriority.LOW.value: "los:events:low",
}

# Default stream for unknown priority
DEFAULT_STREAM = "los:events:normal"

# Lagoon-specific stream prefix for per-lagoon filtering
LAGOON_STREAM_PREFIX = "los:lagoon"

# Global archive stream (all events, for replay/audit)
ARCHIVE_STREAM = "los:events:archive"


class EventBus:
    """Redis Streams based event bus.

    Supports:
    - Priority-routed publish (critical/high/normal/low streams)
    - Per-lagoon fan-out stream for WebSocket consumers
    - Archive stream for full audit and replay
    - Consumer group subscription with at-least-once delivery
    - Manual acknowledgement
    - Reconnection on transient failures
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._subscriptions: list[asyncio.Task[None]] = []
        self._running = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish Redis connection."""
        self._redis = aioredis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            socket_timeout=10,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        await self._redis.ping()
        self._running = True
        logger.info("EventBus connected: %s", self._redis_url)

    async def disconnect(self) -> None:
        """Cancel all subscriptions and close the Redis connection."""
        self._running = False
        for task in self._subscriptions:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._subscriptions.clear()
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("EventBus disconnected")

    def _require_redis(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("EventBus is not connected. Call connect() first.")
        return self._redis

    # ── Publishing ─────────────────────────────────────────────────────────────

    async def publish(self, event: LOSEvent, stream_name: str | None = None) -> str:
        """Publish an event to the appropriate priority stream.

        Also fans out to:
        - The lagoon-specific stream (for per-lagoon WebSocket consumers)
        - The archive stream (for audit and full replay)

        Args:
            event: The LOSEvent to publish.
            stream_name: Override the auto-selected priority stream.

        Returns:
            Redis message ID of the primary stream entry.
        """
        r = self._require_redis()
        payload = event.to_redis_payload()

        priority_val = event.priority.value if isinstance(event.priority, EventPriority) else str(event.priority)
        target = stream_name or STREAM_NAMES.get(priority_val, DEFAULT_STREAM)

        # Primary stream — bounded (keep last 10k per priority)
        message_id: str = await r.xadd(target, payload, maxlen=10_000, approximate=True)

        # Archive — unbounded (full audit)
        await r.xadd(ARCHIVE_STREAM, payload)

        # Lagoon fan-out — bounded per-lagoon (keep last 5k)
        lagoon_stream = f"{LAGOON_STREAM_PREFIX}:{event.lagoon_id}"
        await r.xadd(lagoon_stream, payload, maxlen=5_000, approximate=True)

        logger.debug(
            "Event published type=%s lagoon=%s priority=%s stream=%s id=%s",
            event.event_type,
            event.lagoon_id,
            priority_val,
            target,
            message_id,
        )
        return message_id

    # ── Consumer Groups ────────────────────────────────────────────────────────

    async def create_consumer_group(
        self,
        stream_name: str,
        group_name: str,
        start_id: str = "$",
    ) -> None:
        """Create a consumer group on a stream.

        ``start_id='$'`` reads only new messages; ``'0'`` reads from beginning.
        Silently ignores BUSYGROUP errors (group already exists).
        """
        r = self._require_redis()
        try:
            await r.xgroup_create(stream_name, group_name, start_id, mkstream=True)
            logger.info("Consumer group created: stream=%s group=%s", stream_name, group_name)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.debug("Consumer group already exists: %s/%s", stream_name, group_name)
            else:
                raise

    async def subscribe(
        self,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        handler: Callable[[LOSEvent], Awaitable[None]],
        batch_size: int = 10,
        block_ms: int = 2000,
    ) -> None:
        """Start a background consumer loop on a stream using a consumer group.

        Messages are acknowledged after successful handler execution.
        On handler failure, the message is left unacknowledged for retry
        (it will reappear in the pending entries list).

        Args:
            stream_name: Redis stream key to consume from.
            consumer_group: Consumer group name.
            consumer_name: Unique name for this consumer instance.
            handler: Async callable invoked for each event.
            batch_size: Max messages per XREADGROUP call.
            block_ms: XREADGROUP blocking timeout in milliseconds.
        """
        await self.create_consumer_group(stream_name, consumer_group)

        async def _consume() -> None:
            logger.info(
                "Consumer started: stream=%s group=%s consumer=%s",
                stream_name, consumer_group, consumer_name,
            )
            while self._running:
                try:
                    r = self._require_redis()
                    messages = await r.xreadgroup(
                        consumer_group,
                        consumer_name,
                        {stream_name: ">"},
                        count=batch_size,
                        block=block_ms,
                    )
                    for _stream, entries in (messages or []):
                        for message_id, fields in entries:
                            try:
                                event = LOSEvent.from_redis_payload(fields)
                                await handler(event)
                                await self.acknowledge(stream_name, consumer_group, message_id)
                            except Exception as exc:
                                logger.error(
                                    "Consumer handler error — message NOT acked: "
                                    "stream=%s id=%s error=%s",
                                    stream_name, message_id, exc,
                                )
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Consumer loop error: %s — retrying in 5s", exc)
                    await asyncio.sleep(5)

        task = asyncio.create_task(
            _consume(), name=f"consumer:{stream_name}:{consumer_group}"
        )
        self._subscriptions.append(task)

    async def acknowledge(
        self, stream_name: str, group_name: str, message_id: str
    ) -> None:
        """Acknowledge a message so it is removed from the pending entries list."""
        r = self._require_redis()
        await r.xack(stream_name, group_name, message_id)

    # ── Replay / History ───────────────────────────────────────────────────────

    async def replay_events(
        self,
        stream_name: str,
        start_id: str = "0-0",
        count: int = 1000,
    ) -> list[LOSEvent]:
        """Read events from a stream starting at start_id.

        Use ``'0-0'`` to replay from the very beginning.
        Use a specific message ID as a checkpoint.
        """
        r = self._require_redis()
        messages = await r.xrange(stream_name, min=start_id, count=count)
        events: list[LOSEvent] = []
        for _message_id, fields in messages:
            try:
                events.append(LOSEvent.from_redis_payload(fields))
            except Exception as exc:
                logger.warning("Failed to deserialise event during replay: %s", exc)
        return events

    async def get_event_history(
        self,
        lagoon_id: UUID,
        hours: int = 24,
        count: int = 500,
    ) -> list[LOSEvent]:
        """Retrieve recent events for a specific lagoon from its dedicated stream."""
        r = self._require_redis()
        lagoon_stream = f"{LAGOON_STREAM_PREFIX}:{lagoon_id}"
        start_ms = int(datetime.now(tz=UTC).timestamp() * 1000) - hours * 3600 * 1000
        start_id = f"{start_ms}-0"

        messages = await r.xrange(lagoon_stream, min=start_id, count=count)
        events: list[LOSEvent] = []
        for _message_id, fields in messages:
            try:
                events.append(LOSEvent.from_redis_payload(fields))
            except Exception as exc:
                logger.warning("Failed to deserialise event from history: %s", exc)
        return events

    async def get_live_events(
        self,
        lagoon_id: UUID,
        last_id: str = "$",
        block_ms: int = 5000,
    ) -> tuple[list[LOSEvent], str]:
        """Long-poll for new events since last_id (for WebSocket handlers).

        Returns:
            Tuple of (events, new_cursor_id).
        """
        r = self._require_redis()
        lagoon_stream = f"{LAGOON_STREAM_PREFIX}:{lagoon_id}"
        messages = await r.xread({lagoon_stream: last_id}, count=50, block=block_ms)
        events: list[LOSEvent] = []
        new_last_id = last_id
        for _stream, entries in (messages or []):
            for message_id, fields in entries:
                try:
                    events.append(LOSEvent.from_redis_payload(fields))
                    new_last_id = message_id
                except Exception as exc:
                    logger.warning("Failed to deserialise live event: %s", exc)
        return events, new_last_id

    # ── Health ─────────────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """Return event bus health status for the /health endpoint."""
        if self._redis is None:
            return {"status": "disconnected", "connected": False}
        try:
            await self._redis.ping()
            stream_lengths: dict[str, int] = {}
            for priority_val, stream_name in STREAM_NAMES.items():
                try:
                    stream_lengths[priority_val] = await self._redis.xlen(stream_name)
                except Exception:
                    stream_lengths[priority_val] = -1
            return {
                "status": "healthy",
                "connected": True,
                "active_subscriptions": len(self._subscriptions),
                "stream_lengths": stream_lengths,
            }
        except Exception as exc:
            return {"status": "unhealthy", "connected": False, "error": str(exc)}


# Module-level singleton — used throughout the application.
event_bus = EventBus(redis_url=_settings.REDIS_URL)
