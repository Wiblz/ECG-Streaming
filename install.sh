#!/bin/bash
# ECG-Streaming Installation Script

set -e

echo "=========================================="
echo "  ECG-Streaming Installation"
echo "=========================================="
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed"
    echo "Please install uv first: https://github.com/astral-sh/uv"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install packages
echo ""
echo "Installing packages..."
echo "  1/3 Installing ecg-common..."
uv pip install -e packages/ecg-common

echo "  2/3 Installing ecg-collector..."
uv pip install -e packages/ecg-collector

echo "  3/3 Installing ecg-aggregator..."
uv pip install -e packages/ecg-aggregator

# Generate gRPC code
echo ""
echo "Generating gRPC code from protobuf..."
python packages/ecg-common/generate_proto.py

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Available commands:"
echo "  ecg-collector        - Collector CLI (ble/usb subcommands)"
echo "  ecg-aggregator       - Aggregator CLI"
echo ""
echo "Next steps:"
echo "  1. Copy the example collector config:"
echo "     cp config/collector.yaml.example config/collector.yaml"
echo "  2. Edit config/collector.yaml with your device IDs"
echo "  3. Run: ecg-aggregator run --config config/aggregator.yaml"
echo "  4. Run: ecg-collector ble run --config config/collector.yaml"
echo ""
