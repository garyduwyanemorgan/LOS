"""Base class for all LOS scientific services."""
from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ServiceStatus(StrEnum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class ScientificService(ABC):
    """
    Abstract base for all scientific services in the LOS platform.

    Each service continuously observes, interprets, computes,
    publishes and learns. No service executes only once.
    """

    service_name: str
    loop_name: str
    _status: ServiceStatus = ServiceStatus.INITIALIZING
    _last_run: datetime | None = None
    _run_count: int = 0
    _error_count: int = 0

    @abstractmethod
    async def start(self) -> None:
        """Start the continuous service loop."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the service."""

    @abstractmethod
    async def process_event(self, event: dict[str, Any]) -> None:
        """Process an incoming event from the event bus."""

    @abstractmethod
    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        """
        Compute current scientific state for the lagoon.

        Returns dict with state values and confidence.
        """

    @abstractmethod
    async def publish_state(self, lagoon_id: UUID) -> None:
        """Publish current state to shared memory and event bus."""

    @property
    def status(self) -> ServiceStatus:
        return self._status

    def get_health(self) -> dict[str, Any]:
        return {
            "service": self.service_name,
            "loop": self.loop_name,
            "status": self._status.value,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "run_count": self._run_count,
            "error_count": self._error_count,
        }
