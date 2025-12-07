# ECG-Aggregator

Aggregator + Dashboard module for ECG-Streaming project. Receives ECG data from collectors via gRPC, performs time alignment and synchronization, stores data in SQLite database, and serves a real-time web dashboard and REST API.

## Features

- **gRPC Server**: Receives ECG data from multiple collectors
- **Time Synchronization**: Aligns timestamps from multiple devices to global time
- **Database Storage**: SQLite persistence for all ECG samples
- **Real-time Dashboard**: WebSocket streaming for live ECG visualization
- **REST API**: Metadata and device status endpoints
- **Buffer Management**: Circular buffer for recent samples

## Installation

```bash
pip install -e packages/ecg-aggregator
```

## Usage

### Start Aggregator

```bash
ecg-aggregator --config config.yaml
```

The aggregator will:
1. Start gRPC server (default port: 50051) to receive data from collectors
2. Start HTTP/WebSocket API server (default port: 8000) for the dashboard
3. Collect and synchronize ECG data from all connected collectors
4. Store data in SQLite database (`ecg_data.db`)
5. Stream real-time data to connected web clients

### API Endpoints

- `GET /` - Service information
- `GET /devices` - List all devices with sync status
- `GET /stats` - Synchronization and system statistics
- `GET /buffer/stats` - Buffer statistics
- `GET /buffer/latest` - Latest sample per device
- `WS /ws/ecg` - WebSocket for real-time ECG streaming

## Configuration

See `config.example.yaml` for configuration options:

- `aggregator.grpc_port`: gRPC server port for collectors
- `aggregator.api_port`: HTTP/WebSocket server port for dashboard
- `sync`: Time synchronization settings
- `storage`: Database settings
- `api`: API server settings
- `logging`: Logging configuration

## Architecture

```
Collectors (gRPC clients)
    ↓
gRPC Server (port 50051)
    ↓
Time Alignment Service
    ↓
Database + Buffer
    ↓
WebSocket/REST API (port 8000)
    ↓
Web Dashboard (browsers)
```
