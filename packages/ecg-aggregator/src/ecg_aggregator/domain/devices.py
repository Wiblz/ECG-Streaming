"""Device and collector identity helpers."""

_SIMULATED_COLLECTOR_PREFIX = "sim-"
_SIMULATED_DEVICE_PREFIX = "SIM_"


def is_simulated_collector(collector_id: str) -> bool:
    """Return True if the collector ID identifies a simulated collector."""
    return collector_id.startswith(_SIMULATED_COLLECTOR_PREFIX)


def is_simulated_device(device_id: str) -> bool:
    """Return True if the device ID identifies a simulated device.

    Use this only when the collector ID is not available. Prefer
    is_simulated_collector(collector_id) when the collector is known.
    """
    return device_id.startswith(_SIMULATED_DEVICE_PREFIX)
