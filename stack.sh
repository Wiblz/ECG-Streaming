#!/usr/bin/env bash
# stack.sh — manage the ECG streaming stack and run CLI utilities
# Usage: ./stack.sh [--prod] <command> [args...]

set -euo pipefail

# Parse --prod flag
PROD=false
if [[ "${1:-}" == "--prod" ]]; then
    PROD=true
    shift
fi

cmd="${1:-help}"
shift || true

if $PROD; then
    COMPOSE="docker compose -f docker-compose.prod.yml"
    FRONTEND_URL="http://localhost"
    ENV="prod"
else
    COMPOSE="docker compose"
    FRONTEND_URL="http://localhost:5173"
    ENV="dev"
fi

case "$cmd" in
    build)
        if $PROD; then
            echo "==> Pulling prod Docker images..."
            $COMPOSE pull
        else
            echo "==> Building dev Docker images..."
            $COMPOSE build aggregator frontend
            $COMPOSE build collector-ble collector-usb
            $COMPOSE build simulator
        fi
        echo "==> Done."
        ;;
    up)
        echo "==> Starting $ENV stack (BLE collector)..."
        $COMPOSE --profile ble up -d
        echo "  Frontend:   $FRONTEND_URL"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-usb)
        echo "==> Starting $ENV stack (USB collector)..."
        $COMPOSE --profile usb up -d
        echo "  Frontend:   $FRONTEND_URL"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-agg)
        echo "==> Starting $ENV aggregator + frontend only..."
        $COMPOSE up -d aggregator frontend
        echo "  Frontend:   $FRONTEND_URL"
        echo "  Aggregator: http://localhost:7999"
        ;;
    down)
        echo "==> Stopping $ENV stack..."
        $COMPOSE --profile ble --profile usb --profile simulator down
        ;;
    logs)
        $COMPOSE --profile ble --profile usb --profile simulator logs -f "$@"
        ;;
    clean)
        echo "==> Removing $ENV containers and volumes..."
        $COMPOSE --profile ble --profile usb --profile simulator down -v
        echo "==> Done."
        ;;
    sim)
        echo "==> Running simulator..."
        $COMPOSE run --rm simulator ecg-simulator run "$@"
        ;;
    sim-replay)
        echo "==> Replaying session..."
        $COMPOSE run --rm simulator ecg-simulator replay --db /data/ecg_data.db "$@"
        ;;
    sim-sessions)
        $COMPOSE run --rm simulator ecg-simulator sessions --db /data/ecg_data.db "$@"
        ;;
    ble-scan)
        echo "==> Scanning for BLE Polar devices..."
        $COMPOSE --profile ble run --rm collector-ble ecg-collector ble scan "$@"
        ;;
    usb-scan)
        echo "==> Scanning for ESP32 devices..."
        $COMPOSE --profile usb run --rm collector-usb ecg-collector usb scan "$@"
        ;;
    auto-pair)
        echo "==> Auto-pairing ESP32 devices with Polar sensors..."
        $COMPOSE --profile usb run --rm collector-usb ecg-collector usb auto-pair "$@"
        ;;
    led-identify)
        if [[ $# -lt 1 ]]; then
            echo "Usage: ./stack.sh led-identify <esp-id> [extra args...]" >&2
            exit 2
        fi
        esp_id="$1"
        shift
        echo "==> Triggering LED identify on ESP $esp_id..."
        $COMPOSE --profile usb run --rm collector-usb ecg-collector usb signal --esp-id "$esp_id" "$@"
        ;;
    help|*)
        echo "Usage: ./stack.sh [--prod] <command> [args...]"
        echo ""
        echo "Pass --prod before the command to target the production stack."
        echo ""
        echo "Stack management:"
        echo "  build           Build dev images / pull prod images"
        echo "  up              Start stack with BLE collector"
        echo "  up-usb          Start stack with USB collector"
        echo "  up-agg          Start aggregator + frontend only"
        echo "  down            Stop stack"
        echo "  logs            Follow logs (extra args passed to docker compose logs)"
        echo "  clean           Stop stack and remove containers and volumes"
        echo ""
        echo "Simulator (dev only):"
        echo "  sim [args]           Run synthetic simulator"
        echo "  sim-replay [args]    Replay a recorded session"
        echo "  sim-sessions [args]  List recorded sessions"
        echo ""
        echo "Device utilities:"
        echo "  ble-scan [args]              Scan for BLE Polar devices"
        echo "  usb-scan [args]              Scan for connected ESP32 devices"
        echo "  auto-pair [args]             Auto-pair ESP32 devices with Polar sensors"
        echo "  led-identify <esp-id> [args] Cycle the LED on the given ESP32 to locate it physically"
        ;;
esac
