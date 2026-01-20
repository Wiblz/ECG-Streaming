# ECG-Streaming

Multi-Device Real-Time ECG Aggregation & Web Visualization System

A distributed system for collecting, synchronizing, and visualizing ECG data from up to 20 Polar H10 chest straps with minimal latency.

## Architecture Overview

The system is split into two main modules that can run independently:

```
┌─────────────────────┐         ┌─────────────────────────────────┐
│   ECG COLLECTOR     │         │   ECG AGGREGATOR + DASHBOARD    │
│                     │         │                                 │
│  ┌───────────────┐  │         │  ┌──────────────────────────┐   │
│  │ Polar H10     │  │  gRPC   │  │  gRPC Server             │   │
│  │ BLE Drivers   │──┼────────▶│  │  (receives data)         │   │
│  └───────────────┘  │         │  └──────────────────────────┘   │
│  ┌───────────────┐  │         │  ┌──────────────────────────┐   │
│  │ Adapter       │  │         │  │  Time Alignment Engine   │   │
│  │ Manager       │  │         │  │  (sync timestamps)       │   │
│  └───────────────┘  │         │  └──────────────────────────┘   │
│  ┌───────────────┐  │         │  ┌──────────────────────────┐   │
│  │ gRPC Client   │  │         │  │  SQLite Database         │   │
│  └───────────────┘  │         │  │  (persistence)           │   │
│                     │         │  └──────────────────────────┘   │
└─────────────────────┘         │  ┌──────────────────────────┐   │
                                │  │  WebSocket API Server    │   │
                                │  │  (dashboard)             │   │
                                │  └──────────────────────────┘   │
                                │              │                  │
                                └──────────────┼──────────────────┘
                                               ▼
                                    ┌──────────────────┐
                                    │  Web Dashboard   │
                                    │  (SvelteKit)     │
                                    └──────────────────┘
```

### Module Separation

**Collector (`ecg-collector`)**:
- Connects to N Polar H10 devices via BLE
- Manages multiple BLE adapters (hci0, hci1, hci2...)
- Timestamps samples at collection time
- Streams data to aggregator via gRPC

**Aggregator (`ecg-aggregator`)**:
- Receives data from multiple collectors
- Performs time alignment and synchronization
- Stores samples in SQLite database
- Serves real-time dashboard via WebSocket
- Provides REST API for metadata

## Quick Start

### Installation

```bash
# Install all packages
uv pip install -e packages/ecg-common
uv pip install -e packages/ecg-collector
uv pip install -e packages/ecg-aggregator
```

### Configuration

```bash
# Copy example configs
cp packages/ecg-collector/config.example.yaml packages/ecg-collector/config.yaml
cp packages/ecg-aggregator/config.example.yaml packages/ecg-aggregator/config.yaml

# Edit configuration
# - Add your Polar H10 device IDs
# - Configure aggregator host/port
nano packages/ecg-collector/config.yaml
nano packages/ecg-aggregator/config.yaml
```

### Running

**Local deployment (single machine):**

```bash
# Terminal 1: Start aggregator
ecg-aggregator

# Terminal 2: Start collector
ecg-collector

# Access dashboard at http://localhost:8000
```

Run these commands from the repo root so the default config paths resolve, or pass `--config` explicitly.

**Distributed deployment:**

```bash
# On server (e.g., 192.168.1.100):
ecg-aggregator

# On edge device(s) with BLE adapters:
# Edit packages/ecg-collector/config.yaml: aggregator.host = "192.168.1.100"
ecg-collector
```

## Project Structure

```
ECG-Streaming/
├── packages/
│   ├── ecg-common/           # Shared models, gRPC protocol, logging
│   │   └── src/ecg_common/
│   │       ├── models.py     # Data models (ECGSample, etc.)
│   │       ├── proto/        # gRPC protocol definitions
│   │       └── logging.py    # Logging utilities
│   │
│   ├── ecg-collector/        # Collector module
│   │   ├── config.example.yaml  # Collector config example
│   │   └── src/ecg_collector/
│   │       ├── collector/    # BLE device drivers
│   │       ├── grpc_client.py  # gRPC client
│   │       ├── config.py     # Configuration
│   │       ├── main.py       # Entry point
│   │       └── cli.py        # CLI utilities
│   │
│   └── ecg-aggregator/       # Aggregator + Dashboard
│       ├── config.example.yaml  # Aggregator config example
│       └── src/ecg_aggregator/
│           ├── grpc_server.py  # gRPC server
│           ├── sync/         # Time alignment engine
│           ├── storage/      # SQLite persistence
│           ├── api/          # WebSocket/REST API
│           ├── config.py     # Configuration
│           └── main.py       # Entry point
└── README.md                 # This file
```

## Features

### Collector Features
- ✅ Multi-device BLE connection (up to 20+ devices)
- ✅ Multiple BLE adapter support
- ✅ Concurrent device management
- ✅ gRPC streaming to aggregator
- ✅ Device status monitoring
- ✅ CLI tools (scan, test-connection)

### Aggregator Features
- ✅ gRPC server for receiving data
- ✅ Time synchronization engine
- ✅ SQLite database persistence
- ✅ WebSocket real-time streaming
- ✅ REST API for metadata
- ✅ Buffer management (30s window)
- ✅ Dashboard web interface

## API Reference

### REST Endpoints (Aggregator)

- `GET /` - Service information
- `GET /devices` - List all devices with sync status
- `GET /stats` - Synchronization and system statistics
- `GET /buffer/stats` - Buffer statistics
- `GET /buffer/latest` - Latest sample per device
- `WS /ws/ecg` - WebSocket for real-time ECG streaming

### CLI Tools

**Collector:**
```bash
# Scan for Polar devices
ecg-collector-cli scan

# Test connection to a device
ecg-collector-cli test-connection "Polar H10 ABC123"
```

## Configuration

See `packages/ecg-collector/config.example.yaml` and `packages/ecg-aggregator/config.example.yaml` for detailed configuration options:

**Collector:**
- `device_ids` - List of Polar H10 device IDs
- `aggregator.host` - Aggregator hostname/IP
- `aggregator.port` - Aggregator gRPC port (default: 50051)

**Aggregator:**
- `grpc.port` - gRPC server port (default: 50051)
- `api.port` - HTTP/WebSocket port (default: 8000)
- `storage.database_path` - SQLite database path

## Deployment Scenarios

### Scenario 1: Single Machine (Development/Testing)
- Run both collector and aggregator on localhost
- Good for development and testing with a few devices

### Scenario 2: Distributed (Edge + Server)
- Collector on edge device with BLE adapters
- Aggregator on server (no BLE hardware required)
- Good for production with many devices

### Scenario 3: Multiple Collectors
- Multiple collectors (different locations/rooms)
- Single aggregator receiving from all
- Each collector manages subset of devices

## System Requirements

- **Backend:** Python 3.14+
- **BLE Support:** Linux with BlueZ (for collector only)
- **Package Manager:** uv
- **Frontend:** SvelteKit (coming soon)
- **Platform:** Linux (Raspberry Pi or PC)

## Performance

- End-to-end latency: < 300 ms
- WebSocket refresh rate: 30 FPS (configurable)
- Supports 20+ concurrent devices
- Stable operation for extended sessions

## Development

```bash
# Install development dependencies
uv pip install -e "packages/ecg-common[dev]"
uv pip install -e "packages/ecg-collector[dev]"
uv pip install -e "packages/ecg-aggregator[dev]"

# Run tests
pytest

# Lint code
ruff check .

# Format code
ruff format .
```

## Troubleshooting

**Collector can't connect to devices:**
- Run `ecg-collector-cli scan` to find device IDs
- Check BlueZ configuration
- Verify BLE adapters with `hciconfig`

**Collector can't connect to aggregator:**
- Check aggregator is running and port is correct
- Verify firewall rules allow gRPC port (50051)
- Check network connectivity

**Poor time synchronization:**
- Increase `aggregator.sync.min_samples`
- Check for network latency issues
- Verify device clocks are stable

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]
