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
    b'\n\x13esp_collector.proto\x12\recg_streaming\x1a\x0ccommon.proto"\xed\x01\n\nEspMessage\x122\n\x0csensor_frame\x18\x01 \x01(\x0b2\x1a.ecg_streaming.SensorFrameH\x00\x123\n\x0bdevice_info\x18\x02 \x01(\x0b2\x1c.ecg_streaming.UsbDeviceInfoH\x00\x121\n\nconfig_ack\x18\x03 \x01(\x0b2\x1b.ecg_streaming.UsbConfigAckH\x00\x128\n\tble_debug\x18\x04 \x01(\x0b2#.ecg_streaming.BleNotificationDebugH\x00B\t\n\x07message"\xaa\x01\n\x0bSensorFrame\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12.\n\x0bsensor_type\x18\x02 \x01(\x0e2\x19.ecg_streaming.SensorType\x12\x16\n\x0epolar_clock_us\x18\x03 \x01(\x04\x12\x19\n\x11receiver_clock_us\x18\x04 \x01(\x04\x12\x13\n\x0bsample_rate\x18\x05 \x01(\x05\x12\x10\n\x08raw_data\x18\x06 \x01(\x0c"\xb6\x01\n\rUsbDeviceInfo\x12\x0e\n\x06esp_id\x18\x01 \x01(\t\x12\x18\n\x10firmware_version\x18\x02 \x01(\t\x12\x16\n\x0ecurrent_target\x18\x03 \x01(\t\x12\x17\n\x0fconfig_required\x18\x04 \x01(\x08\x12\x17\n\x0fpolar_connected\x18\x05 \x01(\x08\x121\n\x0cpolar_status\x18\x06 \x01(\x0e2\x1b.ecg_streaming.DeviceStatus"[\n\x0cUsbConfigAck\x12\x0e\n\x06esp_id\x18\x01 \x01(\t\x12\x10\n\x08accepted\x18\x02 \x01(\x08\x12\x0f\n\x07message\x18\x03 \x01(\t\x12\x18\n\x10target_device_id\x18\x04 \x01(\t"\xc1\x01\n\x14BleNotificationDebug\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12\x12\n\nframe_type\x18\x02 \x01(\r\x12\x10\n\x08pmd_type\x18\x03 \x01(\r\x12\x11\n\tnotif_len\x18\x04 \x01(\r\x12\x14\n\x0csample_count\x18\x05 \x01(\r\x12\x16\n\x0epolar_clock_us\x18\x06 \x01(\x04\x12\x13\n\x0binterval_us\x18\x07 \x01(\r\x12\x1a\n\x12notification_index\x18\x08 \x01(\x04"N\n\x15CollectorToEspMessage\x12*\n\x06config\x18\x01 \x01(\x0b2\x18.ecg_streaming.UsbConfigH\x00B\t\n\x07message"x\n\tUsbConfig\x12\x0e\n\x06esp_id\x18\x01 \x01(\t\x12\x18\n\x10target_device_id\x18\x02 \x01(\t\x12\x17\n\x0fecg_sample_rate\x18\x03 \x01(\x05\x12\x17\n\x0facc_sample_rate\x18\x04 \x01(\x05\x12\x0f\n\x07persist\x18\x05 \x01(\x08*@\n\nSensorType\x12\x13\n\x0fSENSOR_TYPE_ECG\x10\x00\x12\x1d\n\x19SENSOR_TYPE_ACCELEROMETER\x10\x01b\x06proto3'
)
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "esp_collector_pb2", _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals["_SENSORTYPE"]._serialized_start = 1141
    _globals["_SENSORTYPE"]._serialized_end = 1205
    _globals["_ESPMESSAGE"]._serialized_start = 53
    _globals["_ESPMESSAGE"]._serialized_end = 290
    _globals["_SENSORFRAME"]._serialized_start = 293
    _globals["_SENSORFRAME"]._serialized_end = 463
    _globals["_USBDEVICEINFO"]._serialized_start = 466
    _globals["_USBDEVICEINFO"]._serialized_end = 648
    _globals["_USBCONFIGACK"]._serialized_start = 650
    _globals["_USBCONFIGACK"]._serialized_end = 741
    _globals["_BLENOTIFICATIONDEBUG"]._serialized_start = 744
    _globals["_BLENOTIFICATIONDEBUG"]._serialized_end = 937
    _globals["_COLLECTORTOESPMESSAGE"]._serialized_start = 939
    _globals["_COLLECTORTOESPMESSAGE"]._serialized_end = 1017
    _globals["_USBCONFIG"]._serialized_start = 1019
    _globals["_USBCONFIG"]._serialized_end = 1139
