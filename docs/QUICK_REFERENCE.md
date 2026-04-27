# Quick Reference

## Development (`./dev.sh`)

| Command           | What it does                        |
|-------------------|-------------------------------------|
| `./dev.sh fmt`    | Format code with ruff               |
| `./dev.sh lint`   | Lint and auto-fix with ruff         |
| `./dev.sh vet`    | Type check with mypy                |
| `./dev.sh check`  | Run fmt + lint + vet                |
| `./dev.sh test`   | Run tests                           |
| `./dev.sh proto`  | Generate gRPC code from .proto files|
| `./dev.sh install`| Install all packages (dev deps)     |
| `./dev.sh clean`  | Remove caches and generated files   |

## Stack (`./stack.sh [--prod]`)

Pass `--prod` before any command to target the production stack.

| Command                       | What it does                              |
|-------------------------------|-------------------------------------------|
| `./stack.sh build`            | Build dev images                          |
| `./stack.sh --prod build`     | Pull prod images from registry            |
| `./stack.sh up`               | Start stack with BLE collector            |
| `./stack.sh up-usb`           | Start stack with USB collector            |
| `./stack.sh up-agg`           | Start aggregator + frontend only          |
| `./stack.sh down`             | Stop all services                         |
| `./stack.sh logs`             | Follow logs                               |
| `./stack.sh clean`            | Remove containers and volumes             |
| `./stack.sh sim [args]`       | Run synthetic simulator                   |
| `./stack.sh sim-replay`       | Replay a recorded session                 |
| `./stack.sh sim-sessions`     | List recorded sessions                    |
| `./stack.sh ble-scan`         | Scan for BLE Polar devices                |
| `./stack.sh usb-scan`         | Scan for connected ESP32 devices          |
| `./stack.sh auto-pair`        | Auto-pair ESP32 devices with Polar sensors|

## Simulator options

```bash
./stack.sh sim --devices 5 --collectors 2 --acc --duration 60
./stack.sh sim-replay 3 --speed 2.0 --loop
./stack.sh sim-sessions
```

## Before committing

```bash
./dev.sh check
```
