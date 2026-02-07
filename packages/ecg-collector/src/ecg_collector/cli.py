"""Unified CLI for ECG Collector."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from ecg_common import __version__
from ecg_common.logging import setup_logging
from rich.console import Console
from rich.live import Live
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
    from ecg_common.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Starting BLE scan command")

    console.print(f"[blue]Scanning for Polar devices ({timeout}s)...[/blue]")

    async def _scan() -> None:
        from ecg_collector.ble_scanner import scan_polar_devices

        polar_devices = await scan_polar_devices(timeout=timeout)

        if polar_devices:
            table = Table(title="Polar Devices Found")
            table.add_column("Name", style="cyan")
            table.add_column("Address", style="green")
            table.add_column("RSSI", style="yellow")

            for device in polar_devices:
                rssi_str = str(device.rssi) if device.rssi is not None else "N/A"
                table.add_row(device.name, device.address, rssi_str)

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
    from ecg_common.logging import get_logger

    logger = get_logger(__name__)
    logger.info(f"Starting BLE test command for device {device_id}")

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
        ble_debug_file=settings.logging.ble_debug_file,
        log_format=settings.logging.format,
    )

    from ecg_common.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Starting BLE run command")

    # Validate configuration
    device_list = settings.get_device_list()
    if not device_list:
        console.print(
            f"[red]No devices configured. Please add devices to {DEFAULT_CONFIG_PATH}[/red]"
        )
        sys.exit(1)

    console.print("[blue]Starting BLE Collector...[/blue]")
    console.print(f"  Collector ID: {settings.collector_id}")
    console.print(f"  Display Name: {settings.display_name}")
    console.print(f"  Devices: {device_list}")
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
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to configuration file")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Scan for USB serial devices (ESP32)."""
    from ecg_collector.config import CollectorSettings
    from ecg_collector.usb.collector import discover_and_group_usb_interfaces, probe_usb_groups
    from ecg_collector.usb.models import ProbeStatus

    # Load config and setup logging so probe logs go to file
    try:
        settings = CollectorSettings.from_yaml(config) if config.exists() else CollectorSettings()
    except Exception:
        settings = CollectorSettings()

    setup_logging(
        level=settings.logging.level,
        log_file=settings.logging.file,
        log_format=settings.logging.format,
        console=False,  # Disable console logging to avoid interfering with Live display
    )

    from ecg_common.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Starting USB scan command")

    console.print("[blue]Scanning for USB devices...[/blue]")

    async def _scan() -> None:
        # Discover device groups
        device_groups = await discover_and_group_usb_interfaces()

        if not device_groups:
            console.print("[yellow]No USB devices found[/yellow]")
            return

        # Create table structure
        def create_table() -> Table:
            table = Table(title="USB Devices Found")
            table.add_column("Physical Device", style="cyan", no_wrap=True)
            table.add_column("Iface", style="dim", no_wrap=True)
            table.add_column("Device Path", style="green")
            table.add_column("Status", style="white")
            table.add_column("ESP ID", style="cyan")
            table.add_column("Target", style="magenta")
            table.add_column("FW", style="yellow")
            table.add_column("Polar", style="blue")
            table.add_column("Config", style="red")
            return table

        def get_status_display(
            status: ProbeStatus,
            error_msg: str | None = None,
            partial_info: object | None = None,
        ) -> str:
            """Get colored status display string."""
            if status == ProbeStatus.DISCOVERED:
                return "[dim]Discovered[/dim]"
            elif status == ProbeStatus.PROBING:
                return "[yellow]Probing...[/yellow]"
            elif status == ProbeStatus.RECEIVED:
                return "[green]Received[/green]"
            elif status == ProbeStatus.TIMEOUT:
                # Show partial activity if detected
                from ecg_collector.usb.models import ProbePartialInfo

                if isinstance(partial_info, ProbePartialInfo):
                    return f"[yellow]Timeout[/yellow] (saw {partial_info.last_message_type})"
                return "[red]No response[/red]"
            else:  # ProbeStatus.ERROR
                return f"[red]Error[/red]: {error_msg or 'Unknown'}"

        def update_table() -> Table:
            """Generate updated table from current device groups state."""
            table = create_table()

            for _group_key, group in sorted(device_groups.items()):
                # Determine display values
                # Prefer bus-port for display if available (more reliable than USB serial)
                if group.bus_port:
                    physical_device_display = f"Port {group.bus_port}"
                elif group.usb_serial:
                    physical_device_display = group.usb_serial
                else:
                    physical_device_display = "Unknown"
                esp_id = ""
                target = ""
                fw = ""
                polar = ""
                config = ""

                # Extract device info if received
                if group.device_info:
                    esp_id = group.device_info.esp_id
                    target = group.device_info.current_target or "<unassigned>"
                    fw = group.device_info.firmware_version
                    polar = "Connected" if group.device_info.polar_connected else "Disconnected"
                    config = "Unconfigured" if group.device_info.config_required else "Configured"

                # Add data interface row
                if group.data_interface:
                    status_display = get_status_display(
                        group.probe_status, group.error_message, group.partial_info
                    )
                    table.add_row(
                        physical_device_display,
                        "DATA",
                        group.data_interface.device_path,
                        status_display,
                        esp_id,
                        target,
                        fw,
                        polar,
                        config,
                    )

                # Add log interface row
                if group.log_interface:
                    log_status = "[blue]Available[/blue]"
                    # Show ESP ID in log row if we got device_info from data interface
                    log_esp_id = esp_id if group.probe_status == ProbeStatus.RECEIVED else ""
                    table.add_row(
                        "",  # Empty for grouped display
                        "LOG",
                        group.log_interface.device_path,
                        log_status,
                        log_esp_id,
                        "",
                        "",
                        "",
                        "",
                    )

            return table

        # Display live-updating table during probing
        with Live(update_table(), console=console, refresh_per_second=4) as live:
            await probe_usb_groups(
                device_groups,
                timeout_s=timeout,
                on_update=lambda group_key, group: live.update(update_table()),
            )

        # Final summary
        total_devices = len(device_groups)
        data_interfaces = sum(1 for g in device_groups.values() if g.data_interface)
        log_interfaces = sum(1 for g in device_groups.values() if g.log_interface)
        received = sum(1 for g in device_groups.values() if g.probe_status == ProbeStatus.RECEIVED)

        console.print(
            f"\n[green]Found {total_devices} physical device(s)[/green] "
            f"({data_interfaces} data, {log_interfaces} log) - "
            f"{received} responded with device_info"
        )

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
    from ecg_collector.usb.collector import discover_and_group_usb_interfaces
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
        ble_debug_file=settings.logging.ble_debug_file,
        log_format=settings.logging.format,
    )

    from ecg_common.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Starting USB run command")

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
        # Use smart discovery to only get DATA interfaces
        console.print("[blue]Auto-discovering USB devices...[/blue]")

        async def discover_data_interfaces() -> list[str]:
            device_groups = await discover_and_group_usb_interfaces()
            data_paths = [
                group.data_interface.device_path
                for group in device_groups.values()
                if group.data_interface
            ]

            # Show discovery summary
            total_devices = len(device_groups)
            log_interfaces = sum(1 for g in device_groups.values() if g.log_interface)
            if total_devices > 0:
                console.print(
                    f"[green]Found {total_devices} ESP device(s)[/green] "
                    f"({len(data_paths)} data interface(s), {log_interfaces} log interface(s))"
                )
                console.print("[dim]Note: Only data interfaces will be used for streaming[/dim]")

            return data_paths

        device_paths = asyncio.run(discover_data_interfaces())

    if not device_paths:
        console.print("[red]No USB devices configured or discovered[/red]")
        console.print("Use --device to specify device paths or enable usb.auto_discover")
        return

    console.print("\n[blue]Starting USB collector:[/blue]")
    console.print(f"  Devices: {', '.join(device_paths)}")
    console.print(f"  Aggregator: {host}:{port}")
    if collector_id:
        console.print(f"  Collector ID: {collector_id}")
    if display_name:
        console.print(f"  Display Name: {display_name}")

    async def _run() -> None:
        # Override settings if CLI args provided
        effective_settings = settings
        if collector_id:
            effective_settings.collector_id = collector_id
        if display_name:
            effective_settings.display_name = display_name
        if host != settings.aggregator.host:
            effective_settings.aggregator.host = host
        if port != settings.aggregator.port:
            effective_settings.aggregator.port = port

        # Create service with unified settings
        service = MultiUsbCollectorService(
            device_paths=device_paths,
            settings=effective_settings,
        )

        try:
            await service.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
        finally:
            await service.stop()

    asyncio.run(_run())


@usb_app.command("auto-pair")
def usb_auto_pair(
    ble_timeout: Annotated[
        float, typer.Option("--ble-timeout", help="BLE scan timeout (seconds)")
    ] = 5.0,
    usb_timeout: Annotated[
        float, typer.Option("--usb-timeout", help="USB probe timeout per device (seconds)")
    ] = 12.0,
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to configuration file")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Auto-pair ESP32 devices with configured Polar H10 monitors.

    Shows status of configured Polar devices and pairs them with available ESPs.

    For each configured Polar device, shows:
    - Not Discovered: Polar not found in BLE scan
    - Discovered: Polar found but not connected to an ESP
    - Connected to ESP: Polar is connected to ESP (shows ESP ID)

    Args:
        ble_timeout: BLE scan duration in seconds
        usb_timeout: USB probe timeout per device in seconds
        config: Path to configuration file with Polar devices
    """
    from ecg_collector.ble_scanner import scan_polar_devices
    from ecg_collector.config import CollectorSettings

    # Load configuration to get list of Polar devices
    try:
        if config.exists():
            settings = CollectorSettings.from_yaml(config)
        else:
            console.print(f"[red]Config file {config} not found[/red]")
            console.print("Please create a config with Polar devices first")
            return
    except Exception as e:
        console.print(f"[red]Failed to load configuration: {e}[/red]")
        return

    configured_polars = settings.get_device_list()
    if not configured_polars:
        console.print("[red]No Polar devices configured in config file[/red]")
        console.print("Add devices to the 'devices' section of your config")
        return

    # Setup logging so probe logs go to file
    setup_logging(
        level=settings.logging.level,
        log_file=settings.logging.file,
        log_format=settings.logging.format,
        console=False,  # Disable console logging to avoid interfering with Live display
    )

    from ecg_common.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Starting USB auto-pair command")

    async def _auto_pair() -> None:
        from rich.console import Group

        from ecg_collector.usb.collector import discover_and_group_usb_interfaces, probe_usb_groups
        from ecg_collector.usb.models import EspDeviceGroup, ProbeStatus

        # Discover USB devices first
        device_groups = await discover_and_group_usb_interfaces()
        if not device_groups:
            console.print("[yellow]No ESP devices found[/yellow]")
            return

        # State tracking
        esp_by_polar: dict[str, str] = {}  # polar_id -> esp_id
        discovered_polar_ids: set[str] = set()
        ble_scan_done = False

        def create_tables() -> Group:
            """Generate both tables from current state."""
            # Polar table
            polar_table = Table(title=f"Polar Devices ({len(configured_polars)} configured)")
            polar_table.add_column("Polar ID", style="magenta")
            polar_table.add_column("Nickname", style="white")
            polar_table.add_column("Status", style="cyan")
            polar_table.add_column("ESP ID", style="yellow")

            for polar_id in configured_polars:
                device_config = settings.get_device_config(polar_id)
                nickname = (
                    device_config.nickname
                    if device_config and device_config.nickname
                    else "[dim]—[/dim]"
                )

                # Determine status
                if polar_id in esp_by_polar:
                    status = "[green]Connected[/green]"
                    esp_id = esp_by_polar[polar_id]
                elif polar_id in discovered_polar_ids:
                    status = "[yellow]Discovered[/yellow]"
                    esp_id = "[dim]—[/dim]"
                elif ble_scan_done:
                    status = "[red]Not Discovered[/red]"
                    esp_id = "[dim]—[/dim]"
                else:
                    status = "[dim]Scanning...[/dim]"
                    esp_id = "[dim]—[/dim]"

                polar_table.add_row(polar_id, nickname, status, esp_id)

            # ESP table
            esp_table = Table(title=f"ESP Devices ({len(device_groups)} found)")
            esp_table.add_column("ESP ID", style="cyan")
            esp_table.add_column("Current Target", style="magenta")
            esp_table.add_column("Polar Status", style="white")
            esp_table.add_column("Probe Status", style="yellow")

            for group in device_groups.values():
                if not group.data_interface:
                    continue

                # Get probe status
                if group.probe_status == ProbeStatus.DISCOVERED:
                    probe_status = "[dim]Probing...[/dim]"
                elif group.probe_status == ProbeStatus.PROBING:
                    probe_status = "[yellow]Probing...[/yellow]"
                elif group.probe_status == ProbeStatus.RECEIVED:
                    probe_status = "[green]OK[/green]"
                elif group.probe_status == ProbeStatus.TIMEOUT:
                    # Show partial activity if detected
                    if group.partial_info:
                        probe_status = (
                            f"[yellow]Timeout[/yellow] ({group.partial_info.last_message_type})"
                        )
                    else:
                        probe_status = "[red]Timeout[/red]"
                else:  # ERROR
                    probe_status = "[red]Error[/red]"

                # Get device info if available
                if group.device_info:
                    esp_id = group.device_info.esp_id
                    target = group.device_info.current_target or "[dim]<unassigned>[/dim]"
                    polar_status = (
                        "[green]Connected[/green]"
                        if group.device_info.polar_connected
                        else "[dim]Disconnected[/dim]"
                    )
                else:
                    esp_id = f"[dim]{group.data_interface.device_path}[/dim]"
                    target = "[dim]—[/dim]"
                    polar_status = "[dim]—[/dim]"

                esp_table.add_row(esp_id, target, polar_status, probe_status)

            return Group(polar_table, "", esp_table)

        # Show initial tables and update live
        with Live(create_tables(), console=console, refresh_per_second=4) as live:

            def update_display(group_key: str, group: EspDeviceGroup) -> None:
                """Update ESP mapping from current device states and refresh display."""
                # Rebuild ESP -> Polar mapping from current device_info
                esp_by_polar.clear()
                for g in device_groups.values():
                    if (
                        g.device_info
                        and g.device_info.current_target
                        and g.device_info.polar_connected
                    ):
                        esp_by_polar[g.device_info.current_target] = g.device_info.esp_id
                live.update(create_tables())

            # Task 1: Probe ESPs
            async def probe_esps() -> None:
                await probe_usb_groups(
                    device_groups, timeout_s=usb_timeout, on_update=update_display
                )

            # Task 2: Scan for Polar devices
            async def scan_polars() -> None:
                nonlocal ble_scan_done
                polar_devices = await scan_polar_devices(timeout=ble_timeout)

                # Update discovered Polar set
                for polar in polar_devices:
                    discovered_polar_ids.add(polar.device_id)
                    live.update(create_tables())

                ble_scan_done = True
                live.update(create_tables())

            # Run probing and BLE scan in parallel
            await asyncio.gather(probe_esps(), scan_polars())

        # Show final summary
        console.print()
        connected_count = sum(1 for p in configured_polars if p in esp_by_polar)
        discovered_count = sum(
            1 for p in configured_polars if p in discovered_polar_ids and p not in esp_by_polar
        )
        not_discovered_count = sum(1 for p in configured_polars if p not in discovered_polar_ids)

        console.print(f"[green]• {connected_count} connected to ESP[/green]")
        console.print(f"[yellow]• {discovered_count} discovered but not connected[/yellow]")
        console.print(f"[red]• {not_discovered_count} not discovered[/red]")

    asyncio.run(_auto_pair())


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
