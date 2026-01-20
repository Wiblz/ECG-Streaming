"""Unified CLI for ECG Collector."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from bleak import BleakScanner
from ecg_common import __version__
from ecg_common.logging import setup_logging
from rich.console import Console
from rich.table import Table

console = Console()

# Main app
app = typer.Typer(
    help="ECG Collector - Stream ECG data from Polar H10 devices via BLE or USB",
    no_args_is_help=True,
)

# BLE subcommands
ble_app = typer.Typer(help="BLE collector commands")
app.add_typer(ble_app, name="ble")

# USB subcommands
usb_app = typer.Typer(help="USB collector commands")
app.add_typer(usb_app, name="usb")


# ============================================================================
# BLE Commands
# ============================================================================


@ble_app.command("scan")
def ble_scan(timeout: int = 5) -> None:
    """Scan for nearby Polar BLE devices.

    Args:
        timeout: Scan duration in seconds
    """
    console.print(f"[blue]Scanning for Polar devices ({timeout}s)...[/blue]")

    async def _scan() -> None:
        devices = await BleakScanner.discover(timeout=timeout)

        polar_devices = [d for d in devices if d.name and "Polar" in d.name]

        if polar_devices:
            table = Table(title="Polar Devices Found")
            table.add_column("Name", style="cyan")
            table.add_column("Address", style="green")
            table.add_column("RSSI", style="yellow")

            for device in polar_devices:
                rssi = (
                    getattr(device.details, "rssi", "N/A") if hasattr(device, "details") else "N/A"
                )
                table.add_row(device.name or "Unknown", device.address, str(rssi))

            console.print(table)
        else:
            console.print("[yellow]No Polar devices found[/yellow]")

    asyncio.run(_scan())


@ble_app.command("test")
def ble_test(device_id: str) -> None:
    """Test connection to a specific BLE device.

    Args:
        device_id: Device ID or MAC address to test
    """
    console.print(f"[blue]Testing connection to {device_id}...[/blue]")

    async def _test() -> None:
        from ecg_collector.ble.drivers import PolarH10Driver

        driver = PolarH10Driver(device_id=device_id, address=device_id)

        success = await driver.connect()

        if success:
            console.print(f"[green]✓ Successfully connected to {device_id}[/green]")

            # Get device info
            info = await driver.get_device_info()
            console.print(f"Device info: {info}")

            # Get battery level
            battery = await driver.get_battery_level()
            if battery:
                console.print(f"Battery level: {battery}%")

            await driver.disconnect()
        else:
            console.print(f"[red]✗ Failed to connect to {device_id}[/red]")

    asyncio.run(_test())


@ble_app.command("run")
def ble_run(
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to configuration file")
    ] = Path("config.yaml"),
) -> None:
    """Run BLE collector with config file.

    Args:
        config: Path to YAML configuration file
    """
    from ecg_collector.ble.service import BleCollectorService
    from ecg_collector.config import CollectorSettings

    # Load configuration
    try:
        if config.exists():
            settings = CollectorSettings.from_yaml(config)
        else:
            console.print(f"[yellow]Config file {config} not found, using defaults[/yellow]")
            settings = CollectorSettings()
    except Exception as e:
        console.print(f"[red]Failed to load configuration: {e}[/red]")
        sys.exit(1)

    # Setup logging
    setup_logging(
        level=settings.logging.level,
        log_file=settings.logging.file,
        log_format=settings.logging.format,
    )

    # Validate configuration
    if not settings.device_ids:
        console.print("[red]No devices configured. Please add device_ids to config.yaml[/red]")
        sys.exit(1)

    console.print("[blue]Starting BLE Collector...[/blue]")
    console.print(f"  Collector ID: {settings.collector_id}")
    console.print(f"  Display Name: {settings.display_name}")
    console.print(f"  Devices: {settings.device_ids}")
    console.print(f"  Aggregator: {settings.aggregator.host}:{settings.aggregator.port}")

    # Create and run service
    service = BleCollectorService(settings)

    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


# ============================================================================
# USB Commands
# ============================================================================


@usb_app.command("scan")
def usb_scan() -> None:
    """Scan for USB serial devices (ESP32)."""
    from ecg_collector.usb.collector import discover_usb_devices

    console.print("[blue]Scanning for USB devices...[/blue]")

    async def _scan() -> None:
        devices = await discover_usb_devices()

        if devices:
            table = Table(title="USB Devices Found")
            table.add_column("Device Path", style="green")

            for device in devices:
                table.add_row(device)

            console.print(table)
            console.print(f"\n[green]Found {len(devices)} USB device(s)[/green]")
        else:
            console.print("[yellow]No USB devices found[/yellow]")

    asyncio.run(_scan())


@usb_app.command("run")
def usb_run(
    device: Annotated[
        str, typer.Option("--device", "-d", help="USB device path (e.g., /dev/ttyACM0)")
    ],
    aggregator: Annotated[
        str, typer.Option("--aggregator", "-a", help="Aggregator address (host:port)")
    ] = "localhost:50051",
    collector_id: Annotated[
        str | None, typer.Option("--id", "-i", help="Collector ID (auto-generated if not provided)")
    ] = None,
) -> None:
    """Run USB collector for ESP32 device.

    Args:
        device: USB device path (e.g., /dev/ttyACM0)
        aggregator: Aggregator address in host:port format
        collector_id: Optional collector ID
    """
    from ecg_collector.config import CollectorSettings
    from ecg_collector.usb.service import UsbCollectorService

    # Setup logging (reuse config.yaml if present)
    config = Path("config.yaml")
    try:
        settings = CollectorSettings.from_yaml(config) if config.exists() else CollectorSettings()
    except Exception as e:
        console.print(f"[red]Failed to load configuration: {e}[/red]")
        settings = CollectorSettings()

    setup_logging(
        level=settings.logging.level,
        log_file=settings.logging.file,
        log_format=settings.logging.format,
    )

    # Parse aggregator address
    try:
        host, port_str = aggregator.rsplit(":", 1)
        port = int(port_str)
    except ValueError:
        console.print(f"[red]Invalid aggregator address: {aggregator}[/red]")
        console.print("Format should be host:port (e.g., localhost:50051)")
        return

    console.print("[blue]Starting USB collector:[/blue]")
    console.print(f"  Device: {device}")
    console.print(f"  Aggregator: {host}:{port}")
    if collector_id:
        console.print(f"  Collector ID: {collector_id}")

    async def _run() -> None:
        service = UsbCollectorService(
            device_path=device,
            aggregator_host=host,
            aggregator_port=port,
            collector_id=collector_id,
        )

        try:
            await service.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
        finally:
            await service.stop()

    asyncio.run(_run())


# ============================================================================
# Main
# ============================================================================


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[bool, typer.Option("--version", "-v", help="Show version and exit")] = False,
) -> None:
    """ECG Collector - Stream ECG data from Polar H10 devices."""
    if version:
        console.print(f"ecg-collector version {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
