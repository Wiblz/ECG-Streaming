#!/bin/bash
# ECG Collector Remote Installation Script
# Usage: ./install-collector.sh <user@host> <aggregator_host> <device_ids> [display_name]
#
# Example: ./install-collector.sh pi@192.168.1.100 192.168.1.50 "Polar1,Polar2" "Lab RPi"

set -e -u -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <user@host> <aggregator_host> <device_ids> [display_name]"
    echo ""
    echo "Arguments:"
    echo "  user@host      - SSH target (e.g., pi@192.168.1.100)"
    echo "  aggregator_host - Aggregator server IP/hostname (e.g., 192.168.1.50)"
    echo "  device_ids     - Comma-separated device IDs (e.g., 'Polar1,Polar2')"
    echo "  display_name   - Optional human-readable name (e.g., 'Lab RPi')"
    echo ""
    echo "Example:"
    echo "  $0 pi@192.168.1.100 192.168.1.50 'Polar1,Polar2' 'Lab RPi'"
    exit 1
fi

SSH_TARGET="$1"
AGGREGATOR_HOST="$2"
DEVICE_IDS="$3"
DISPLAY_NAME="${4:-$SSH_TARGET}"

echo -e "${GREEN}=== ECG Collector Installation ===${NC}"
echo "Target: $SSH_TARGET"
echo "Aggregator: $AGGREGATOR_HOST"
echo "Devices: $DEVICE_IDS"
echo "Display Name: $DISPLAY_NAME"
echo ""

# Extract user and host
SSH_USER=$(echo "$SSH_TARGET" | cut -d'@' -f1)
SSH_HOST=$(echo "$SSH_TARGET" | cut -d'@' -f2)

# Test SSH connection
echo -e "${YELLOW}Testing SSH connection...${NC}"
if ! ssh -o ConnectTimeout=5 "$SSH_TARGET" "echo 'SSH OK'" 2>/dev/null; then
    echo -e "${RED}ERROR: Cannot connect to $SSH_TARGET${NC}"
    echo "Make sure the host is reachable and you have the correct credentials."
    exit 1
fi
echo -e "${GREEN}✓ SSH connection OK${NC}"

# Create installation directory
INSTALL_DIR="/home/$SSH_USER/ecg-collector"
echo -e "${YELLOW}Creating installation directory: $INSTALL_DIR${NC}"
ssh "$SSH_TARGET" "mkdir -p '$INSTALL_DIR'"

# Package the collector
echo -e "${YELLOW}Packaging collector...${NC}"
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Copy entire workspace
cp -r packages "$TEMP_DIR/"
cp pyproject.toml "$TEMP_DIR/"
cp uv.lock "$TEMP_DIR/"

# Create tarball
echo -e "${YELLOW}Creating package archive...${NC}"
TARBALL="$TEMP_DIR/ecg-collector.tar.gz"
tar -czf "$TARBALL" -C "$TEMP_DIR" packages pyproject.toml uv.lock

# Transfer files
echo -e "${YELLOW}Transferring files to $SSH_TARGET...${NC}"
scp "$TARBALL" "$SSH_TARGET:$INSTALL_DIR/ecg-collector.tar.gz"

# Create remote installation script
cat > "$TEMP_DIR/remote-install.sh" << 'REMOTE_SCRIPT'
#!/bin/bash
set -e -u -o pipefail

INSTALL_DIR="$1"
AGGREGATOR_HOST="$2"
DEVICE_IDS="$3"
DISPLAY_NAME="$4"

echo "=== Remote Installation ==="
cd "$INSTALL_DIR"

# Check if collector is running (exclude this install script from the match)
if pgrep -f ".venv/bin/ecg-collector" > /dev/null 2>&1; then
    echo "ERROR: ecg-collector is currently running!"
    echo "Please stop it before updating:"
    echo "  pkill -f '.venv/bin/ecg-collector'"
    exit 1
fi

# Extract files
echo "Extracting files..."
tar -xzf ecg-collector.tar.gz
rm ecg-collector.tar.gz

# Detect package manager and install system dependencies
echo "Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu/Raspberry Pi OS
    sudo apt-get update
    sudo apt-get install -y \
        bluetooth \
        bluez \
        libbluetooth-dev \
        libglib2.0-dev \
        curl
elif command -v pacman &> /dev/null; then
    # Arch Linux
    sudo pacman -Sy --noconfirm \
        bluez \
        bluez-utils \
        curl
else
    echo "WARNING: Unknown package manager. Please install manually:"
    echo "  - Bluetooth/BlueZ"
    echo "  - curl"
fi

# Install uv if not present
if ! [ -f "$HOME/.local/bin/uv" ]; then
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# uv installs to ~/.local/bin, just use it directly
UV="$HOME/.local/bin/uv"

# Use uv to sync the entire workspace
echo "Setting up Python environment and installing packages..."
$UV sync --package ecg-collector

# Generate configuration file in package directory
echo "Creating configuration..."
CONFIG_DIR="$INSTALL_DIR/config"
CONFIG_PATH="$CONFIG_DIR/collector.yaml"
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_PATH" << CONFIG
collector_id: "$(hostname)-collector"
display_name: "$DISPLAY_NAME"
devices:
$(echo "$DEVICE_IDS" | tr ',' '\n' | sed 's/^ *//;s/ *$//;s/.*/  "&":/')

ble:
  max_devices_per_adapter: 7
  connection_timeout: 10

aggregator:
  host: "$AGGREGATOR_HOST"
  port: 50051
  batch_size: 50
  batch_interval: 0.1

logging:
  level: INFO
  format: detailed
CONFIG

echo "Configuration created at $CONFIG_PATH"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Installation directory: $INSTALL_DIR"
echo "Configuration file: $CONFIG_PATH"
echo ""
echo "To run the collector:"
echo "  cd $INSTALL_DIR && .venv/bin/ecg-collector ble run --config $CONFIG_PATH"
REMOTE_SCRIPT

# Transfer and execute remote installation script
scp "$TEMP_DIR/remote-install.sh" "$SSH_TARGET:$INSTALL_DIR/remote-install.sh"
ssh "$SSH_TARGET" "chmod +x '$INSTALL_DIR/remote-install.sh'"

echo -e "${YELLOW}Running remote installation...${NC}"
ssh -t "$SSH_TARGET" "'$INSTALL_DIR/remote-install.sh' '$INSTALL_DIR' '$AGGREGATOR_HOST' '$DEVICE_IDS' '$DISPLAY_NAME'"

echo ""
echo -e "${GREEN}=== Installation Complete ===${NC}"
echo ""
echo "To run the collector:"
echo "  ssh -t $SSH_TARGET 'cd $INSTALL_DIR && .venv/bin/ecg-collector ble run --config config/collector.yaml'"
echo ""
echo "To edit config:"
echo "  ssh $SSH_TARGET 'nano $INSTALL_DIR/config/collector.yaml'"
