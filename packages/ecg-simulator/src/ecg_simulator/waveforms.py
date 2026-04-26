"""Synthetic waveform generators and device factory for the ECG simulator."""

import math

from ecg_simulator.config import SimulatedDevice, SimulatorConfig


def generate_device_id(index: int) -> str:
    """Generate a deterministic device identifier with SIM prefix."""
    value = index & 0xFFFFFFFFFFFF
    octets = [(value >> shift) & 0xFF for shift in range(40, -1, -8)]
    mac_address = ":".join(f"{octet:02X}" for octet in octets)
    return f"SIM_{mac_address}"


def build_collectors(config: SimulatorConfig) -> list[tuple[str, list[SimulatedDevice]]]:
    """Create collectors and distribute devices evenly across them."""
    collector_count = max(1, config.collectors)
    buckets: list[list[SimulatedDevice]] = [[] for _ in range(collector_count)]

    # Polar clock represents device uptime, not wall time - start from small value
    base_polar_us = 10_000_000  # 10 seconds of device uptime
    for index in range(config.devices):
        collector_index = index % collector_count
        device = SimulatedDevice(
            device_id=generate_device_id(index + 1),
            nickname=f"Sim Device {index + 1:02d}",
            ecg_phase=(index * 0.37) % (2 * math.pi),
            acc_phase=(index * 0.19) % (2 * math.pi),
            battery_level=max(30, 100 - index),
            polar_clock_us=base_polar_us + (index * 5_000),
            receiver_clock_offset_us=collector_index * 100_000 + index * 1_000,
        )
        buckets[collector_index].append(device)

    collectors: list[tuple[str, list[SimulatedDevice]]] = []
    for collector_index, devices in enumerate(buckets, start=1):
        collector_id = f"sim-collector-{collector_index:02d}"
        collectors.append((collector_id, devices))
    return collectors


def triangle_wave(phase: float) -> float:
    """Return a triangle wave in the range [-1, 1] for phase in [0, 1)."""
    return 1.0 - 4.0 * abs(phase - 0.5)


def square_wave(phase: float) -> float:
    """Return a square wave in the range [-1, 1] for phase in [0, 1)."""
    return 1.0 if phase < 0.5 else -1.0


def tent_pulse(phase: float, center: float, width: float) -> float:
    """Return a triangular pulse in [0, 1] centered at `center` with half-width `width`."""
    distance = abs(phase - center)
    if distance >= width:
        return 0.0
    return 1.0 - (distance / width)
