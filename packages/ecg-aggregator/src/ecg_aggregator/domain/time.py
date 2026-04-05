"""Shared semantic time types used across the aggregator."""

from typing import NewType

Seconds = NewType("Seconds", float)
HostTimeSeconds = NewType("HostTimeSeconds", float)
DeviceClockSeconds = NewType("DeviceClockSeconds", float)
GlobalTimeSeconds = NewType("GlobalTimeSeconds", float)
OffsetSeconds = NewType("OffsetSeconds", float)
DeviceTimestampUs = NewType("DeviceTimestampUs", int)
WallClockUs = NewType("WallClockUs", int)
ReceiverClockUs = NewType("ReceiverClockUs", int)
