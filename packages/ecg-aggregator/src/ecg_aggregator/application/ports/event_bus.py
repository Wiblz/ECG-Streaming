"""Event bus abstractions for core services."""

import asyncio
from typing import Protocol

from ecg_aggregator.domain.events import DomainEvent


class DomainEventBus(Protocol):
    """Publish and subscribe to domain events."""

    async def publish(self, event: DomainEvent) -> None:
        """Publish a single event."""

    async def subscribe(
        self,
        event_types: tuple[type[DomainEvent], ...] | None = None,
    ) -> asyncio.Queue[DomainEvent]:
        """Subscribe to domain events, optionally filtered by type."""

    async def unsubscribe(self, queue: asyncio.Queue[DomainEvent]) -> None:
        """Remove an event subscription."""
