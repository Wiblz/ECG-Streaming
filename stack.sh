#!/usr/bin/env bash
# stack.sh — manage the ECG streaming stack and run CLI utilities
# Usage: ./stack.sh <command> [args...]

set -euo pipefail

cmd="${1:-help}"
shift || true

PROD="-f docker-compose.prod.yml"

case "$cmd" in
    build)
        echo "==> Building dev Docker images..."
        docker compose build aggregator frontend
        docker compose build collector-ble collector-usb
        docker compose build simulator
        echo "==> Done."
        ;;
    build-prod)
        echo "==> Building prod Docker images..."
        docker compose $PROD build aggregator frontend
        docker compose $PROD build collector-ble collector-usb
        echo "==> Done."
        ;;
    up)
        echo "==> Starting dev stack (BLE collector)..."
        docker compose --profile ble up -d
        echo "  Frontend:   http://localhost:5173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-usb)
        echo "==> Starting dev stack (USB collector)..."
        docker compose --profile usb up -d
        echo "  Frontend:   http://localhost:5173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-agg)
        echo "==> Starting dev aggregator + frontend only..."
        docker compose up -d aggregator frontend
        echo "  Frontend:   http://localhost:5173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-prod)
        echo "==> Starting prod stack (BLE collector)..."
        docker compose $PROD --profile ble up -d
        echo "  Frontend:   http://localhost:4173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-prod-usb)
        echo "==> Starting prod stack (USB collector)..."
        docker compose $PROD --profile usb up -d
        echo "  Frontend:   http://localhost:4173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    up-prod-agg)
        echo "==> Starting prod aggregator + frontend only..."
        docker compose $PROD up -d aggregator frontend
        echo "  Frontend:   http://localhost:4173"
        echo "  Aggregator: http://localhost:7999"
        ;;
    down)
        echo "==> Stopping dev stack..."
        docker compose --profile ble --profile usb --profile simulator down
        ;;
    down-prod)
        echo "==> Stopping prod stack..."
        docker compose $PROD --profile ble --profile usb down
        ;;
    logs)
        docker compose --profile ble --profile usb --profile simulator logs -f "$@"
        ;;
    logs-prod)
        docker compose $PROD --profile ble --profile usb logs -f "$@"
        ;;
    clean)
        echo "==> Removing dev containers and volumes..."
        docker compose --profile ble --profile usb --profile simulator down -v
        echo "==> Done."
        ;;
    clean-prod)
        echo "==> Removing prod containers and volumes..."
        docker compose $PROD --profile ble --profile usb down -v
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
        echo "Development stack:"
        echo "  build           Build all dev Docker images"
        echo "  up              Start dev stack with BLE collector"
        echo "  up-usb          Start dev stack with USB collector"
        echo "  up-agg          Start dev aggregator + frontend only"
        echo "  down            Stop dev stack"
        echo "  logs            Follow dev logs (extra args passed to docker compose logs)"
        echo "  clean           Stop dev stack and remove containers and volumes"
        echo ""
        echo "Production stack:"
        echo "  build-prod      Build all prod Docker images"
        echo "  up-prod         Start prod stack with BLE collector"
        echo "  up-prod-usb     Start prod stack with USB collector"
        echo "  up-prod-agg     Start prod aggregator + frontend only"
        echo "  down-prod       Stop prod stack"
        echo "  logs-prod       Follow prod logs"
        echo "  clean-prod      Stop prod stack and remove containers and volumes"
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
