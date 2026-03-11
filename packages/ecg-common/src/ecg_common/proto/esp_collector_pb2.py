"""Generated protocol buffer code."""

from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC, 5, 29, 0, "", "esp_collector.proto"
)
_sym_db = _symbol_database.Default()
from . import common_pb2 as common__pb2

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x13esp_collector.proto\x12\recg_streaming\x1a\x0ccommon.proto"\xed\x01\n\nEspMessage\x122\n\x0csensor_frame\x18\x01 \x01(\x0b2\x1a.ecg_streaming.SensorFrameH\x00\x123\n\x0bdevice_info\x18\x02 \x01(\x0b2\x1c.ecg_streaming.UsbDeviceInfoH\x00\x121\n\nconfig_ack\x18\x03 \x01(\x0b2\x1b.ecg_streaming.UsbConfigAckH\x00\x128\n\tble_debug\x18\x04 \x01(\x0b2#.ecg_streaming.BleNotificationDebugH\x00B\t\n\x07message"\xaa\x01\n\x0bSensorFrame\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12.\n\x0bsensor_type\x18\x02 \x01(\x0e2\x19.ecg_streaming.SensorType\x12\x16\n\x0epolar_clock_us\x18\x03 \x01(\x04\x12\x19\n\x11receiver_clock_us\x18\x04 \x01(\x04\x12\x13\n\x0bsample_rate\x18\x05 \x01(\x05\x12\x10\n\x08raw_data\x18\x06 \x01(\x0c"\xd0\x02\n\rUsbDeviceInfo\x12\x0e\n\x06esp_id\x18\x01 \x01(\t\x12\x13\n\x0bapp_version\x18\x02 \x01(\t\x12\x13\n\x0bidf_version\x18\x03 \x01(\t\x12\x18\n\x10protocol_version\x18\x04 \x01(\r\x12\x16\n\x0ecurrent_target\x18\x05 \x01(\t\x12\x17\n\x0fconfig_required\x18\x06 \x01(\x08\x12\x17\n\x0fpolar_connected\x18\x07 \x01(\x08\x121\n\x0cpolar_status\x18\x08 \x01(\x0e2\x1b.ecg_streaming.DeviceStatus\x12\x16\n\x0escanner_active\x18\t \x01(\x08\x12\x1a\n\x12scanner_request_id\x18\n \x01(\r\x12\x1b\n\x13polar_battery_known\x18\x0b \x01(\x08\x12\x1d\n\x15polar_battery_percent\x18\x0c \x01(\r"[\n\x0cUsbConfigAck\x12\x0e\n\x06esp_id\x18\x01 \x01(\t\x12\x10\n\x08accepted\x18\x02 \x01(\x08\x12\x0f\n\x07message\x18\x03 \x01(\t\x12\x18\n\x10target_device_id\x18\x04 \x01(\t"\xe8\x01\n\x14BleNotificationDebug\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12\x12\n\nframe_type\x18\x02 \x01(\r\x12\x10\n\x08pmd_type\x18\x03 \x01(\r\x12\x11\n\tnotif_len\x18\x04 \x01(\r\x12\x14\n\x0csample_count\x18\x05 \x01(\r\x12\x16\n\x0epolar_clock_us\x18\x06 \x01(\x04\x12\x13\n\x0binterval_us\x18\x07 \x01(\r\x12\x1a\n\x12notification_index\x18\x08 \x01(\x04\x12\x18\n\x10conn_interval_ms\x18\t \x01(\r\x12\x0b\n\x03mtu\x18\n \x01(\r"e\n\x0fBleScanSighting\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x0f\n\x07address\x18\x03 \x01(\t\x12\x0c\n\x04rssi\x18\x04 \x01(\x05\x12\x12\n\nseen_at_us\x18\x05 \x01(\x04"{\n\rBleScanResult\x12\x12\n\nrequest_id\x18\x01 \x01(\r\x12\x0e\n\x06esp_id\x18\x02 \x01(\t\x121\n\tsightings\x18\x03 \x03(\x0b2\x1e.ecg_streaming.BleScanSighting\x12\x13\n\x0bduration_ms\x18\x04 \x01(\r"Y\n\x13EspDiscoveryMessage\x127\n\x0fble_scan_result\x18\x01 \x01(\x0b2\x1c.ecg_streaming.BleScanResultH\x00B\t\n\x07message"\x85\x01\n\x15CollectorToEspMessage\x12*\n\x06config\x18\x01 \x01(\x0b2\x18.ecg_streaming.UsbConfigH\x00\x125\n\x0estart_ble_scan\x18\x02 \x01(\x0b2\x1b.ecg_streaming.StartBleScanH\x00B\t\n\x07message"x\n\tUsbConfig\x12\x0e\n\x06esp_id\x18\x01 \x01(\t\x12\x18\n\x10target_device_id\x18\x02 \x01(\t\x12\x17\n\x0fecg_sample_rate\x18\x03 \x01(\x05\x12\x17\n\x0facc_sample_rate\x18\x04 \x01(\x05\x12\x0f\n\x07persist\x18\x05 \x01(\x08"\\\n\x0cStartBleScan\x12\x0e\n\x06esp_id\x18\x01 \x01(\t\x12\x12\n\nrequest_id\x18\x02 \x01(\r\x12\x13\n\x0bduration_ms\x18\x03 \x01(\r\x12\x13\n\x0bname_prefix\x18\x04 \x01(\t*@\n\nSensorType\x12\x13\n\x0fSENSOR_TYPE_ECG\x10\x00\x12\x1d\n\x19SENSOR_TYPE_ACCELEROMETER\x10\x01b\x06proto3'
)
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "esp_collector_pb2", _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals["_SENSORTYPE"]._serialized_start = 1803
    _globals["_SENSORTYPE"]._serialized_end = 1867
    _globals["_ESPMESSAGE"]._serialized_start = 53
    _globals["_ESPMESSAGE"]._serialized_end = 290
    _globals["_SENSORFRAME"]._serialized_start = 293
    _globals["_SENSORFRAME"]._serialized_end = 463
    _globals["_USBDEVICEINFO"]._serialized_start = 466
    _globals["_USBDEVICEINFO"]._serialized_end = 802
    _globals["_USBCONFIGACK"]._serialized_start = 804
    _globals["_USBCONFIGACK"]._serialized_end = 895
    _globals["_BLENOTIFICATIONDEBUG"]._serialized_start = 898
    _globals["_BLENOTIFICATIONDEBUG"]._serialized_end = 1130
    _globals["_BLESCANSIGHTING"]._serialized_start = 1132
    _globals["_BLESCANSIGHTING"]._serialized_end = 1233
    _globals["_BLESCANRESULT"]._serialized_start = 1235
    _globals["_BLESCANRESULT"]._serialized_end = 1358
    _globals["_ESPDISCOVERYMESSAGE"]._serialized_start = 1360
    _globals["_ESPDISCOVERYMESSAGE"]._serialized_end = 1449
    _globals["_COLLECTORTOESPMESSAGE"]._serialized_start = 1452
    _globals["_COLLECTORTOESPMESSAGE"]._serialized_end = 1585
    _globals["_USBCONFIG"]._serialized_start = 1587
    _globals["_USBCONFIG"]._serialized_end = 1707
    _globals["_STARTBLESCAN"]._serialized_start = 1709
    _globals["_STARTBLESCAN"]._serialized_end = 1801
