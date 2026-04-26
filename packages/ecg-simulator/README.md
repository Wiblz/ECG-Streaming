# ECG-Simulator

Synthetic collector simulator for the ECG-Streaming stack.

The simulator acts as one or more mock collectors and streams data to the
aggregator over the existing gRPC interface. It supports two modes:

- **Synthetic** — mathematically generated ECG and accelerometer waveforms,
  useful for stress-testing and frontend development without physical devices.
- **Replay** — re-emits a previously recorded session directly from the
  aggregator's SQLite database at the original timing (or a configurable speed
  multiplier), useful for realistic end-to-end testing.

## Install

Via Docker (recommended — no local install needed):

```bash
./stack.sh sim --devices 5 --collectors 2
```

Natively:

```bash
uv pip install -e packages/ecg-common
uv pip install -e packages/ecg-simulator
```

Or from the workspace root:

```bash
./dev.sh install
```

## Commands

### `run` — synthetic streaming

```bash
ecg-simulator run --devices 24 --collectors 2 --acc
```

| Option                 | Default     | Description                                  |
|------------------------|-------------|----------------------------------------------|
| `--host`               | `127.0.0.1` | Aggregator host                              |
| `--port`               | `50051`     | Aggregator gRPC port                         |
| `--devices`            | `20`        | Total simulated devices                      |
| `--collectors`         | `1`         | Number of simulated collectors               |
| `--ecg-rate`           | `130`       | ECG sample rate per device (Hz)              |
| `--acc-rate`           | `100`       | Accelerometer sample rate per device (Hz)    |
| `--batch-size`         | `13`        | Samples per outbound gRPC batch              |
| `--acc`                | off         | Enable accelerometer streaming               |
| `--duration`           | —           | Auto-stop after N seconds                    |
| `--startup-stagger-ms` | `50`        | Delay between initial device status messages |
| `--verbose-sync`       | off         | Print per-device sync-ready events           |

### `sessions` — list recorded sessions

```bash
ecg-simulator sessions --db ecg_data.db
```

Lists all sessions stored in the aggregator database, with ID, start time,
duration, device count, and sample count. Use the session ID with `replay`.

### `replay` — replay a recorded session

```bash
ecg-simulator replay 3 --db ecg_data.db
```

Loads session 3 from the database and re-emits it through the gRPC pipeline
at real-time speed. The original device IDs and nicknames are preserved.

| Option         | Default       | Description                        |
|----------------|---------------|------------------------------------|
| `--db`         | `ecg_data.db` | Path to aggregator SQLite database |
| `--host`       | `127.0.0.1`   | Aggregator host                    |
| `--port`       | `50051`       | Aggregator gRPC port               |
| `--speed`      | `1.0`         | Playback speed multiplier          |
| `--batch-size` | `13`          | Samples per outbound gRPC batch    |
| `--loop`       | off           | Restart the session when it ends   |
| `--duration`   | —             | Auto-stop after N seconds          |
