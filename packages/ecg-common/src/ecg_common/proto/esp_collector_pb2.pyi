from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import (
    ClassVar as _ClassVar,
)

import common_pb2 as _common_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class SensorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SENSOR_TYPE_ECG: _ClassVar[SensorType]
    SENSOR_TYPE_ACCELEROMETER: _ClassVar[SensorType]

SENSOR_TYPE_ECG: SensorType
SENSOR_TYPE_ACCELEROMETER: SensorType

class EspMessage(_message.Message):
    __slots__ = ("sensor_frame", "device_info", "config_ack", "ble_debug")
    SENSOR_FRAME_FIELD_NUMBER: _ClassVar[int]
    DEVICE_INFO_FIELD_NUMBER: _ClassVar[int]
    CONFIG_ACK_FIELD_NUMBER: _ClassVar[int]
    BLE_DEBUG_FIELD_NUMBER: _ClassVar[int]
    sensor_frame: SensorFrame
    device_info: UsbDeviceInfo
    config_ack: UsbConfigAck
    ble_debug: BleNotificationDebug

    def __init__(
        self,
        sensor_frame: SensorFrame | _Mapping | None = ...,
        device_info: UsbDeviceInfo | _Mapping | None = ...,
        config_ack: UsbConfigAck | _Mapping | None = ...,
        ble_debug: BleNotificationDebug | _Mapping | None = ...,
    ) -> None: ...

class SensorFrame(_message.Message):
    __slots__ = (
        "device_id",
        "sensor_type",
        "polar_clock_us",
        "receiver_clock_us",
        "sample_rate",
        "raw_data",
    )
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

    def __init__(
        self,
        device_id: str | None = ...,
        sensor_type: SensorType | str | None = ...,
        polar_clock_us: int | None = ...,
        receiver_clock_us: int | None = ...,
        sample_rate: int | None = ...,
        raw_data: bytes | None = ...,
    ) -> None: ...

class UsbDeviceInfo(_message.Message):
    __slots__ = (
        "esp_id",
        "app_version",
        "idf_version",
        "protocol_version",
        "current_target",
        "config_required",
        "polar_connected",
        "polar_status",
        "scanner_active",
        "scanner_request_id",
        "polar_battery_known",
        "polar_battery_percent",
    )
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    APP_VERSION_FIELD_NUMBER: _ClassVar[int]
    IDF_VERSION_FIELD_NUMBER: _ClassVar[int]
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TARGET_FIELD_NUMBER: _ClassVar[int]
    CONFIG_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    POLAR_CONNECTED_FIELD_NUMBER: _ClassVar[int]
    POLAR_STATUS_FIELD_NUMBER: _ClassVar[int]
    SCANNER_ACTIVE_FIELD_NUMBER: _ClassVar[int]
    SCANNER_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    POLAR_BATTERY_KNOWN_FIELD_NUMBER: _ClassVar[int]
    POLAR_BATTERY_PERCENT_FIELD_NUMBER: _ClassVar[int]
    esp_id: str
    app_version: str
    idf_version: str
    protocol_version: int
    current_target: str
    config_required: bool
    polar_connected: bool
    polar_status: _common_pb2.DeviceStatus
    scanner_active: bool
    scanner_request_id: int
    polar_battery_known: bool
    polar_battery_percent: int

    def __init__(
        self,
        esp_id: str | None = ...,
        app_version: str | None = ...,
        idf_version: str | None = ...,
        protocol_version: int | None = ...,
        current_target: str | None = ...,
        config_required: bool = ...,
        polar_connected: bool = ...,
        polar_status: _common_pb2.DeviceStatus | str | None = ...,
        scanner_active: bool = ...,
        scanner_request_id: int | None = ...,
        polar_battery_known: bool = ...,
        polar_battery_percent: int | None = ...,
    ) -> None: ...

class UsbConfigAck(_message.Message):
    __slots__ = ("esp_id", "accepted", "message", "target_device_id")
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TARGET_DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    esp_id: str
    accepted: bool
    message: str
    target_device_id: str

    def __init__(
        self,
        esp_id: str | None = ...,
        accepted: bool = ...,
        message: str | None = ...,
        target_device_id: str | None = ...,
    ) -> None: ...

class BleNotificationDebug(_message.Message):
    __slots__ = (
        "device_id",
        "frame_type",
        "pmd_type",
        "notif_len",
        "sample_count",
        "polar_clock_us",
        "interval_us",
        "notification_index",
        "conn_interval_ms",
        "mtu",
    )
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

    def __init__(
        self,
        device_id: str | None = ...,
        frame_type: int | None = ...,
        pmd_type: int | None = ...,
        notif_len: int | None = ...,
        sample_count: int | None = ...,
        polar_clock_us: int | None = ...,
        interval_us: int | None = ...,
        notification_index: int | None = ...,
        conn_interval_ms: int | None = ...,
        mtu: int | None = ...,
    ) -> None: ...

class BleScanSighting(_message.Message):
    __slots__ = ("device_id", "name", "address", "rssi", "seen_at_us")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    RSSI_FIELD_NUMBER: _ClassVar[int]
    SEEN_AT_US_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    name: str
    address: str
    rssi: int
    seen_at_us: int

    def __init__(
        self,
        device_id: str | None = ...,
        name: str | None = ...,
        address: str | None = ...,
        rssi: int | None = ...,
        seen_at_us: int | None = ...,
    ) -> None: ...

class BleScanResult(_message.Message):
    __slots__ = ("request_id", "esp_id", "sightings", "duration_ms")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    SIGHTINGS_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    request_id: int
    esp_id: str
    sightings: _containers.RepeatedCompositeFieldContainer[BleScanSighting]
    duration_ms: int

    def __init__(
        self,
        request_id: int | None = ...,
        esp_id: str | None = ...,
        sightings: _Iterable[BleScanSighting | _Mapping] | None = ...,
        duration_ms: int | None = ...,
    ) -> None: ...

class EspDiscoveryMessage(_message.Message):
    __slots__ = ("ble_scan_result",)
    BLE_SCAN_RESULT_FIELD_NUMBER: _ClassVar[int]
    ble_scan_result: BleScanResult

    def __init__(self, ble_scan_result: BleScanResult | _Mapping | None = ...) -> None: ...

class CollectorToEspMessage(_message.Message):
    __slots__ = ("config", "start_ble_scan")
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    START_BLE_SCAN_FIELD_NUMBER: _ClassVar[int]
    config: UsbConfig
    start_ble_scan: StartBleScan

    def __init__(
        self,
        config: UsbConfig | _Mapping | None = ...,
        start_ble_scan: StartBleScan | _Mapping | None = ...,
    ) -> None: ...

class UsbConfig(_message.Message):
    __slots__ = ("esp_id", "target_device_id", "ecg_sample_rate", "acc_sample_rate", "persist")
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

    def __init__(
        self,
        esp_id: str | None = ...,
        target_device_id: str | None = ...,
        ecg_sample_rate: int | None = ...,
        acc_sample_rate: int | None = ...,
        persist: bool = ...,
    ) -> None: ...

class StartBleScan(_message.Message):
    __slots__ = ("esp_id", "request_id", "duration_ms", "name_prefix")
    ESP_ID_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    NAME_PREFIX_FIELD_NUMBER: _ClassVar[int]
    esp_id: str
    request_id: int
    duration_ms: int
    name_prefix: str

    def __init__(
        self,
        esp_id: str | None = ...,
        request_id: int | None = ...,
        duration_ms: int | None = ...,
        name_prefix: str | None = ...,
    ) -> None: ...
