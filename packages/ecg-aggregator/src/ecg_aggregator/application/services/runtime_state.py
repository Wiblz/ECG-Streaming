"""Runtime registries for connected collectors and devices."""

import itertools
import time
from dataclasses import dataclass, field

from ecg_common import DeviceStatus

from ecg_aggregator.domain.time import HostTimeSeconds, Seconds

ACTIVE_DEVICE_WINDOW_S = Seconds(30.0)


@dataclass
class CollectorMetadata:
    """Metadata for a connected collector."""

    collector_id: str
    display_name: str
    device_ids: list[str]
    version: str
    metadata: dict[str, str]
    connected_at: HostTimeSeconds
    last_seen: HostTimeSeconds
    samples_sent: int = 0
    active_devices: int = 0
    generation: int = 0


@dataclass
class DeviceRuntimeStatus:
    """Status information for a device."""

    device_id: str
    collector_id: str
    status: DeviceStatus = DeviceStatus.DISCONNECTED
    last_update: HostTimeSeconds = field(default_factory=lambda: HostTimeSeconds(time.time()))
    last_data_time: HostTimeSeconds | None = None
    battery_level: int | None = None
    error_message: str | None = None


class CollectorRegistry:
    """Own collector runtime state."""

    def __init__(self) -> None:
        self.collectors: dict[str, CollectorMetadata] = {}
        self._generations = itertools.count(1)

    def register(
        self,
        *,
        collector_id: str,
        display_name: str,
        device_ids: list[str],
        version: str,
        metadata: dict[str, str],
    ) -> CollectorMetadata:
        """Register or replace a collector runtime entry."""
        now = HostTimeSeconds(time.time())
        collector = CollectorMetadata(
            collector_id=collector_id,
            display_name=display_name,
            device_ids=device_ids,
            version=version,
            metadata=metadata,
            connected_at=now,
            last_seen=now,
            samples_sent=0,
            active_devices=0,
            generation=next(self._generations),
        )
        self.collectors[collector_id] = collector
        return collector

    def current_generation(self, collector_id: str) -> int | None:
        """Get the registration generation of the current entry, if any."""
        collector = self.collectors.get(collector_id)
        return collector.generation if collector is not None else None

    def record_activity(self, collector_id: str) -> None:
        """Update the last-seen timestamp for a connected collector."""
        collector = self.collectors.get(collector_id)
        if collector is not None:
            collector.last_seen = HostTimeSeconds(time.time())

    def add_samples_sent(self, collector_id: str, count: int) -> None:
        """Increment the sample count for a collector."""
        collector = self.collectors.get(collector_id)
        if collector is not None:
            collector.samples_sent += count

    def set_active_devices(self, collector_id: str, count: int) -> None:
        """Update the active device count for a collector."""
        collector = self.collectors.get(collector_id)
        if collector is not None:
            collector.active_devices = count

    def remove(self, collector_id: str) -> None:
        """Remove a collector from the registry."""
        self.collectors.pop(collector_id, None)


class DeviceRegistry:
    """Own device runtime status state."""

    def __init__(self) -> None:
        self.device_statuses: dict[str, DeviceRuntimeStatus] = {}

    def ensure_device(
        self,
        *,
        device_id: str,
        collector_id: str,
        status: DeviceStatus = DeviceStatus.DISCONNECTED,
    ) -> DeviceRuntimeStatus:
        """Ensure a device exists in the registry."""
        now = HostTimeSeconds(time.time())
        device = self.device_statuses.get(device_id)
        if device is None:
            device = DeviceRuntimeStatus(
                device_id=device_id,
                collector_id=collector_id,
                status=status,
                last_update=now,
            )
            self.device_statuses[device_id] = device
            return device

        device.collector_id = collector_id
        device.last_update = now
        return device

    def mark_data_received(self, *, device_id: str, collector_id: str) -> DeviceRuntimeStatus:
        """Mark that a device sent data recently."""
        device = self.ensure_device(device_id=device_id, collector_id=collector_id)
        device.last_data_time = HostTimeSeconds(time.time())
        return device

    def update_status(
        self,
        *,
        device_id: str,
        collector_id: str,
        status: DeviceStatus,
        battery_level: int | None,
        error_message: str | None,
    ) -> DeviceRuntimeStatus:
        """Update the runtime status for a device."""
        device = self.ensure_device(
            device_id=device_id,
            collector_id=collector_id,
            status=status,
        )
        device.status = status
        device.last_update = HostTimeSeconds(time.time())
        device.battery_level = battery_level
        device.error_message = error_message
        return device

    def disconnect_collector_devices(self, collector_id: str) -> list[str]:
        """Remove all devices for a collector from the registry."""
        disconnected = [
            device_id
            for device_id, device in self.device_statuses.items()
            if device.collector_id == collector_id
        ]
        for device_id in disconnected:
            del self.device_statuses[device_id]
        return disconnected

    def count_active_devices_for_collector(
        self, collector_id: str, active_window_s: Seconds = ACTIVE_DEVICE_WINDOW_S
    ) -> int:
        """Count active devices for a given collector."""
        now = HostTimeSeconds(time.time())
        return sum(
            1
            for device in self.device_statuses.values()
            if device.collector_id == collector_id
            and device.last_data_time is not None
            and (now - device.last_data_time) <= active_window_s
        )

    def count_active_devices(self, active_window_s: Seconds = ACTIVE_DEVICE_WINDOW_S) -> int:
        """Count active devices across all collectors."""
        now = HostTimeSeconds(time.time())
        return sum(
            1
            for device in self.device_statuses.values()
            if device.last_data_time is not None
            and (now - device.last_data_time) <= active_window_s
        )
