# ESP32 Firmware

The `esp32/` directory contains C firmware for the ESP32-S3-Zero receiver boards. Each receiver connects to a single Polar H10 sensor via BLE and forwards ECG data to the host over USB CDC.

This is a one-time setup per board. Once flashed, boards do not need to be reflashed unless the firmware changes.

## Requirements

- [ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/get-started/) v5.5
- Target chip: ESP32-S3

## Install ESP-IDF

```bash
# Clone ESP-IDF
mkdir -p ~/Projects/esp
cd ~/Projects/esp
git clone --branch v5.5 --depth 1 https://github.com/espressif/esp-idf.git

# Run the installer (installs toolchain, Python env, etc.)
cd esp-idf
./install.sh esp32s3

# Add to your shell (add this to ~/.bashrc or ~/.zshrc)
. ~/Projects/esp/esp-idf/export.sh
```

## Build

```bash
cd esp32/
idf.py build
```

The compiled binary will be at `build/ecg_esp32.bin`.

## Flash

### 1. Enter download mode

The ESP32-S3-Zero must be in download mode before flashing:

1. Hold the **BOOT** button
2. Press and release the **RESET** button
3. Release **BOOT**

The board will appear as `/dev/ttyACM*` or `/dev/ttyUSB*`.

### 2. Flash the firmware

```bash
idf.py -p /dev/ttyACM0 flash
```

Replace `/dev/ttyACM0` with your actual port. To find it:

```bash
ls /dev/ttyACM* /dev/ttyUSB*
```

If you get a permission error:

```bash
sudo usermod -a -G dialout $USER
# log out and back in
```

### 3. Reboot

After flashing completes, press the **RESET** button to boot into the new firmware. The board will reconnect as a USB CDC device and is ready to use.

## Erase flash (factory reset)

To fully reset a board before reflashing:

```bash
idf.py -p /dev/ttyACM0 --baud 115200 --no-stub erase-flash
```

Then reflash as above. The `--no-stub` and reduced baud rate avoid a known disconnection issue with the ESP32-S3 USB-JTAG interface at high speeds.

## Verify

After flashing and rebooting, confirm the board is recognised:

```bash
./stack.sh usb-scan          # dev
./stack.sh --prod usb-scan   # prod
```

The board should appear in the scan output and be ready for pairing.
