# ECG-Simulator

Synthetic collector simulator for the ECG-Streaming stack.

This package acts like one or more mock collectors and streams synthetic ECG and
optional accelerometer data to the real aggregator over the existing gRPC
interface. It is intended for stress-testing the aggregator and frontend without
requiring physical devices.

## Install

```bash
uv pip install -e packages/ecg-common
uv pip install -e packages/ecg-simulator
```

## Usage

```bash
ecg-simulator run --devices 24 --collectors 2 --acc
```

Useful options:

- `--devices`: total number of simulated devices
- `--collectors`: number of simulated collectors
- `--ecg-rate`: ECG sample rate per device
- `--acc-rate`: accelerometer sample rate per device (default `100`)
- `--batch-size`: samples per outbound gRPC batch
- `--acc`: enable accelerometer streaming
- `--duration`: stop automatically after N seconds

By default the simulator connects to `localhost:50051`, which matches the
aggregator gRPC default.
