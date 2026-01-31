"""Generated protocol buffer code."""

from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC, 5, 29, 0, "", "common.proto"
)
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x0ccommon.proto\x12\recg_streaming"\x8e\x01\n\tECGSample\x12\r\n\x05value\x18\x01 \x01(\x05\x12\x16\n\x0epolar_clock_us\x18\x02 \x01(\x04\x12\x11\n\tdevice_id\x18\x03 \x01(\t\x12\x15\n\rwall_clock_us\x18\x04 \x01(\x04\x12\x19\n\x11receiver_clock_us\x18\x05 \x01(\x04\x12\x15\n\rtime_verified\x18\x06 \x01(\x08"\xaa\x01\n\x13AccelerometerSample\x12\t\n\x01x\x18\x01 \x01(\x02\x12\t\n\x01y\x18\x02 \x01(\x02\x12\t\n\x01z\x18\x03 \x01(\x02\x12\x16\n\x0epolar_clock_us\x18\x04 \x01(\x04\x12\x11\n\tdevice_id\x18\x05 \x01(\t\x12\x15\n\rwall_clock_us\x18\x06 \x01(\x04\x12\x19\n\x11receiver_clock_us\x18\x07 \x01(\x04\x12\x15\n\rtime_verified\x18\x08 \x01(\x08*\xba\x01\n\x0cDeviceStatus\x12\x19\n\x15DEVICE_STATUS_UNKNOWN\x10\x00\x12\x1e\n\x1aDEVICE_STATUS_DISCONNECTED\x10\x01\x12\x1c\n\x18DEVICE_STATUS_CONNECTING\x10\x02\x12\x1b\n\x17DEVICE_STATUS_CONNECTED\x10\x03\x12\x1b\n\x17DEVICE_STATUS_STREAMING\x10\x04\x12\x17\n\x13DEVICE_STATUS_ERROR\x10\x05b\x06proto3'
)
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "common_pb2", _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals["_DEVICESTATUS"]._serialized_start = 350
    _globals["_DEVICESTATUS"]._serialized_end = 536
    _globals["_ECGSAMPLE"]._serialized_start = 32
    _globals["_ECGSAMPLE"]._serialized_end = 174
    _globals["_ACCELEROMETERSAMPLE"]._serialized_start = 177
    _globals["_ACCELEROMETERSAMPLE"]._serialized_end = 347
