from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional
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
    __slots__ = ('value', 'polar_clock_us', 'device_id', 'wall_clock_us', 'receiver_clock_us', 'time_verified')
    VALUE_FIELD_NUMBER: _ClassVar[int]
    POLAR_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    WALL_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    RECEIVER_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    TIME_VERIFIED_FIELD_NUMBER: _ClassVar[int]
    value: int
    polar_clock_us: int
    device_id: str
    wall_clock_us: int
    receiver_clock_us: int
    time_verified: bool

    def __init__(self, value: _Optional[int]=..., polar_clock_us: _Optional[int]=..., device_id: _Optional[str]=..., wall_clock_us: _Optional[int]=..., receiver_clock_us: _Optional[int]=..., time_verified: bool=...) -> None:
        ...

class AccelerometerSample(_message.Message):
    __slots__ = ('x', 'y', 'z', 'polar_clock_us', 'device_id', 'wall_clock_us', 'receiver_clock_us', 'time_verified')
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    POLAR_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    WALL_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    RECEIVER_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    TIME_VERIFIED_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    polar_clock_us: int
    device_id: str
    wall_clock_us: int
    receiver_clock_us: int
    time_verified: bool

    def __init__(self, x: _Optional[float]=..., y: _Optional[float]=..., z: _Optional[float]=..., polar_clock_us: _Optional[int]=..., device_id: _Optional[str]=..., wall_clock_us: _Optional[int]=..., receiver_clock_us: _Optional[int]=..., time_verified: bool=...) -> None:
        ...