"""CLI utilities for ECG Collector."""

import asyncio

import typer
from bleak import BleakScanner
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="ECG Collector CLI utilities")
console = Console()


@app.command()
def scan(timeout: int = 5) -> None:
    """Scan for nearby Polar devices.

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


@app.command()
def test_connection(device_id: str, timeout: int = 10) -> None:
    """Test connection to a specific device.

    Args:
        device_id: Device ID or address to test
        timeout: Connection timeout in seconds
    """
    console.print(f"[blue]Testing connection to {device_id}...[/blue]")

    async def _test() -> None:
        from ecg_collector.collector.polar_h10_driver import PolarH10Driver

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


if __name__ == "__main__":
    app()
