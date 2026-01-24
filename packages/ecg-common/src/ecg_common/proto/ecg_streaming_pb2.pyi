from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union
DESCRIPTOR: _descriptor.FileDescriptor

class UsbPayloadType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    USB_PAYLOAD_TYPE_UNKNOWN: _ClassVar[UsbPayloadType]
    USB_PAYLOAD_TYPE_COLLECTOR_MESSAGE: _ClassVar[UsbPayloadType]
    USB_PAYLOAD_TYPE_AGGREGATOR_MESSAGE: _ClassVar[UsbPayloadType]

class DeviceStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DEVICE_STATUS_UNKNOWN: _ClassVar[DeviceStatus]
    DEVICE_STATUS_DISCONNECTED: _ClassVar[DeviceStatus]
    DEVICE_STATUS_CONNECTING: _ClassVar[DeviceStatus]
    DEVICE_STATUS_CONNECTED: _ClassVar[DeviceStatus]
    DEVICE_STATUS_STREAMING: _ClassVar[DeviceStatus]
    DEVICE_STATUS_ERROR: _ClassVar[DeviceStatus]
USB_PAYLOAD_TYPE_UNKNOWN: UsbPayloadType
USB_PAYLOAD_TYPE_COLLECTOR_MESSAGE: UsbPayloadType
USB_PAYLOAD_TYPE_AGGREGATOR_MESSAGE: UsbPayloadType
DEVICE_STATUS_UNKNOWN: DeviceStatus
DEVICE_STATUS_DISCONNECTED: DeviceStatus
DEVICE_STATUS_CONNECTING: DeviceStatus
DEVICE_STATUS_CONNECTED: DeviceStatus
DEVICE_STATUS_STREAMING: DeviceStatus
DEVICE_STATUS_ERROR: DeviceStatus

class UsbFrame(_message.Message):
    __slots__ = ('version', 'payload_type', 'seq', 'crc32', 'payload')
    VERSION_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_TYPE_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    CRC32_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    version: int
    payload_type: UsbPayloadType
    seq: int
    crc32: int
    payload: bytes

    def __init__(self, version: _Optional[int]=..., payload_type: _Optional[_Union[UsbPayloadType, str]]=..., seq: _Optional[int]=..., crc32: _Optional[int]=..., payload: _Optional[bytes]=...) -> None:
        ...

class CollectorMessage(_message.Message):
    __slots__ = ('registration', 'ecg_batch', 'status_update', 'heartbeat', 'acc_batch', 'usb_device_info', 'usb_config_ack', 'ble_debug')
    REGISTRATION_FIELD_NUMBER: _ClassVar[int]
    ECG_BATCH_FIELD_NUMBER: _ClassVar[int]
    STATUS_UPDATE_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    ACC_BATCH_FIELD_NUMBER: _ClassVar[int]
    USB_DEVICE_INFO_FIELD_NUMBER: _ClassVar[int]
    USB_CONFIG_ACK_FIELD_NUMBER: _ClassVar[int]
    BLE_DEBUG_FIELD_NUMBER: _ClassVar[int]
    registration: CollectorRegistration
    ecg_batch: ECGSampleBatch
    status_update: DeviceStatusUpdate
    heartbeat: CollectorHeartbeat
    acc_batch: AccelerometerSampleBatch
    usb_device_info: UsbDeviceInfo
    usb_config_ack: UsbConfigAck
    ble_debug: BleNotificationDebug

    def __init__(self, registration: _Optional[_Union[CollectorRegistration, _Mapping]]=..., ecg_batch: _Optional[_Union[ECGSampleBatch, _Mapping]]=..., status_update: _Optional[_Union[DeviceStatusUpdate, _Mapping]]=..., heartbeat: _Optional[_Union[CollectorHeartbeat, _Mapping]]=..., acc_batch: _Optional[_Union[AccelerometerSampleBatch, _Mapping]]=..., usb_device_info: _Optional[_Union[UsbDeviceInfo, _Mapping]]=..., usb_config_ack: _Optional[_Union[UsbConfigAck, _Mapping]]=..., ble_debug: _Optional[_Union[BleNotificationDebug, _Mapping]]=...) -> None:
        ...

class AggregatorMessage(_message.Message):
    __slots__ = ('registration_ack', 'sync_status', 'control', 'usb_config')
    REGISTRATION_ACK_FIELD_NUMBER: _ClassVar[int]
    SYNC_STATUS_FIELD_NUMBER: _ClassVar[int]
    CONTROL_FIELD_NUMBER: _ClassVar[int]
    USB_CONFIG_FIELD_NUMBER: _ClassVar[int]
    registration_ack: RegistrationAck
    sync_status: SyncStatusUpdate
    control: ControlCommand
    usb_config: UsbConfig

    def __init__(self, registration_ack: _Optional[_Union[RegistrationAck, _Mapping]]=..., sync_status: _Optional[_Union[SyncStatusUpdate, _Mapping]]=..., control: _Optional[_Union[ControlCommand, _Mapping]]=..., usb_config: _Optional[_Union[UsbConfig, _Mapping]]=...) -> None:
        ...

class CollectorRegistration(_message.Message):
    __slots__ = ('collector_id', 'device_ids', 'version', 'metadata', 'display_name')

    class MetadataEntry(_message.Message):
        __slots__ = ('key', 'value')
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str

        def __init__(self, key: _Optional[str]=..., value: _Optional[str]=...) -> None:
            ...
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

    def __init__(self, collector_id: _Optional[str]=..., device_ids: _Optional[_Iterable[str]]=..., version: _Optional[str]=..., metadata: _Optional[_Mapping[str, str]]=..., display_name: _Optional[str]=...) -> None:
        ...

class RegistrationAck(_message.Message):
    __slots__ = ('accepted', 'message', 'server_time_ms')
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SERVER_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    message: str
    server_time_ms: int

    def __init__(self, accepted: bool=..., message: _Optional[str]=..., server_time_ms: _Optional[int]=...) -> None:
        ...

class ECGSampleBatch(_message.Message):
    __slots__ = ('device_id', 'samples', 'batch_timestamp_ms')
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_FIELD_NUMBER: _ClassVar[int]
    BATCH_TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    samples: _containers.RepeatedCompositeFieldContainer[ECGSample]
    batch_timestamp_ms: int

    def __init__(self, device_id: _Optional[str]=..., samples: _Optional[_Iterable[_Union[ECGSample, _Mapping]]]=..., batch_timestamp_ms: _Optional[int]=...) -> None:
        ...

class ECGSample(_message.Message):
    __slots__ = ('device_timestamp_us', 'host_receive_time_s', 'raw_value', 'sample_rate')
    DEVICE_TIMESTAMP_US_FIELD_NUMBER: _ClassVar[int]
    HOST_RECEIVE_TIME_S_FIELD_NUMBER: _ClassVar[int]
    RAW_VALUE_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    device_timestamp_us: float
    host_receive_time_s: float
    raw_value: int
    sample_rate: int

    def __init__(self, device_timestamp_us: _Optional[float]=..., host_receive_time_s: _Optional[float]=..., raw_value: _Optional[int]=..., sample_rate: _Optional[int]=...) -> None:
        ...

class AccelerometerSampleBatch(_message.Message):
    __slots__ = ('device_id', 'samples', 'batch_timestamp_ms')
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_FIELD_NUMBER: _ClassVar[int]
    BATCH_TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    samples: _containers.RepeatedCompositeFieldContainer[AccelerometerSample]
    batch_timestamp_ms: int

    def __init__(self, device_id: _Optional[str]=..., samples: _Optional[_Iterable[_Union[AccelerometerSample, _Mapping]]]=..., batch_timestamp_ms: _Optional[int]=...) -> None:
        ...

class AccelerometerSample(_message.Message):
    __slots__ = ('device_timestamp_us', 'host_receive_time_s', 'x', 'y', 'z', 'sample_rate')
    DEVICE_TIMESTAMP_US_FIELD_NUMBER: _ClassVar[int]
    HOST_RECEIVE_TIME_S_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    device_timestamp_us: float
    host_receive_time_s: float
    x: float
    y: float
    z: float
    sample_rate: int

    def __init__(self, device_timestamp_us: _Optional[float]=..., host_receive_time_s: _Optional[float]=..., x: _Optional[float]=..., y: _Optional[float]=..., z: _Optional[float]=..., sample_rate: _Optional[int]=...) -> None:
        ...

class DeviceStatusUpdate(_message.Message):
    __slots__ = ('device_id', 'status', 'battery_level', 'error_message', 'device_info')

    class DeviceInfoEntry(_message.Message):
        __slots__ = ('key', 'value')
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str

        def __init__(self, key: _Optional[str]=..., value: _Optional[str]=...) -> None:
            ...
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

    def __init__(self, device_id: _Optional[str]=..., status: _Optional[_Union[DeviceStatus, str]]=..., battery_level: _Optional[int]=..., error_message: _Optional[str]=..., device_info: _Optional[_Mapping[str, str]]=...) -> None:
        ...

class CollectorHeartbeat(_message.Message):
    __slots__ = ('timestamp_ms', 'samples_sent', 'active_devices')
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_SENT_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_DEVICES_FIELD_NUMBER: _ClassVar[int]
    timestamp_ms: int
    samples_sent: int
    active_devices: int

    def __init__(self, timestamp_ms: _Optional[int]=..., samples_sent: _Optional[int]=..., active_devices: _Optional[int]=...) -> None:
        ...

class SyncStatusUpdate(_message.Message):
    __slots__ = ('device_id', 'sync_ready', 'offset_s', 'offset_version', 'confidence')
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

    def __init__(self, device_id: _Optional[str]=..., sync_ready: bool=..., offset_s: _Optional[float]=..., offset_version: _Optional[int]=..., confidence: _Optional[float]=...) -> None:
        ...

class ControlCommand(_message.Message):
    __slots__ = ('command', 'device_id', 'parameters')

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
        __slots__ = ('key', 'value')
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str

        def __init__(self, key: _Optional[str]=..., value: _Optional[str]=...) -> None:
            ...
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    command: ControlCommand.CommandType
    device_id: str
    parameters: _containers.ScalarMap[str, str]

    def __init__(self, command: _Optional[_Union[ControlCommand.CommandType, str]]=..., device_id: _Optional[str]=..., parameters: _Optional[_Mapping[str, str]]=...) -> None:
        ...

class UsbDeviceInfo(_message.Message):
    __slots__ = ('esp_id', 'firmware_version', 'current_target', 'config_required', 'polar_connected')
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TARGET_FIELD_NUMBER: _ClassVar[int]
    CONFIG_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    POLAR_CONNECTED_FIELD_NUMBER: _ClassVar[int]
    esp_id: str
    firmware_version: str
    current_target: str
    config_required: bool
    polar_connected: bool

    def __init__(self, esp_id: _Optional[str]=..., firmware_version: _Optional[str]=..., current_target: _Optional[str]=..., config_required: bool=..., polar_connected: bool=...) -> None:
        ...

class UsbConfig(_message.Message):
    __slots__ = ('esp_id', 'target_device_id', 'ecg_sample_rate', 'acc_sample_rate', 'ecg_batch_size', 'acc_batch_size', 'persist')
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    ECG_SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    ACC_SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    ECG_BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    ACC_BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    PERSIST_FIELD_NUMBER: _ClassVar[int]
    esp_id: str
    target_device_id: str
    ecg_sample_rate: int
    acc_sample_rate: int
    ecg_batch_size: int
    acc_batch_size: int
    persist: bool

    def __init__(self, esp_id: _Optional[str]=..., target_device_id: _Optional[str]=..., ecg_sample_rate: _Optional[int]=..., acc_sample_rate: _Optional[int]=..., ecg_batch_size: _Optional[int]=..., acc_batch_size: _Optional[int]=..., persist: bool=...) -> None:
        ...

class UsbConfigAck(_message.Message):
    __slots__ = ('esp_id', 'accepted', 'message', 'target_device_id')
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TARGET_DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    esp_id: str
    accepted: bool
    message: str
    target_device_id: str

    def __init__(self, esp_id: _Optional[str]=..., accepted: bool=..., message: _Optional[str]=..., target_device_id: _Optional[str]=...) -> None:
        ...

class BleNotificationDebug(_message.Message):
    __slots__ = ('device_id', 'frame_type', 'pmd_type', 'notif_len', 'sample_count', 'pmd_timestamp_ns', 'interval_ms', 'notification_index')
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    FRAME_TYPE_FIELD_NUMBER: _ClassVar[int]
    PMD_TYPE_FIELD_NUMBER: _ClassVar[int]
    NOTIF_LEN_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_COUNT_FIELD_NUMBER: _ClassVar[int]
    PMD_TIMESTAMP_NS_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_MS_FIELD_NUMBER: _ClassVar[int]
    NOTIFICATION_INDEX_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    frame_type: int
    pmd_type: int
    notif_len: int
    sample_count: int
    pmd_timestamp_ns: int
    interval_ms: int
    notification_index: int

    def __init__(self, device_id: _Optional[str]=..., frame_type: _Optional[int]=..., pmd_type: _Optional[int]=..., notif_len: _Optional[int]=..., sample_count: _Optional[int]=..., pmd_timestamp_ns: _Optional[int]=..., interval_ms: _Optional[int]=..., notification_index: _Optional[int]=...) -> None:
        ...