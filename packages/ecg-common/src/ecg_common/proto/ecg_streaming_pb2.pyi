from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import (
    ClassVar as _ClassVar,
)

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
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

class CollectorMessage(_message.Message):
    __slots__ = ("registration", "sample_batch", "status_update", "heartbeat")
    REGISTRATION_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_BATCH_FIELD_NUMBER: _ClassVar[int]
    STATUS_UPDATE_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    registration: CollectorRegistration
    sample_batch: ECGSampleBatch
    status_update: DeviceStatusUpdate
    heartbeat: CollectorHeartbeat

    def __init__(
        self,
        registration: CollectorRegistration | _Mapping | None = ...,
        sample_batch: ECGSampleBatch | _Mapping | None = ...,
        status_update: DeviceStatusUpdate | _Mapping | None = ...,
        heartbeat: CollectorHeartbeat | _Mapping | None = ...,
    ) -> None: ...

class AggregatorMessage(_message.Message):
    __slots__ = ("registration_ack", "sync_status", "control")
    REGISTRATION_ACK_FIELD_NUMBER: _ClassVar[int]
    SYNC_STATUS_FIELD_NUMBER: _ClassVar[int]
    CONTROL_FIELD_NUMBER: _ClassVar[int]
    registration_ack: RegistrationAck
    sync_status: SyncStatusUpdate
    control: ControlCommand

    def __init__(
        self,
        registration_ack: RegistrationAck | _Mapping | None = ...,
        sync_status: SyncStatusUpdate | _Mapping | None = ...,
        control: ControlCommand | _Mapping | None = ...,
    ) -> None: ...

class CollectorRegistration(_message.Message):
    __slots__ = ("collector_id", "device_ids", "version", "metadata", "display_name")

    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str

        def __init__(self, key: str | None = ..., value: str | None = ...) -> None: ...

    COLLECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_IDS_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    collector_id: str
    device_ids: _containers.RepeatedScalarFieldContainer[str]
    version: str
    metadata: _containers.ScalarMap[str, str]
    display_name: str

    def __init__(
        self,
        collector_id: str | None = ...,
        device_ids: _Iterable[str] | None = ...,
        version: str | None = ...,
        metadata: _Mapping[str, str] | None = ...,
        display_name: str | None = ...,
    ) -> None: ...

class RegistrationAck(_message.Message):
    __slots__ = ("accepted", "message", "server_time_ms")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SERVER_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    message: str
    server_time_ms: int

    def __init__(
        self,
        accepted: bool = ...,
        message: str | None = ...,
        server_time_ms: int | None = ...,
    ) -> None: ...

class ECGSampleBatch(_message.Message):
    __slots__ = ("device_id", "samples", "batch_timestamp_ms")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_FIELD_NUMBER: _ClassVar[int]
    BATCH_TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    samples: _containers.RepeatedCompositeFieldContainer[ECGSample]
    batch_timestamp_ms: int

    def __init__(
        self,
        device_id: str | None = ...,
        samples: _Iterable[ECGSample | _Mapping] | None = ...,
        batch_timestamp_ms: int | None = ...,
    ) -> None: ...

class ECGSample(_message.Message):
    __slots__ = ("device_timestamp_us", "host_receive_time_s", "raw_value", "sample_rate")
    DEVICE_TIMESTAMP_US_FIELD_NUMBER: _ClassVar[int]
    HOST_RECEIVE_TIME_S_FIELD_NUMBER: _ClassVar[int]
    RAW_VALUE_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    device_timestamp_us: float
    host_receive_time_s: float
    raw_value: int
    sample_rate: int

    def __init__(
        self,
        device_timestamp_us: float | None = ...,
        host_receive_time_s: float | None = ...,
        raw_value: int | None = ...,
        sample_rate: int | None = ...,
    ) -> None: ...

class DeviceStatusUpdate(_message.Message):
    __slots__ = ("device_id", "status", "battery_level", "error_message", "device_info")

    class DeviceInfoEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str

        def __init__(self, key: str | None = ..., value: str | None = ...) -> None: ...

    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    BATTERY_LEVEL_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    DEVICE_INFO_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    status: DeviceStatus
    battery_level: int
    error_message: str
    device_info: _containers.ScalarMap[str, str]

    def __init__(
        self,
        device_id: str | None = ...,
        status: DeviceStatus | str | None = ...,
        battery_level: int | None = ...,
        error_message: str | None = ...,
        device_info: _Mapping[str, str] | None = ...,
    ) -> None: ...

class CollectorHeartbeat(_message.Message):
    __slots__ = ("timestamp_ms", "samples_sent", "active_devices")
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_SENT_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_DEVICES_FIELD_NUMBER: _ClassVar[int]
    timestamp_ms: int
    samples_sent: int
    active_devices: int

    def __init__(
        self,
        timestamp_ms: int | None = ...,
        samples_sent: int | None = ...,
        active_devices: int | None = ...,
    ) -> None: ...

class SyncStatusUpdate(_message.Message):
    __slots__ = ("device_id", "sync_ready", "offset_s", "offset_version", "confidence")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SYNC_READY_FIELD_NUMBER: _ClassVar[int]
    OFFSET_S_FIELD_NUMBER: _ClassVar[int]
    OFFSET_VERSION_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    sync_ready: bool
    offset_s: float
    offset_version: int
    confidence: float

    def __init__(
        self,
        device_id: str | None = ...,
        sync_ready: bool = ...,
        offset_s: float | None = ...,
        offset_version: int | None = ...,
        confidence: float | None = ...,
    ) -> None: ...

class ControlCommand(_message.Message):
    __slots__ = ("command", "device_id", "parameters")

    class CommandType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        COMMAND_TYPE_UNKNOWN: _ClassVar[ControlCommand.CommandType]
        COMMAND_TYPE_START_DEVICE: _ClassVar[ControlCommand.CommandType]
        COMMAND_TYPE_STOP_DEVICE: _ClassVar[ControlCommand.CommandType]
        COMMAND_TYPE_DISCONNECT_DEVICE: _ClassVar[ControlCommand.CommandType]
        COMMAND_TYPE_SHUTDOWN: _ClassVar[ControlCommand.CommandType]

    COMMAND_TYPE_UNKNOWN: ControlCommand.CommandType
    COMMAND_TYPE_START_DEVICE: ControlCommand.CommandType
    COMMAND_TYPE_STOP_DEVICE: ControlCommand.CommandType
    COMMAND_TYPE_DISCONNECT_DEVICE: ControlCommand.CommandType
    COMMAND_TYPE_SHUTDOWN: ControlCommand.CommandType

    class ParametersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str

        def __init__(self, key: str | None = ..., value: str | None = ...) -> None: ...

    COMMAND_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    command: ControlCommand.CommandType
    device_id: str
    parameters: _containers.ScalarMap[str, str]

    def __init__(
        self,
        command: ControlCommand.CommandType | str | None = ...,
        device_id: str | None = ...,
        parameters: _Mapping[str, str] | None = ...,
    ) -> None: ...
