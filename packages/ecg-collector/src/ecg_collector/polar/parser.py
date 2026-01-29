"""Shared parser for Polar H10 PMD (Polar Measurement Data) frames.

This module provides unified parsing logic for both BLE and USB data flows.
"""

import struct

from ecg_common.proto import common_pb2


def parse_ecg_frame(
    raw_data: bytes,
    last_sample_polar_clock_us: int,
    sample_rate: int,
    device_id: str,
    wall_clock_us: int,
    receiver_clock_us: int,
) -> list[common_pb2.ECGSample]:
    """Parse ECG samples from raw PMD frame data with timestamps.

    Polar H10 ECG format:
    - Each sample is 3 bytes (24-bit signed integer)
    - Sample rate is typically 130 Hz
    - Values are raw ADC counts

    Args:
        raw_data: Raw bytes from PMD frame (after 10-byte header)
        last_sample_polar_clock_us: Polar clock timestamp of last sample (microseconds since Polar boot)
        sample_rate: Sample rate in Hz
        device_id: Device identifier (e.g., "Polar H10 ABC123")
        wall_clock_us: Wall clock (epoch time) when collector received frame (microseconds)
        receiver_clock_us: Receiver clock (microseconds since ESP32/collector boot)

    Returns:
        List of ECGSample proto messages with all timestamps
    """
    sample_count = len(raw_data) // 3
    interval_us = 1_000_000 // sample_rate  # Interval in microseconds
    samples = []

    for i in range(sample_count):
        # Extract 3-byte signed integer (little-endian)
        sample_bytes = raw_data[i * 3 : (i + 1) * 3]
        raw_value = int.from_bytes(sample_bytes, byteorder="little", signed=True)

        # Calculate timestamp for this sample (counting backwards from last sample)
        polar_clock_us = last_sample_polar_clock_us - (sample_count - i - 1) * interval_us

        # Only the last sample has the direct timestamp from PMD frame
        is_last_sample = i == sample_count - 1

        samples.append(
            common_pb2.ECGSample(
                value=raw_value,
                polar_clock_us=int(polar_clock_us),
                device_id=device_id,
                wall_clock_us=wall_clock_us,
                receiver_clock_us=receiver_clock_us,
                time_verified=is_last_sample,
            )
        )

    return samples


def parse_acc_frame(
    raw_data: bytes,
    last_sample_polar_clock_us: int,
    sample_rate: int,
    device_id: str,
    wall_clock_us: int,
    receiver_clock_us: int,
) -> list[common_pb2.AccelerometerSample]:
    """Parse accelerometer samples from raw PMD frame data with timestamps.

    Polar H10 ACC format:
    - Each sample is 6 bytes (3x int16 for x, y, z)
    - Sample rate is typically 50-200 Hz (configurable)
    - Values are in milligravity (mG), converted to g

    Args:
        raw_data: Raw bytes from PMD frame (after 10-byte header)
        last_sample_polar_clock_us: Polar clock timestamp of last sample (microseconds since Polar boot)
        sample_rate: Sample rate in Hz
        device_id: Device identifier (e.g., "Polar H10 ABC123")
        wall_clock_us: Wall clock (epoch time) when collector received frame (microseconds)
        receiver_clock_us: Receiver clock (microseconds since ESP32/collector boot)

    Returns:
        List of AccelerometerSample proto messages with all timestamps
    """
    sample_count = len(raw_data) // 6
    interval_us = 1_000_000 // sample_rate  # Interval in microseconds
    samples = []

    for i in range(sample_count):
        offset = i * 6
        # Extract 3x int16 values (x, y, z) in little-endian
        x, y, z = struct.unpack("<hhh", raw_data[offset : offset + 6])

        # Polar H10 sends accelerometer data in milligravity (mG)
        # Convert to g (gravity units) by dividing by 1000
        x_g = x / 1000.0
        y_g = y / 1000.0
        z_g = z / 1000.0

        # Calculate timestamp for this sample (counting backwards from last sample)
        polar_clock_us = last_sample_polar_clock_us - (sample_count - i - 1) * interval_us

        # Only the last sample has the direct timestamp from PMD frame
        is_last_sample = i == sample_count - 1

        samples.append(
            common_pb2.AccelerometerSample(
                x=x_g,
                y=y_g,
                z=z_g,
                polar_clock_us=int(polar_clock_us),
                device_id=device_id,
                wall_clock_us=wall_clock_us,
                receiver_clock_us=receiver_clock_us,
                time_verified=is_last_sample,
            )
        )

    return samples
