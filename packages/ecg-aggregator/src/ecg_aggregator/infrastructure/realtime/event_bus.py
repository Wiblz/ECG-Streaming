"""In-memory domain event bus."""

import asyncio

from ecg_aggregator.application.ports.event_bus import DomainEventBus
from ecg_aggregator.domain.events import DomainEvent


class InMemoryDomainEventBus(DomainEventBus):
    """A simple in-process pub/sub implementation for domain events."""

    def __init__(self) -> None:
        self._all_subscribers: set[asyncio.Queue[DomainEvent]] = set()
        self._typed_subscribers: dict[type[DomainEvent], set[asyncio.Queue[DomainEvent]]] = {}
        self._queue_filters: dict[
            asyncio.Queue[DomainEvent], tuple[type[DomainEvent], ...] | None
        ] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event: DomainEvent) -> None:
        """Broadcast an event to all exact-type and wildcard subscribers."""
        async with self._lock:
            all_subscribers = tuple(self._all_subscribers)
            typed_subscribers = tuple(self._typed_subscribers.get(type(event), ()))

        for queue in all_subscribers:
            await queue.put(event)

        for queue in typed_subscribers:
            await queue.put(event)

    async def subscribe(
        self,
        event_types: tuple[type[DomainEvent], ...] | None = None,
    ) -> asyncio.Queue[DomainEvent]:
        """Register a queue for domain events."""
        queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        async with self._lock:
            self._queue_filters[queue] = event_types
            if event_types is None:
                self._all_subscribers.add(queue)
            else:
                for event_type in event_types:
                    self._typed_subscribers.setdefault(event_type, set()).add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[DomainEvent]) -> None:
        """Remove a queue subscription."""
        async with self._lock:
            event_types = self._queue_filters.pop(queue, None)
            if event_types is None:
                self._all_subscribers.discard(queue)
                return

            for event_type in event_types:
                subscribers = self._typed_subscribers.get(event_type)
                if not subscribers:
                    continue
                subscribers.discard(queue)
                if not subscribers:
                    self._typed_subscribers.pop(event_type, None)
