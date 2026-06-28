"""Integration tests for the Redis Streams event bus.

Requires Redis running at localhost:6379.
Skip these tests if Redis is unavailable.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from backend.event_bus.models import (
    ChemicalEvent,
    EventPriority,
    EventType,
    LOSEvent,
)


def _redis_available() -> bool:
    try:
        import redis as sync_redis
        r = sync_redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        return True
    except Exception:
        return False


redis_available = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis not available at localhost:6379",
)


@pytest.mark.asyncio
@redis_available
async def test_event_serialisation_round_trip() -> None:
    """LOSEvent must serialise to Redis payload and deserialise back to identical object."""
    event = ChemicalEvent(
        lagoon_id=uuid.uuid4(),
        event_type=EventType.DO_CRITICAL_LOW.value,
        priority=EventPriority.CRITICAL,
        confidence=0.92,
        payload={"do_mg_l": 1.8, "parameter": "dissolved_oxygen"},
    )

    redis_payload = event.to_redis_payload()
    restored = LOSEvent.from_redis_payload(redis_payload)

    assert str(restored.lagoon_id) == str(event.lagoon_id)
    assert restored.event_type == event.event_type
    assert restored.priority == event.priority
    assert abs(restored.confidence - event.confidence) < 0.001
    assert restored.payload["do_mg_l"] == 1.8


@pytest.mark.asyncio
@redis_available
async def test_event_bus_publish_subscribe() -> None:
    """EventBus publish → subscribe cycle must deliver the event."""
    from backend.event_bus.bus import EventBus

    bus = EventBus(redis_url="redis://localhost:6379/15")  # use DB 15 for tests
    await bus.connect()

    lagoon_id = uuid.uuid4()
    received_events: list[LOSEvent] = []

    async def handler(event: LOSEvent) -> None:
        received_events.append(event)

    consumer_task = asyncio.create_task(
        bus.subscribe(
            stream_name=f"los:lagoon:{lagoon_id}",
            consumer_group="test-group",
            consumer_name="test-consumer-1",
            handler=handler,
            max_messages=1,
        )
    )

    await asyncio.sleep(0.1)

    event = ChemicalEvent(
        lagoon_id=lagoon_id,
        event_type=EventType.DO_CRITICAL_LOW.value,
        priority=EventPriority.HIGH,
        confidence=0.88,
        payload={"test": True},
    )
    await bus.publish(event)

    try:
        await asyncio.wait_for(consumer_task, timeout=5.0)
    except asyncio.TimeoutError:
        consumer_task.cancel()

    assert len(received_events) == 1, f"Expected 1 event, got {len(received_events)}"
    received = received_events[0]
    assert str(received.lagoon_id) == str(lagoon_id)

    await bus.disconnect()
