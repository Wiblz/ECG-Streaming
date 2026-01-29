"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 0, '', 'usb_transport.proto')
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x13usb_transport.proto\x12\recg_streaming"}\n\x08UsbFrame\x12\x0f\n\x07version\x18\x01 \x01(\r\x123\n\x0cpayload_type\x18\x02 \x01(\x0e2\x1d.ecg_streaming.UsbPayloadType\x12\x0b\n\x03seq\x18\x03 \x01(\x07\x12\r\n\x05crc32\x18\x04 \x01(\x07\x12\x0f\n\x07payload\x18\x05 \x01(\x0c*w\n\x0eUsbPayloadType\x12\x1c\n\x18USB_PAYLOAD_TYPE_UNKNOWN\x10\x00\x12 \n\x1cUSB_PAYLOAD_TYPE_ESP_MESSAGE\x10\x01\x12%\n!USB_PAYLOAD_TYPE_COLLECTOR_TO_ESP\x10\x02b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'usb_transport_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_USBPAYLOADTYPE']._serialized_start = 165
    _globals['_USBPAYLOADTYPE']._serialized_end = 284
    _globals['_USBFRAME']._serialized_start = 38
    _globals['_USBFRAME']._serialized_end = 163