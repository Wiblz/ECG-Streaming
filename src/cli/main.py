"""CLI tool for debugging and monitoring ECG streaming system."""

import asyncio
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.live import Live
from rich.table import Table

from src.collector.adapter_manager import BLEAdapterManager
from src.collector.device_driver import DeviceStatus
from src.common.logging import get_logger
from src.config.settings import load_settings
from src.sync.time_alignment import TimeAlignmentService

app = typer.Typer(help="ECG Streaming CLI - Device debugging and monitoring")
console = Console()
logger = get_logger(__name__)


@app.command()
def scan(
    adapter: str | None = None,
    timeout: int = 10,
) -> None:
    """Scan for nearby Polar H10 devices."""
    from bleak import BleakScanner

    async def do_scan() -> None:
        console.print(f"[yellow]Scanning for BLE devices (timeout: {timeout}s)...[/yellow]")

        if adapter:
            devices = await BleakScanner.discover(
                timeout=float(timeout), bluez={"adapter": adapter}
            )
        else:
            devices = await BleakScanner.discover(timeout=float(timeout))

        # Filter for Polar devices
        polar_devices = [d for d in devices if d.name and "Polar" in d.name]

        if not polar_devices:
            console.print("[red]No Polar devices found[/red]")
            return

        # Create table
        table = Table(title="Found Polar Devices", box=box.ROUNDED)
        table.add_column("Name", style="cyan")
        table.add_column("Address", style="green")
        table.add_column("RSSI", style="yellow")

        for device in polar_devices:
            rssi = device.rssi if hasattr(device, "rssi") else "N/A"
            table.add_row(device.name, device.address, str(rssi))

        console.print(table)

    asyncio.run(do_scan())


@app.command()
def list_devices(
    config_file: Path | None = None,
) -> None:
    """List configured devices and their status."""
    settings = load_settings(config_file)

    if not settings.device_ids:
        console.print("[yellow]No devices configured[/yellow]")
        console.print("Add device IDs to your configuration file.")
        return

    # Create table
    table = Table(title="Configured Devices", box=box.ROUNDED)
    table.add_column("Device ID", style="cyan")
    table.add_column("Status", style="green")

    for device_id in settings.device_ids:
        table.add_row(device_id, "Configured")

    console.print(table)
    console.print(f"\n[blue]Total devices: {len(settings.device_ids)}[/blue]")


@app.command()
def test_connection(
    device_id: str,
    address: str | None = None,
    adapter: str | None = None,
) -> None:
    """Test connection to a single device."""
    from src.collector.polar_h10_driver import PolarH10Driver

    async def do_test() -> None:
        console.print(f"[yellow]Testing connection to {device_id}...[/yellow]")

        # Create driver
        driver = PolarH10Driver(device_id=device_id, address=address, adapter_id=adapter)

        # Try to connect
        with console.status("[bold green]Connecting..."):
            success = await driver.connect()

        if not success:
            console.print(f"[red]Failed to connect to {device_id}[/red]")
            return

        console.print(f"[green]✓ Connected to {device_id}[/green]")

        # Get device info
        info = await driver.get_device_info()
        console.print("\n[cyan]Device Information:[/cyan]")
        for key, value in info.items():
            console.print(f"  {key}: {value}")

        # Get battery level
        battery = await driver.get_battery_level()
        if battery is not None:
            console.print(f"\n[yellow]Battery Level: {battery}%[/yellow]")

        # Disconnect
        await driver.disconnect()
        console.print("\n[green]✓ Disconnected[/green]")

    asyncio.run(do_test())


@app.command()
def monitor(
    config_file: Path | None = None,
    refresh_rate: float = 1.0,
) -> None:
    """Monitor device connections and sync status in real-time."""
    settings = load_settings(config_file)

    if not settings.device_ids:
        console.print("[red]No devices configured[/red]")
        return

    async def do_monitor() -> None:
        # Initialize services
        adapter_manager = BLEAdapterManager(
            max_devices_per_adapter=settings.ble.max_devices_per_adapter
        )
        time_alignment = TimeAlignmentService(
            window_size=settings.sync.regression_window_size,
            min_samples=settings.sync.min_samples_for_sync,
            confidence_threshold=settings.sync.confidence_threshold,
        )

        # Add devices
        for device_id in settings.device_ids:
            adapter_manager.add_device(device_id)
            time_alignment.register_device(device_id)

        # Connect devices
        console.print("[yellow]Connecting to devices...[/yellow]")
        await adapter_manager.connect_all()

        # Start streaming
        console.print("[yellow]Starting data streams...[/yellow]")
        await adapter_manager.start_streaming_all()

        def generate_table() -> Table:
            """Generate status table."""
            table = Table(title="Device Status", box=box.ROUNDED)
            table.add_column("Device ID", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Sync Ready", style="yellow")
            table.add_column("Confidence", style="magenta")
            table.add_column("Drift (ppm)", style="blue")
            table.add_column("Samples", style="white")

            for driver in adapter_manager.get_all_devices():
                # Get sync model
                model = time_alignment.get_device_model(driver.device_id)
                sync_ready = time_alignment.is_device_ready(driver.device_id)

                # Status icon
                status_icon = {
                    DeviceStatus.CONNECTED: "🟢",
                    DeviceStatus.STREAMING: "🔵",
                    DeviceStatus.DISCONNECTED: "🔴",
                    DeviceStatus.ERROR: "❌",
                }.get(driver.status, "⚪")

                # Sync data
                if model:
                    confidence = f"{model.confidence:.3f}"
                    drift_ppm = f"{(model.drift - 1.0) * 1_000_000:.1f}"
                    samples = str(model.sample_count)
                else:
                    confidence = "-"
                    drift_ppm = "-"
                    samples = "-"

                sync_icon = "✓" if sync_ready else "✗"

                table.add_row(
                    driver.device_id,
                    f"{status_icon} {driver.status.value}",
                    sync_icon,
                    confidence,
                    drift_ppm,
                    samples,
                )

            return table

        # Monitor loop
        try:
            with Live(generate_table(), refresh_per_second=1 / refresh_rate, console=console):
                while True:
                    # Process samples and update time models
                    for driver in adapter_manager.get_all_devices():
                        sample = await driver.read_ecg_sample()
                        if sample:
                            time_alignment.add_timestamp_pair(
                                sample.device_id,
                                sample.device_timestamp,
                                sample.host_receive_time,
                            )

                    await asyncio.sleep(0.01)  # Small sleep to avoid busy loop

        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping monitor...[/yellow]")
        finally:
            # Cleanup
            await adapter_manager.stop_streaming_all()
            await adapter_manager.disconnect_all()

    asyncio.run(do_monitor())


@app.command()
def adapter_stats(
    config_file: Path | None = None,
) -> None:
    """Show BLE adapter statistics."""
    settings = load_settings(config_file)

    adapter_manager = BLEAdapterManager(
        max_devices_per_adapter=settings.ble.max_devices_per_adapter
    )

    # Add devices
    for device_id in settings.device_ids:
        adapter_manager.add_device(device_id)

    # Get stats
    stats = adapter_manager.get_adapter_stats()

    # Create table
    table = Table(title="BLE Adapter Statistics", box=box.ROUNDED)
    table.add_column("Adapter", style="cyan")
    table.add_column("Devices", style="green")
    table.add_column("Capacity", style="yellow")
    table.add_column("Utilization", style="magenta")

    for adapter_id, adapter_stats_dict in stats.items():
        utilization_val = adapter_stats_dict["utilization"]
        assert isinstance(utilization_val, float)
        utilization = f"{utilization_val * 100:.1f}%"
        table.add_row(
            adapter_id,
            str(adapter_stats_dict["device_count"]),
            str(adapter_stats_dict["capacity"]),
            utilization,
        )

    console.print(table)

    # Device assignment
    console.print("\n[cyan]Device Assignments:[/cyan]")
    for adapter_id, adapter_stats_dict in stats.items():
        console.print(f"\n[yellow]{adapter_id}:[/yellow]")
        devices = adapter_stats_dict["devices"]
        assert isinstance(devices, list)
        for device_id in devices:
            console.print(f"  • {device_id}")


@app.command()
def create_config(
    output: Path = Path("config.yaml"),
) -> None:
    """Create a default configuration file."""
    from src.config.settings import create_default_config

    if output.exists():
        overwrite = typer.confirm(f"{output} already exists. Overwrite?")
        if not overwrite:
            console.print("[yellow]Aborted[/yellow]")
            return

    create_default_config(output)
    console.print(f"[green]✓ Created default configuration at {output}[/green]")
    console.print("\n[cyan]Next steps:[/cyan]")
    console.print("1. Edit the configuration file to add your device IDs")
    console.print("2. Run 'ecg-cli monitor' to start monitoring")


if __name__ == "__main__":
    app()
