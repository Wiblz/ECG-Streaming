#!/usr/bin/env bash
# stack.sh — manage the ECG streaming stack and run CLI utilities
# Usage: ./stack.sh <command> [args...]

set -euo pipefail

cmd="${1:-help}"
shift || true

case "$cmd" in
    build)
        echo "==> Building Docker images..."
        docker compose build aggregator frontend
        docker compose build collector-ble collector-usb
        docker compose build simulator
        echo "==> Done."
        ;;
    up)
        echo "==> Starting stack (BLE collector)..."
        docker compose --profile ble up -d
        echo "  Frontend:   http://localhost:5173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-usb)
        echo "==> Starting stack (USB collector)..."
        docker compose --profile usb up -d
        echo "  Frontend:   http://localhost:5173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-agg)
        echo "==> Starting aggregator + frontend only..."
        docker compose up -d aggregator frontend
        echo "  Frontend:   http://localhost:5173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    down)
        echo "==> Stopping stack..."
        docker compose --profile ble --profile usb --profile simulator down
        ;;
    logs)
        docker compose --profile ble --profile usb --profile simulator logs -f "$@"
        ;;
    clean)
        echo "==> Removing containers and volumes..."
        docker compose --profile ble --profile usb --profile simulator down -v
        echo "==> Done."
        ;;
    sim)
        echo "==> Running simulator..."
        docker compose run --rm simulator ecg-simulator run "$@"
        ;;
    sim-replay)
        echo "==> Replaying session..."
        docker compose run --rm simulator ecg-simulator replay --db /data/ecg_data.db "$@"
        ;;
    sim-sessions)
        docker compose run --rm simulator ecg-simulator sessions --db /data/ecg_data.db "$@"
        ;;
    usb-scan)
        echo "==> Scanning for ESP32 devices..."
        docker compose run --rm collector-usb ecg-collector usb scan "$@"
        ;;
    auto-pair)
        echo "==> Auto-pairing ESP32 devices with Polar sensors..."
        docker compose run --rm collector-usb ecg-collector usb auto-pair "$@"
        ;;
    help|*)
        echo "Usage: ./stack.sh <command> [args...]"
        echo ""
        echo "Stack management:"
        echo "  build       Build all Docker images"
        echo "  up          Start stack with BLE collector"
        echo "  up-usb      Start stack with USB collector"
        echo "  up-agg      Start aggregator + frontend only"
        echo "  down        Stop all services"
        echo "  logs        Follow logs (extra args passed to docker compose logs)"
        echo "  clean       Stop and remove containers and volumes"
        echo ""
        echo "Simulator:"
        echo "  sim [args]           Run synthetic simulator (args passed to ecg-simulator run)"
        echo "  sim-replay [args]    Replay a recorded session"
        echo "  sim-sessions [args]  List recorded sessions"
        echo ""
        echo "Device utilities:"
        echo "  usb-scan [args]  Scan for connected ESP32 devices"
        echo "  auto-pair [args] Auto-pair ESP32 devices with Polar sensors"
        ;;
esac
