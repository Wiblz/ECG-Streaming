from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class UsbPayloadType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    USB_PAYLOAD_TYPE_UNKNOWN: _ClassVar[UsbPayloadType]
    USB_PAYLOAD_TYPE_ESP_MESSAGE: _ClassVar[UsbPayloadType]
    USB_PAYLOAD_TYPE_COLLECTOR_TO_ESP: _ClassVar[UsbPayloadType]

USB_PAYLOAD_TYPE_UNKNOWN: UsbPayloadType
USB_PAYLOAD_TYPE_ESP_MESSAGE: UsbPayloadType
USB_PAYLOAD_TYPE_COLLECTOR_TO_ESP: UsbPayloadType

class UsbFrame(_message.Message):
    __slots__ = ("version", "payload_type", "seq", "crc32", "payload")
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

    def __init__(
        self,
        version: int | None = ...,
        payload_type: UsbPayloadType | str | None = ...,
        seq: int | None = ...,
        crc32: int | None = ...,
        payload: bytes | None = ...,
    ) -> None: ...
