import common_pb2 as _common_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union
DESCRIPTOR: _descriptor.FileDescriptor

class SensorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SENSOR_TYPE_ECG: _ClassVar[SensorType]
    SENSOR_TYPE_ACCELEROMETER: _ClassVar[SensorType]
SENSOR_TYPE_ECG: SensorType
SENSOR_TYPE_ACCELEROMETER: SensorType

class EspMessage(_message.Message):
    __slots__ = ('sensor_frame', 'device_info', 'config_ack', 'ble_debug')
    SENSOR_FRAME_FIELD_NUMBER: _ClassVar[int]
    DEVICE_INFO_FIELD_NUMBER: _ClassVar[int]
    CONFIG_ACK_FIELD_NUMBER: _ClassVar[int]
    BLE_DEBUG_FIELD_NUMBER: _ClassVar[int]
    sensor_frame: SensorFrame
    device_info: UsbDeviceInfo
    config_ack: UsbConfigAck
    ble_debug: BleNotificationDebug

    def __init__(self, sensor_frame: _Optional[_Union[SensorFrame, _Mapping]]=..., device_info: _Optional[_Union[UsbDeviceInfo, _Mapping]]=..., config_ack: _Optional[_Union[UsbConfigAck, _Mapping]]=..., ble_debug: _Optional[_Union[BleNotificationDebug, _Mapping]]=...) -> None:
        ...

class SensorFrame(_message.Message):
    __slots__ = ('device_id', 'sensor_type', 'polar_clock_us', 'receiver_clock_us', 'sample_rate', 'raw_data')
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SENSOR_TYPE_FIELD_NUMBER: _ClassVar[int]
    POLAR_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    RECEIVER_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    RAW_DATA_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    sensor_type: SensorType
    polar_clock_us: int
    receiver_clock_us: int
    sample_rate: int
    raw_data: bytes

    def __init__(self, device_id: _Optional[str]=..., sensor_type: _Optional[_Union[SensorType, str]]=..., polar_clock_us: _Optional[int]=..., receiver_clock_us: _Optional[int]=..., sample_rate: _Optional[int]=..., raw_data: _Optional[bytes]=...) -> None:
        ...

class UsbDeviceInfo(_message.Message):
    __slots__ = ('esp_id', 'firmware_version', 'current_target', 'config_required', 'polar_connected', 'polar_status')
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TARGET_FIELD_NUMBER: _ClassVar[int]
    CONFIG_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    POLAR_CONNECTED_FIELD_NUMBER: _ClassVar[int]
    POLAR_STATUS_FIELD_NUMBER: _ClassVar[int]
    esp_id: str
    firmware_version: str
    current_target: str
    config_required: bool
    polar_connected: bool
    polar_status: _common_pb2.DeviceStatus

    def __init__(self, esp_id: _Optional[str]=..., firmware_version: _Optional[str]=..., current_target: _Optional[str]=..., config_required: bool=..., polar_connected: bool=..., polar_status: _Optional[_Union[_common_pb2.DeviceStatus, str]]=...) -> None:
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
    __slots__ = ('device_id', 'frame_type', 'pmd_type', 'notif_len', 'sample_count', 'polar_clock_us', 'interval_us', 'notification_index', 'conn_interval_ms', 'mtu')
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    FRAME_TYPE_FIELD_NUMBER: _ClassVar[int]
    PMD_TYPE_FIELD_NUMBER: _ClassVar[int]
    NOTIF_LEN_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_COUNT_FIELD_NUMBER: _ClassVar[int]
    POLAR_CLOCK_US_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_US_FIELD_NUMBER: _ClassVar[int]
    NOTIFICATION_INDEX_FIELD_NUMBER: _ClassVar[int]
    CONN_INTERVAL_MS_FIELD_NUMBER: _ClassVar[int]
    MTU_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    frame_type: int
    pmd_type: int
    notif_len: int
    sample_count: int
    polar_clock_us: int
    interval_us: int
    notification_index: int
    conn_interval_ms: int
    mtu: int

    def __init__(self, device_id: _Optional[str]=..., frame_type: _Optional[int]=..., pmd_type: _Optional[int]=..., notif_len: _Optional[int]=..., sample_count: _Optional[int]=..., polar_clock_us: _Optional[int]=..., interval_us: _Optional[int]=..., notification_index: _Optional[int]=..., conn_interval_ms: _Optional[int]=..., mtu: _Optional[int]=...) -> None:
        ...

class CollectorToEspMessage(_message.Message):
    __slots__ = ('config',)
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    config: UsbConfig

    def __init__(self, config: _Optional[_Union[UsbConfig, _Mapping]]=...) -> None:
        ...

class UsbConfig(_message.Message):
    __slots__ = ('esp_id', 'target_device_id', 'ecg_sample_rate', 'acc_sample_rate', 'persist')
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    ECG_SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    ACC_SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    PERSIST_FIELD_NUMBER: _ClassVar[int]
    esp_id: str
    target_device_id: str
    ecg_sample_rate: int
    acc_sample_rate: int
    persist: bool

    def __init__(self, esp_id: _Optional[str]=..., target_device_id: _Optional[str]=..., ecg_sample_rate: _Optional[int]=..., acc_sample_rate: _Optional[int]=..., persist: bool=...) -> None:
        ...