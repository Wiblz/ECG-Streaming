"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings
from . import collector_aggregator_pb2 as collector__aggregator__pb2
GRPC_GENERATED_VERSION = '1.71.2'
GRPC_VERSION = grpc.__version__
_version_not_supported = False
try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True
if _version_not_supported:
    raise RuntimeError(f'The grpc package installed is at version {GRPC_VERSION},' + f' but the generated code in collector_aggregator_pb2_grpc.py depends on' + f' grpcio>={GRPC_GENERATED_VERSION}.' + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}' + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.')

class ECGStreamingServiceStub(object):
    """Collector ↔ Aggregator Communication (gRPC)

    This file defines the gRPC service and messages for communication between
    Collector services and the central Aggregator.

    ============================================================================
    gRPC Service Definition
    ============================================================================

    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.StreamECG = channel.stream_stream('/ecg_streaming.ECGStreamingService/StreamECG', request_serializer=collector__aggregator__pb2.CollectorMessage.SerializeToString, response_deserializer=collector__aggregator__pb2.AggregatorMessage.FromString, _registered_method=True)

class ECGStreamingServiceServicer(object):
    """Collector ↔ Aggregator Communication (gRPC)

    This file defines the gRPC service and messages for communication between
    Collector services and the central Aggregator.

    ============================================================================
    gRPC Service Definition
    ============================================================================

    """

    def StreamECG(self, request_iterator, context):
        """Bidirectional streaming between Collector and Aggregator
        Client (collector) sends samples and status updates
        Server (aggregator) sends sync status and control commands
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

def add_ECGStreamingServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {'StreamECG': grpc.stream_stream_rpc_method_handler(servicer.StreamECG, request_deserializer=collector__aggregator__pb2.CollectorMessage.FromString, response_serializer=collector__aggregator__pb2.AggregatorMessage.SerializeToString)}
    generic_handler = grpc.method_handlers_generic_handler('ecg_streaming.ECGStreamingService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('ecg_streaming.ECGStreamingService', rpc_method_handlers)

class ECGStreamingService(object):
    """Collector ↔ Aggregator Communication (gRPC)

    This file defines the gRPC service and messages for communication between
    Collector services and the central Aggregator.

    ============================================================================
    gRPC Service Definition
    ============================================================================

    """

    @staticmethod
    def StreamECG(request_iterator, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.stream_stream(request_iterator, target, '/ecg_streaming.ECGStreamingService/StreamECG', collector__aggregator__pb2.CollectorMessage.SerializeToString, collector__aggregator__pb2.AggregatorMessage.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)