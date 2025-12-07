"""Generated protocol buffer code."""

from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC, 5, 29, 0, "", "proto/ecg_streaming.proto"
)
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x19proto/ecg_streaming.proto\x12\recg_streaming"\x86\x02\n\x10CollectorMessage\x12<\n\x0cregistration\x18\x01 \x01(\x0b2$.ecg_streaming.CollectorRegistrationH\x00\x125\n\x0csample_batch\x18\x02 \x01(\x0b2\x1d.ecg_streaming.ECGSampleBatchH\x00\x12:\n\rstatus_update\x18\x03 \x01(\x0b2!.ecg_streaming.DeviceStatusUpdateH\x00\x126\n\theartbeat\x18\x04 \x01(\x0b2!.ecg_streaming.CollectorHeartbeatH\x00B\t\n\x07message"\xc4\x01\n\x11AggregatorMessage\x12:\n\x10registration_ack\x18\x01 \x01(\x0b2\x1e.ecg_streaming.RegistrationAckH\x00\x126\n\x0bsync_status\x18\x02 \x01(\x0b2\x1f.ecg_streaming.SyncStatusUpdateH\x00\x120\n\x07control\x18\x03 \x01(\x0b2\x1d.ecg_streaming.ControlCommandH\x00B\t\n\x07message"\xc9\x01\n\x15CollectorRegistration\x12\x14\n\x0ccollector_id\x18\x01 \x01(\t\x12\x12\n\ndevice_ids\x18\x02 \x03(\t\x12\x0f\n\x07version\x18\x03 \x01(\t\x12D\n\x08metadata\x18\x04 \x03(\x0b22.ecg_streaming.CollectorRegistration.MetadataEntry\x1a/\n\rMetadataEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01"L\n\x0fRegistrationAck\x12\x10\n\x08accepted\x18\x01 \x01(\x08\x12\x0f\n\x07message\x18\x02 \x01(\t\x12\x16\n\x0eserver_time_ms\x18\x03 \x01(\x03"j\n\x0eECGSampleBatch\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12)\n\x07samples\x18\x02 \x03(\x0b2\x18.ecg_streaming.ECGSample\x12\x1a\n\x12batch_timestamp_ms\x18\x03 \x01(\x03"m\n\tECGSample\x12\x1b\n\x13device_timestamp_us\x18\x01 \x01(\x01\x12\x1b\n\x13host_receive_time_s\x18\x02 \x01(\x01\x12\x11\n\traw_value\x18\x03 \x01(\x05\x12\x13\n\x0bsample_rate\x18\x04 \x01(\x05"\xab\x02\n\x12DeviceStatusUpdate\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12+\n\x06status\x18\x02 \x01(\x0e2\x1b.ecg_streaming.DeviceStatus\x12\x1a\n\rbattery_level\x18\x03 \x01(\x05H\x00\x88\x01\x01\x12\x1a\n\rerror_message\x18\x04 \x01(\tH\x01\x88\x01\x01\x12F\n\x0bdevice_info\x18\x05 \x03(\x0b21.ecg_streaming.DeviceStatusUpdate.DeviceInfoEntry\x1a1\n\x0fDeviceInfoEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01B\x10\n\x0e_battery_levelB\x10\n\x0e_error_message"X\n\x12CollectorHeartbeat\x12\x14\n\x0ctimestamp_ms\x18\x01 \x01(\x03\x12\x14\n\x0csamples_sent\x18\x02 \x01(\x05\x12\x16\n\x0eactive_devices\x18\x03 \x01(\x05"w\n\x10SyncStatusUpdate\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12\x12\n\nsync_ready\x18\x02 \x01(\x08\x12\x10\n\x08offset_s\x18\x03 \x01(\x01\x12\x16\n\x0eoffset_version\x18\x04 \x01(\x05\x12\x12\n\nconfidence\x18\x05 \x01(\x01"\x8e\x03\n\x0eControlCommand\x12:\n\x07command\x18\x01 \x01(\x0e2).ecg_streaming.ControlCommand.CommandType\x12\x16\n\tdevice_id\x18\x02 \x01(\tH\x00\x88\x01\x01\x12A\n\nparameters\x18\x03 \x03(\x0b2-.ecg_streaming.ControlCommand.ParametersEntry\x1a1\n\x0fParametersEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01"\xa3\x01\n\x0bCommandType\x12\x18\n\x14COMMAND_TYPE_UNKNOWN\x10\x00\x12\x1d\n\x19COMMAND_TYPE_START_DEVICE\x10\x01\x12\x1c\n\x18COMMAND_TYPE_STOP_DEVICE\x10\x02\x12"\n\x1eCOMMAND_TYPE_DISCONNECT_DEVICE\x10\x03\x12\x19\n\x15COMMAND_TYPE_SHUTDOWN\x10\x04B\x0c\n\n_device_id*\xba\x01\n\x0cDeviceStatus\x12\x19\n\x15DEVICE_STATUS_UNKNOWN\x10\x00\x12\x1e\n\x1aDEVICE_STATUS_DISCONNECTED\x10\x01\x12\x1c\n\x18DEVICE_STATUS_CONNECTING\x10\x02\x12\x1b\n\x17DEVICE_STATUS_CONNECTED\x10\x03\x12\x1b\n\x17DEVICE_STATUS_STREAMING\x10\x04\x12\x17\n\x13DEVICE_STATUS_ERROR\x10\x052i\n\x13ECGStreamingService\x12R\n\tStreamECG\x12\x1f.ecg_streaming.CollectorMessage\x1a .ecg_streaming.AggregatorMessage(\x010\x01b\x06proto3'
)
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "proto.ecg_streaming_pb2", _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals["_COLLECTORREGISTRATION_METADATAENTRY"]._loaded_options = None
    _globals["_COLLECTORREGISTRATION_METADATAENTRY"]._serialized_options = b"8\x01"
    _globals["_DEVICESTATUSUPDATE_DEVICEINFOENTRY"]._loaded_options = None
    _globals["_DEVICESTATUSUPDATE_DEVICEINFOENTRY"]._serialized_options = b"8\x01"
    _globals["_CONTROLCOMMAND_PARAMETERSENTRY"]._loaded_options = None
    _globals["_CONTROLCOMMAND_PARAMETERSENTRY"]._serialized_options = b"8\x01"
    _globals["_DEVICESTATUS"]._serialized_start = 1924
    _globals["_DEVICESTATUS"]._serialized_end = 2110
    _globals["_COLLECTORMESSAGE"]._serialized_start = 45
    _globals["_COLLECTORMESSAGE"]._serialized_end = 307
    _globals["_AGGREGATORMESSAGE"]._serialized_start = 310
    _globals["_AGGREGATORMESSAGE"]._serialized_end = 506
    _globals["_COLLECTORREGISTRATION"]._serialized_start = 509
    _globals["_COLLECTORREGISTRATION"]._serialized_end = 710
    _globals["_COLLECTORREGISTRATION_METADATAENTRY"]._serialized_start = 663
    _globals["_COLLECTORREGISTRATION_METADATAENTRY"]._serialized_end = 710
    _globals["_REGISTRATIONACK"]._serialized_start = 712
    _globals["_REGISTRATIONACK"]._serialized_end = 788
    _globals["_ECGSAMPLEBATCH"]._serialized_start = 790
    _globals["_ECGSAMPLEBATCH"]._serialized_end = 896
    _globals["_ECGSAMPLE"]._serialized_start = 898
    _globals["_ECGSAMPLE"]._serialized_end = 1007
    _globals["_DEVICESTATUSUPDATE"]._serialized_start = 1010
    _globals["_DEVICESTATUSUPDATE"]._serialized_end = 1309
    _globals["_DEVICESTATUSUPDATE_DEVICEINFOENTRY"]._serialized_start = 1224
    _globals["_DEVICESTATUSUPDATE_DEVICEINFOENTRY"]._serialized_end = 1273
    _globals["_COLLECTORHEARTBEAT"]._serialized_start = 1311
    _globals["_COLLECTORHEARTBEAT"]._serialized_end = 1399
    _globals["_SYNCSTATUSUPDATE"]._serialized_start = 1401
    _globals["_SYNCSTATUSUPDATE"]._serialized_end = 1520
    _globals["_CONTROLCOMMAND"]._serialized_start = 1523
    _globals["_CONTROLCOMMAND"]._serialized_end = 1921
    _globals["_CONTROLCOMMAND_PARAMETERSENTRY"]._serialized_start = 1692
    _globals["_CONTROLCOMMAND_PARAMETERSENTRY"]._serialized_end = 1741
    _globals["_CONTROLCOMMAND_COMMANDTYPE"]._serialized_start = 1744
    _globals["_CONTROLCOMMAND_COMMANDTYPE"]._serialized_end = 1907
    _globals["_ECGSTREAMINGSERVICE"]._serialized_start = 2112
    _globals["_ECGSTREAMINGSERVICE"]._serialized_end = 2217
