# Docker Quick Start

## TL;DR

```bash
# 1. Copy and edit config
cp config/collector.yaml.example config/collector.yaml
vim config/collector.yaml  # Add your device IDs

# 2. Build images
./stack.sh build

# 3. Start with USB collector
./stack.sh up-usb

# OR start with BLE collector
./stack.sh up

# 4. Open browser
open http://localhost:5173

# 5. View logs
./stack.sh logs

# 6. Stop
./stack.sh down
```

## What Gets Started

| Service                                | Port  | Description                                 |
|----------------------------------------|-------|---------------------------------------------|
| **aggregator**                         | 7999  | gRPC server, stores data in SQLite          |
| **collector-ble** or **collector-usb** | -     | Connects to Polar H10 (BLE) or ESP32 (USB)  |
| **frontend**                           | 5173  | Web UI for visualization                    |

## Configuration

Edit `config/collector.yaml` with your device IDs. See `config/collector.yaml.example` for the full structure.

```yaml
# IMPORTANT: Use container name for Docker networking
aggregator:
  host: "aggregator"  # NOT "localhost"!
  port: 50051
```

## BLE vs USB Mode

### BLE Mode

**When to use**: Connecting directly to Polar H10 devices via Bluetooth

**Requirements**:
- Bluetooth adapter on host
- Privileged Docker access

```bash
./stack.sh up
```

### USB Mode

**When to use**: Using ESP32 devices connected via USB

**Requirements**:
- ESP32 devices at `/dev/ttyACM*` or `/dev/ttyUSB*`
- User in `dialout` group: `sudo usermod -a -G dialout $USER`

```bash
./stack.sh up-usb
```

## Device Utilities

```bash
# Scan for BLE Polar devices
./stack.sh ble-scan

# Scan for connected ESP32 devices
./stack.sh usb-scan

# Auto-pair ESP32 devices with Polar sensors
./stack.sh auto-pair
```

## Simulator

Run a synthetic data stream against the aggregator (useful for testing without hardware):

```bash
# Start aggregator first
./stack.sh up-agg

# Run simulator with defaults (20 devices, 1 collector)
./stack.sh sim

# Pass arguments directly
./stack.sh sim --devices 5 --collectors 2 --acc

# List recorded sessions
./stack.sh sim-sessions

# Replay a session
./stack.sh sim-replay 3
```

## Production Stack

Pass `--prod` before any command to use production images from the registry:

```bash
# Pull images
./stack.sh --prod build

# Start
./stack.sh --prod up-agg
./stack.sh --prod up-usb

# Stop
./stack.sh --prod down
```

Requires a `.env` file with:
```
GITHUB_REPOSITORY_OWNER=your-username-lowercase
IMAGE_TAG=latest
```

## Common Issues

### "Cannot access Bluetooth"
```bash
sudo systemctl status bluetooth
hciconfig
```

### "Cannot open /dev/ttyACM0"
```bash
sudo usermod -a -G dialout $USER
newgrp dialout
ls -la /dev/ttyACM*
```

### "Collector cannot connect to aggregator"
Verify config uses the container name:
```yaml
aggregator:
  host: "aggregator"  # ✓ Correct
  # host: "localhost" # ✗ Wrong in Docker
```

### "Database locked"
```bash
./stack.sh down
./stack.sh up-usb
```

## Data Persistence

The database is stored in `./data/ecg_data.db` (bind-mounted into the container).

**Backup**:
```bash
cp data/ecg_data.db data/ecg_data_backup_$(date +%Y%m%d_%H%M%S).db
```

## Development Tips

### Rebuild After Code Changes
```bash
./stack.sh build
./stack.sh up-usb
```

### View Specific Service Logs
```bash
docker compose logs -f aggregator
docker compose logs -f collector-usb
docker compose logs -f frontend
```

### Shell into Container
```bash
docker exec -it ecg-aggregator bash
docker exec -it ecg-collector-usb bash
```

### Check Service Health
```bash
docker compose ps
```

## Architecture

```
Browser ──▶ Frontend:5173 ──▶ Aggregator:7999 ──▶ SQLite DB
                                    ▲
                                    │
                               Collector
                                 ▲  ▲
                                 │  │
                          BLE────┘  └────USB
                      (Polar H10)    (ESP32)
```
