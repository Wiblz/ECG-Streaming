"""Client and server classes corresponding to protobuf-defined services."""

import grpc
import warnings
from ..proto import ecg_streaming_pb2 as proto_dot_ecg__streaming__pb2

GRPC_GENERATED_VERSION = "1.71.2"
GRPC_VERSION = grpc.__version__
_version_not_supported = False
try:
    from grpc._utilities import first_version_is_lower

    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True
if _version_not_supported:
    raise RuntimeError(
        f"The grpc package installed is at version {GRPC_VERSION},"
        + f" but the generated code in proto/ecg_streaming_pb2_grpc.py depends on"
        + f" grpcio>={GRPC_GENERATED_VERSION}."
        + f" Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}"
        + f" or downgrade your generated code using grpcio-tools<={GRPC_VERSION}."
    )


class ECGStreamingServiceStub(object):
    """ECG Streaming Service
    Bidirectional streaming between Collector and Aggregator
    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.StreamECG = channel.stream_stream(
            "/ecg_streaming.ECGStreamingService/StreamECG",
            request_serializer=proto_dot_ecg__streaming__pb2.CollectorMessage.SerializeToString,
            response_deserializer=proto_dot_ecg__streaming__pb2.AggregatorMessage.FromString,
            _registered_method=True,
        )


class ECGStreamingServiceServicer(object):
    """ECG Streaming Service
    Bidirectional streaming between Collector and Aggregator
    """

    def StreamECG(self, request_iterator, context):
        """Stream ECG data from collectors to aggregator
        Client (collector) sends samples, server (aggregator) sends control messages
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


def add_ECGStreamingServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
        "StreamECG": grpc.stream_stream_rpc_method_handler(
            servicer.StreamECG,
            request_deserializer=proto_dot_ecg__streaming__pb2.CollectorMessage.FromString,
            response_serializer=proto_dot_ecg__streaming__pb2.AggregatorMessage.SerializeToString,
        )
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "ecg_streaming.ECGStreamingService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers("ecg_streaming.ECGStreamingService", rpc_method_handlers)


class ECGStreamingService(object):
    """ECG Streaming Service
    Bidirectional streaming between Collector and Aggregator
    """

    @staticmethod
    def StreamECG(
        request_iterator,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.stream_stream(
            request_iterator,
            target,
            "/ecg_streaming.ECGStreamingService/StreamECG",
            proto_dot_ecg__streaming__pb2.CollectorMessage.SerializeToString,
            proto_dot_ecg__streaming__pb2.AggregatorMessage.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True,
        )
