from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class DeviceStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DEVICE_STATUS_UNKNOWN: _ClassVar[DeviceStatus]
    DEVICE_STATUS_DISCONNECTED: _ClassVar[DeviceStatus]
    DEVICE_STATUS_CONNECTING: _ClassVar[DeviceStatus]
    DEVICE_STATUS_CONNECTED: _ClassVar[DeviceStatus]
    DEVICE_STATUS_STREAMING: _ClassVar[DeviceStatus]
    DEVICE_STATUS_ERROR: _ClassVar[DeviceStatus]

DEVICE_STATUS_UNKNOWN: DeviceStatus
DEVICE_STATUS_DISCONNECTED: DeviceStatus
DEVICE_STATUS_CONNECTING: DeviceStatus
DEVICE_STATUS_CONNECTED: DeviceStatus
DEVICE_STATUS_STREAMING: DeviceStatus
DEVICE_STATUS_ERROR: DeviceStatus

class ECGSample(_message.Message):
    __slots__ = ("value", "polar_clock_us")
    VALUE_FIELD_NUMBER: _ClassVar[int]
    POLAR_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    value: int
    polar_clock_us: int

    def __init__(self, value: int | None = ..., polar_clock_us: int | None = ...) -> None: ...

class AccelerometerSample(_message.Message):
    __slots__ = ("x", "y", "z", "polar_clock_us")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    POLAR_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    polar_clock_us: int

    def __init__(
        self,
        x: float | None = ...,
        y: float | None = ...,
        z: float | None = ...,
        polar_clock_us: int | None = ...,
    ) -> None: ...
