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

DEFAULT_CONFIG_PATH = Path("packages") / "ecg-collector" / "config.yaml"

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
    ] = DEFAULT_CONFIG_PATH,
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
        console.print(
            f"[red]No devices configured. Please add device_ids to {DEFAULT_CONFIG_PATH}[/red]"
        )
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
def usb_scan(
    timeout: Annotated[
        float, typer.Option("--timeout", "-t", help="Probe timeout per device (seconds)")
    ] = 12.0,
) -> None:
    """Scan for USB serial devices (ESP32)."""
    from ecg_collector.usb.collector import discover_usb_devices, probe_usb_device

    console.print("[blue]Scanning for USB devices...[/blue]")

    async def _scan() -> None:
        devices = await discover_usb_devices()

        if devices:
            table = Table(title="USB Devices Found")
            table.add_column("Device Path", style="green")
            table.add_column("ESP ID", style="cyan")
            table.add_column("Target", style="magenta")
            table.add_column("FW", style="yellow")
            table.add_column("Polar", style="blue")
            table.add_column("Config Required", style="red")
            table.add_column("Message", style="white")

            for device in devices:
                info = await probe_usb_device(device, timeout_s=timeout)
                if info and info.get("type") == "usb_device_info":
                    target = info.get("current_target") or "<unassigned>"
                    table.add_row(
                        device,
                        info.get("esp_id", ""),
                        target,
                        info.get("firmware_version", ""),
                        str(info.get("polar_connected", "")),
                        str(info.get("config_required", "")),
                        "usb_device_info",
                    )
                elif info:
                    table.add_row(
                        device,
                        "",
                        info.get("device_id", ""),
                        "",
                        "",
                        "",
                        info.get("type", ""),
                    )
                else:
                    table.add_row(device, "", "", "", "", "", "no data")

            console.print(table)
            console.print(f"\n[green]Found {len(devices)} USB device(s)[/green]")
        else:
            console.print("[yellow]No USB devices found[/yellow]")

    asyncio.run(_scan())


@usb_app.command("run")
def usb_run(
    aggregator: Annotated[
        str | None, typer.Option("--aggregator", "-a", help="Aggregator address (host:port)")
    ] = None,
    devices: Annotated[
        list[str] | None,
        typer.Option("--device", "-d", help="USB device path (repeatable)"),
    ] = None,
    collector_id: Annotated[
        str | None, typer.Option("--id", "-i", help="Collector ID (auto-generated if not provided)")
    ] = None,
    display_name: Annotated[
        str | None, typer.Option("--name", "-n", help="Collector display name")
    ] = None,
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to configuration file")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Run USB collector for ESP32 device.

    Args:
        aggregator: Aggregator address in host:port format
        devices: USB device paths (repeatable)
        collector_id: Optional collector ID
        display_name: Optional display name
        config: Path to YAML configuration file
    """
    from ecg_collector.config import CollectorSettings
    from ecg_collector.usb.collector import discover_usb_devices
    from ecg_collector.usb.service import MultiUsbCollectorService

    # Load configuration
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

    # Resolve aggregator address
    if aggregator:
        try:
            host, port_str = aggregator.rsplit(":", 1)
            port = int(port_str)
        except ValueError:
            console.print(f"[red]Invalid aggregator address: {aggregator}[/red]")
            console.print("Format should be host:port (e.g., localhost:50051)")
            return
    else:
        host = settings.aggregator.host
        port = settings.aggregator.port

    # Resolve device paths
    device_paths = devices or settings.usb.devices
    if not device_paths and settings.usb.auto_discover:
        device_paths = asyncio.run(discover_usb_devices())

    if not device_paths:
        console.print("[red]No USB devices configured or discovered[/red]")
        console.print("Use --device to specify device paths or enable usb.auto_discover")
        return

    console.print("[blue]Starting USB collector:[/blue]")
    console.print(f"  Devices: {', '.join(device_paths)}")
    console.print(f"  Aggregator: {host}:{port}")
    if collector_id:
        console.print(f"  Collector ID: {collector_id}")
    if display_name:
        console.print(f"  Display Name: {display_name}")

    async def _run() -> None:
        service = MultiUsbCollectorService(
            device_paths=device_paths,
            aggregator_host=host,
            aggregator_port=port,
            collector_id=collector_id or settings.collector_id,
            display_name=display_name or settings.display_name,
            allowed_device_ids=settings.usb.allowed_device_ids,
            detect_timeout_s=settings.usb.detect_timeout_s,
            device_map=settings.usb.device_map,
            persist_config=settings.usb.persist_config,
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
