# ECG-Streaming

## Project: Multi-Device Real-Time ECG Aggregation & Web Visualization

### Objective

Implement a hardware-agnostic real-time signal collection, alignment, and visualization system that can ingest ECG data from 20 Polar H10 chest straps and display synchronized waveforms in a web browser with minimal latency.

The system must:

- Support 20 concurrent BLE devices
- Synchronize data streams into a single timebase
- Expose a browser-based live monitor
- Allow future replacement of hardware (non-Polar devices) without architectural changes

### High-Level Architecture

```
Sensors → Collector Layer → Time Alignment Engine → API Server → Web UI
```

**Key design principles:**

- Time synchronization is centralized
- Device drivers are abstracted
- Visualization is not coupled to the sensor type

## Functional Requirements

### 1. Device Collection Layer

Implement a collector service that:

- Connects to multiple Polar H10 devices over BLE
- Subscribes to ECG and optional accelerometer streams
- Handles >7 devices per BLE adapter (expect multiple USB dongles)
- Allows binding device → adapter mapping
- Exposes a uniform interface:
  ```python
  read() → (device_id, device_timestamp, raw_sample)
  ```

Device driver must implement a base interface to allow replacements (future sensors).

**Technology:**

- Python 3.14
- Virtual environment via `uv venv`
- BLE via `polar-ble-sdk` or `Bleak`
- Linux BlueZ multi-interface support (hci0, hci1, hci2…)

### 2. Time Alignment Engine

Implement a synchronization service that:

- Accepts `(device_timestamp, host_receive_time)` pairs
- Continuously estimates:
  ```
  host_time = drift * device_time + offset
  ```
- Maintains a live regression model per device
- Converts all ECG samples into a global timebase
- Computes reliability/confidence of time correction per device
- Supports dropout detection and reconnection handling

**Optional Phase 2:**

- Implement ECG cross-correlation for fine temporal alignment
- Optional mechanical synchronization event detection (accelerometer spike or ECG artifact)

### 3. Streaming Backend

Implement a backend API service that:

- Buffers the last 30 seconds of synchronized ECG data
- Streams data to browsers via WebSocket at configurable rate (30–60 fps)
- Supports endpoints:
  - `/ws/ecg` — live stream
  - `/devices` — list active devices
  - `/stats` — synchronization error report

**Data format:**

```json
{
  "device_id": "H10_07",
  "global_time": 1716492342.182,
  "raw": 412,
  "confidence": 0.992
}
```

**Technology:**

- Python 3.14
- Virtual environment via `uv venv`
- FastAPI
- WebSockets (native FastAPI)

### 4. Web UI

Implement a browser interface that:

- Shows ECG waveforms in quasi-real-time
- Supports:
  - Multiple streams
  - Device selection
  - Focus view per channel
  - Sliding time window
  - Zoom and pan
- Displays time correction confidence and connectivity
- Does NOT compute timestamps

**Technology:**

- **Framework:** SvelteKit
- **Charting:** Canvas-based rendering (PixiJS, raw Canvas, or WebGL if needed)
- **WebSocket client:** Native browser WebSocket API with SvelteKit stores for state management
- **Styling:** CSS modules or Tailwind CSS (optional)

## Non-Functional Requirements

### Performance

- End-to-end latency < 300 ms
- Minimum refresh rate 20 fps
- Support burst handling
- No frame stall when losing devices

### Maintainability

- Strict separation of:
  - Drivers
  - Sync engine
  - API
  - UI
- Module boundaries enforced
- No hardware-specific assumptions in logic

### Logging & Debugging

**Per-device logs:**

- Offset
- Drift
- Jitter

**CLI debug mode for:**

- Device connection health
- Clock drift

**Visualization diagnostics panel:**

- Dropouts
- Skew
- RMS sync error

## Deliverables

### Mandatory

- Collector daemon
- Synchronization engine
- FastAPI/WebSocket server
- Live web viewer

### Bonus

- Session recording
- Replay UI
- Export tool (CSV / HDF5)
- Interactive R-peak visualizer

## Success Criteria

The project succeeds when:

- ✅ 20 Polar H10s stream simultaneously
- ✅ Data shares a common timebase
- ✅ Browser shows stable ECG across all devices
- ✅ Latency < 300 ms
- ✅ Swapping devices requires only replacing driver module
- ✅ System runs for 30 minutes without instability

## Engineering Constraints

- **Backend Language:** Python 3.14
- **Package Management:** uv (with `uv venv` for virtual environments)
- **Frontend Framework:** SvelteKit
- **Platform:** Linux (Raspberry Pi or PC)
- Backend must run headless
- Deployment script included

## Optional Phase 2 (Future ready)

- Hardware sync sources (research ECG)
- Trigger-based alignment
- Heartbeat-based synchronization
- Offline re-alignment
