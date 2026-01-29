"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 0, '', 'collector_aggregator.proto')
_sym_db = _symbol_database.Default()
from . import common_pb2 as common__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1acollector_aggregator.proto\x12\recg_streaming\x1a\x0ccommon.proto"\xb5\x02\n\x10CollectorMessage\x12<\n\x0cregistration\x18\x01 \x01(\x0b2$.ecg_streaming.CollectorRegistrationH\x00\x12,\n\tecg_batch\x18\x02 \x01(\x0b2\x17.ecg_streaming.ECGBatchH\x00\x126\n\tacc_batch\x18\x03 \x01(\x0b2!.ecg_streaming.AccelerometerBatchH\x00\x12:\n\rstatus_update\x18\x04 \x01(\x0b2!.ecg_streaming.DeviceStatusUpdateH\x00\x126\n\theartbeat\x18\x05 \x01(\x0b2!.ecg_streaming.CollectorHeartbeatH\x00B\t\n\x07message"\xdf\x01\n\x15CollectorRegistration\x12\x14\n\x0ccollector_id\x18\x01 \x01(\t\x12\x12\n\ndevice_ids\x18\x02 \x03(\t\x12\x0f\n\x07version\x18\x03 \x01(\t\x12D\n\x08metadata\x18\x04 \x03(\x0b22.ecg_streaming.CollectorRegistration.MetadataEntry\x12\x14\n\x0cdisplay_name\x18\x05 \x01(\t\x1a/\n\rMetadataEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01"\x90\x01\n\x08ECGBatch\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12\x15\n\rwall_clock_us\x18\x02 \x01(\x04\x12\x1a\n\x12batch_timestamp_us\x18\x03 \x01(\x04\x12\x13\n\x0bsample_rate\x18\x04 \x01(\x05\x12)\n\x07samples\x18\x05 \x03(\x0b2\x18.ecg_streaming.ECGSample"\xa4\x01\n\x12AccelerometerBatch\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12\x15\n\rwall_clock_us\x18\x02 \x01(\x04\x12\x1a\n\x12batch_timestamp_us\x18\x03 \x01(\x04\x12\x13\n\x0bsample_rate\x18\x04 \x01(\x05\x123\n\x07samples\x18\x05 \x03(\x0b2".ecg_streaming.AccelerometerSample"\xab\x02\n\x12DeviceStatusUpdate\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12+\n\x06status\x18\x02 \x01(\x0e2\x1b.ecg_streaming.DeviceStatus\x12\x1a\n\rbattery_level\x18\x03 \x01(\x05H\x00\x88\x01\x01\x12\x1a\n\rerror_message\x18\x04 \x01(\tH\x01\x88\x01\x01\x12F\n\x0bdevice_info\x18\x05 \x03(\x0b21.ecg_streaming.DeviceStatusUpdate.DeviceInfoEntry\x1a1\n\x0fDeviceInfoEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01B\x10\n\x0e_battery_levelB\x10\n\x0e_error_message"X\n\x12CollectorHeartbeat\x12\x14\n\x0ctimestamp_ms\x18\x01 \x01(\x03\x12\x14\n\x0csamples_sent\x18\x02 \x01(\x05\x12\x16\n\x0eactive_devices\x18\x03 \x01(\x05"\x92\x01\n\x11AggregatorMessage\x12:\n\x10registration_ack\x18\x01 \x01(\x0b2\x1e.ecg_streaming.RegistrationAckH\x00\x126\n\x0bsync_status\x18\x02 \x01(\x0b2\x1f.ecg_streaming.SyncStatusUpdateH\x00B\t\n\x07message"L\n\x0fRegistrationAck\x12\x10\n\x08accepted\x18\x01 \x01(\x08\x12\x0f\n\x07message\x18\x02 \x01(\t\x12\x16\n\x0eserver_time_ms\x18\x03 \x01(\x03"w\n\x10SyncStatusUpdate\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12\x12\n\nsync_ready\x18\x02 \x01(\x08\x12\x10\n\x08offset_s\x18\x03 \x01(\x01\x12\x16\n\x0eoffset_version\x18\x04 \x01(\x05\x12\x12\n\nconfidence\x18\x05 \x01(\x012i\n\x13ECGStreamingService\x12R\n\tStreamECG\x12\x1f.ecg_streaming.CollectorMessage\x1a .ecg_streaming.AggregatorMessage(\x010\x01b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'collector_aggregator_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_COLLECTORREGISTRATION_METADATAENTRY']._loaded_options = None
    _globals['_COLLECTORREGISTRATION_METADATAENTRY']._serialized_options = b'8\x01'
    _globals['_DEVICESTATUSUPDATE_DEVICEINFOENTRY']._loaded_options = None
    _globals['_DEVICESTATUSUPDATE_DEVICEINFOENTRY']._serialized_options = b'8\x01'
    _globals['_COLLECTORMESSAGE']._serialized_start = 60
    _globals['_COLLECTORMESSAGE']._serialized_end = 369
    _globals['_COLLECTORREGISTRATION']._serialized_start = 372
    _globals['_COLLECTORREGISTRATION']._serialized_end = 595
    _globals['_COLLECTORREGISTRATION_METADATAENTRY']._serialized_start = 548
    _globals['_COLLECTORREGISTRATION_METADATAENTRY']._serialized_end = 595
    _globals['_ECGBATCH']._serialized_start = 598
    _globals['_ECGBATCH']._serialized_end = 742
    _globals['_ACCELEROMETERBATCH']._serialized_start = 745
    _globals['_ACCELEROMETERBATCH']._serialized_end = 909
    _globals['_DEVICESTATUSUPDATE']._serialized_start = 912
    _globals['_DEVICESTATUSUPDATE']._serialized_end = 1211
    _globals['_DEVICESTATUSUPDATE_DEVICEINFOENTRY']._serialized_start = 1126
    _globals['_DEVICESTATUSUPDATE_DEVICEINFOENTRY']._serialized_end = 1175
    _globals['_COLLECTORHEARTBEAT']._serialized_start = 1213
    _globals['_COLLECTORHEARTBEAT']._serialized_end = 1301
    _globals['_AGGREGATORMESSAGE']._serialized_start = 1304
    _globals['_AGGREGATORMESSAGE']._serialized_end = 1450
    _globals['_REGISTRATIONACK']._serialized_start = 1452
    _globals['_REGISTRATIONACK']._serialized_end = 1528
    _globals['_SYNCSTATUSUPDATE']._serialized_start = 1530
    _globals['_SYNCSTATUSUPDATE']._serialized_end = 1649
    _globals['_ECGSTREAMINGSERVICE']._serialized_start = 1651
    _globals['_ECGSTREAMINGSERVICE']._serialized_end = 1756