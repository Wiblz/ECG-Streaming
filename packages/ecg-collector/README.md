# ECG-Collector

Collector module for ECG-Streaming project. Connects to multiple Polar H10 devices via Bluetooth LE, timestamps samples, and streams data to the aggregator via gRPC.

## Features

- Multi-device Polar H10 BLE connection
- Concurrent device management across multiple BLE adapters
- High-performance gRPC streaming to aggregator
- Real-time sample timestamping
- Device status monitoring

## Installation

```bash
pip install -e packages/ecg-collector
```

## Usage

### Start Collector

```bash
ecg-collector
```

### CLI Tools

```bash
# Scan for nearby Polar devices
ecg-collector-cli scan

# Test connection to a device
ecg-collector-cli test-connection <device_id>

# Monitor adapter statistics
ecg-collector-cli adapter-stats
```

## Configuration

See `packages/ecg-collector/config.example.yaml` for configuration options. Default config path is `packages/ecg-collector/config.yaml`.

- `device_ids`: List of Polar H10 device IDs to connect to
- `ble`: BLE adapter settings
- `aggregator`: Aggregator connection settings (host, port)
- `logging`: Logging configuration
- `usb`: USB settings (autodiscover, devices, allowlist, device_map, persist_config)
  - `usb.device_map` uses ESP IDs reported over USB to assign a target Polar device ID.
  - Provisioning is required before the ESP will start scanning for a Polar device.
