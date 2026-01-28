"""gRPC protocol definitions for ECG-Streaming."""

# Auto-generated protocol buffer modules
# Generated from .proto files in this directory

# Common types (shared across all protocols)
# USB transport layer (ESP32 <-> Collector framing)
# ESP32 <-> Collector communication
# Collector <-> Aggregator communication (gRPC)
from ecg_common.proto import (
    collector_aggregator_pb2,
    collector_aggregator_pb2_grpc,
    common_pb2,
    esp_collector_pb2,
    usb_transport_pb2,
)

__all__ = [
    # Common
    "common_pb2",
    # USB Transport
    "usb_transport_pb2",
    # ESP-Collector
    "esp_collector_pb2",
    # Collector-Aggregator
    "collector_aggregator_pb2",
    "collector_aggregator_pb2_grpc",
]
