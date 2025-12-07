# ECG-Common

Shared models, gRPC protocols, and utilities for the ECG-Streaming project.

## Contents

- **models.py**: Data classes (ECGSample, AccelerometerSample, DeviceStatus)
- **proto/**: gRPC protocol definitions (.proto files and generated Python code)
- **logging.py**: Shared logging configuration
- **config.py**: Common configuration utilities

## Installation

```bash
pip install -e packages/ecg-common
```

## Usage

```python
from ecg_common.models import ECGSample, DeviceStatus
from ecg_common.proto import ecg_pb2, ecg_pb2_grpc
```
