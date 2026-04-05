"""Collector query application service."""

import time

from ecg_aggregator.application.dto.collectors import CollectorHealth, CollectorInfoDTO
from ecg_aggregator.application.services.runtime_state import CollectorRegistry
from ecg_aggregator.domain.time import HostTimeSeconds, Seconds
from ecg_aggregator.infrastructure.persistence.sqlite_database import ECGDatabase


class CollectorQueryService:
    """Read-oriented collector queries."""

    def __init__(
        self,
        *,
        database: ECGDatabase,
        collector_registry: CollectorRegistry,
    ) -> None:
        self.database = database
        self.collector_registry = collector_registry

    def list_collectors(self) -> list[CollectorInfoDTO]:
        """Return all known collectors with merged persisted/runtime state."""
        current_time = HostTimeSeconds(time.time())
        db_collectors = {
            collector["collector_id"]: collector for collector in self.database.get_all_collectors()
        }
        connected_collectors = self.collector_registry.collectors
        all_collector_ids = set(db_collectors.keys()) | set(connected_collectors.keys())

        collectors: list[CollectorInfoDTO] = []
        for collector_id in all_collector_ids:
            display_name = collector_id
            device_ids: list[str] = []
            version: str | None = None
            metadata: dict[str, object] = {}
            first_seen: HostTimeSeconds | None = None
            last_seen: HostTimeSeconds | None = None
            connected_at: HostTimeSeconds | None = None
            last_heartbeat: HostTimeSeconds | None = None
            samples_sent = 0
            active_devices = 0

            if collector_id in db_collectors:
                db_info = db_collectors[collector_id]
                display_name = db_info["display_name"] or collector_id
                version = db_info["version"]
                metadata = dict(db_info["metadata"])
                first_seen = db_info["first_seen"]
                last_seen = db_info["last_seen"]
                last_heartbeat = db_info["last_heartbeat"]

            if collector_id in connected_collectors:
                conn_info = connected_collectors[collector_id]
                display_name = conn_info.display_name
                device_ids = conn_info.device_ids
                version = conn_info.version
                metadata = dict(conn_info.metadata)
                connected_at = conn_info.connected_at
                last_heartbeat = conn_info.last_seen
                samples_sent = conn_info.samples_sent
                active_devices = conn_info.active_devices

            health: CollectorHealth = "disconnected"
            time_since_heartbeat: Seconds | None = None
            if last_heartbeat is not None:
                time_since_heartbeat = Seconds(current_time - last_heartbeat)
                if time_since_heartbeat < 15:
                    health = "healthy"
                elif time_since_heartbeat < 30:
                    health = "warning"

            collectors.append(
                CollectorInfoDTO(
                    collector_id=collector_id,
                    display_name=display_name,
                    device_ids=device_ids,
                    version=version,
                    metadata=metadata,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    connected_at=connected_at,
                    last_heartbeat=last_heartbeat,
                    time_since_heartbeat=time_since_heartbeat,
                    samples_sent=samples_sent,
                    active_devices=active_devices,
                    health=health,
                    connected=collector_id in connected_collectors,
                )
            )

        health_order = {"healthy": 0, "warning": 1, "disconnected": 2}
        collectors.sort(
            key=lambda collector: (
                health_order.get(collector.health, 3),
                -(collector.last_seen or 0),
            )
        )
        return collectors
