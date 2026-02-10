"""CLI for ECG Aggregator using Typer and Rich."""

import asyncio
import contextlib
import logging
import signal
import sys
from collections import deque
from pathlib import Path
from typing import Annotated

import typer
from ecg_common import __version__
from ecg_common.logging import get_logger, get_run_log_paths, setup_logging
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ecg_aggregator.aggregator import ECGAggregator
from ecg_aggregator.config import AggregatorSettings

app = typer.Typer(
    name="ecg-aggregator",
    help="ECG Aggregator - receives data from collectors, syncs timing, stores in DB, serves API",
    add_completion=False,
)
console = Console()
logger = get_logger(__name__)

DEFAULT_CONFIG_PATH = Path("packages") / "ecg-aggregator" / "config.yaml"

# Global log buffer for TUI
log_buffer: deque[str] = deque(maxlen=50)


class BufferHandler(logging.Handler):
    """Custom logging handler that captures logs to a deque buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the buffer."""
        try:
            msg = self.format(record)
            log_buffer.append(msg)
        except Exception:
            self.handleError(record)


def generate_log_panel() -> Panel:
    """Generate log panel for live display.

    Returns:
        Rich Panel with recent logs
    """
    log_text = Text()
    for log_line in log_buffer:
        # Color code logs based on level
        if "ERROR" in log_line or "CRITICAL" in log_line:
            log_text.append(log_line + "\n", style="red")
        elif "WARNING" in log_line:
            log_text.append(log_line + "\n", style="yellow")
        elif "INFO" in log_line:
            log_text.append(log_line + "\n", style="cyan")
        else:
            log_text.append(log_line + "\n", style="white")

    return Panel(log_text, title="Recent Logs", border_style="blue")


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"ecg-aggregator version {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
) -> None:
    """ECG Aggregator CLI."""
    pass


def generate_status_table(aggregator: ECGAggregator) -> Table:
    """Generate status table for live display.

    Args:
        aggregator: ECGAggregator instance

    Returns:
        Rich Table with current status
    """
    # Main status table
    table = Table(title="ECG Aggregator Status", show_header=True, header_style="bold cyan")
    table.add_column("Component", style="cyan", width=20)
    table.add_column("Status", style="green")
    table.add_column("Details", style="white")

    # Server status
    table.add_row(
        "gRPC Server",
        "✓ Running" if aggregator.grpc_server else "✗ Stopped",
        f"Port {aggregator.config.grpc.port}",
    )
    table.add_row(
        "HTTP/WebSocket",
        "✓ Running" if aggregator.http_server else "✗ Stopped",
        f"Port {aggregator.config.api.port}",
    )
    table.add_row(
        "Database",
        "✓ Connected" if aggregator.database else "✗ Disconnected",
        str(aggregator.config.storage.database_path),
    )

    # Add separator
    table.add_row("", "", "", end_section=True)

    # Collectors section
    if aggregator.grpc_servicer:
        collectors = aggregator.grpc_servicer.collectors
        table.add_row(
            "Connected Collectors",
            f"{len(collectors)} active",
            ", ".join(collectors.keys()) if collectors else "None",
        )

        # Devices
        all_devices = set()
        for collector_data in collectors.values():
            all_devices.update(collector_data.device_ids)

        table.add_row(
            "Registered Devices",
            f"{len(all_devices)} total",
            ", ".join(all_devices) if all_devices else "None",
        )
    else:
        table.add_row("Connected Collectors", "N/A", "gRPC servicer not initialized")

    # Add separator
    table.add_row("", "", "", end_section=True)

    # Buffer statistics
    ecg_stats = aggregator.ecg_buffer.get_stats()
    acc_stats = aggregator.acc_buffer.get_stats()

    table.add_row(
        "ECG Buffer",
        f"{ecg_stats['total_samples']} samples",
        f"{ecg_stats['device_count']} devices",
    )
    table.add_row(
        "ACC Buffer",
        f"{acc_stats['total_samples']} samples",
        f"{acc_stats['device_count']} devices",
    )

    def format_rates(stats: dict) -> str:
        rates: dict[str, float] = stats.get("samples_per_second_per_device", {})
        if not rates:
            return "None"
        parts = [f"{device_id}:{rate:.1f}/s" for device_id, rate in sorted(rates.items())]
        return ", ".join(parts)

    table.add_row(
        "ECG Rate",
        f"{ecg_stats.get('samples_per_second', 0.0):.1f}/s total",
        format_rates(ecg_stats),
    )
    table.add_row(
        "ACC Rate",
        f"{acc_stats.get('samples_per_second', 0.0):.1f}/s total",
        format_rates(acc_stats),
    )

    return table


def generate_collectors_table(aggregator: ECGAggregator) -> Table:
    """Generate detailed collectors table.

    Args:
        aggregator: ECGAggregator instance

    Returns:
        Rich Table with collector details
    """
    table = Table(title="Collectors", show_header=True, header_style="bold magenta")
    table.add_column("Collector ID", style="cyan", width=25)
    table.add_column("Display Name", style="white", width=30)
    table.add_column("Devices", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("Type", style="blue")

    if not aggregator.grpc_servicer:
        table.add_row("No gRPC servicer", "", "", "", "")
        return table

    collectors = aggregator.grpc_servicer.collectors

    if not collectors:
        table.add_row("No collectors connected", "", "", "", "")
        return table

    for collector_id, collector_data in collectors.items():
        display_name = collector_data.display_name
        device_ids = collector_data.device_ids
        status = "CONNECTED"  # Collectors dict only contains connected collectors
        metadata = collector_data.metadata
        collector_type = metadata.get("type", "unknown")

        table.add_row(
            collector_id,
            display_name,
            ", ".join(device_ids) if device_ids else "None",
            status,
            collector_type,
        )

    return table


@app.command()
def run(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to configuration file",
            exists=False,
        ),
    ] = DEFAULT_CONFIG_PATH,
    tui: Annotated[
        bool,
        typer.Option(
            "--tui",
            help="Enable live TUI display (dashboard + logs)",
        ),
    ] = False,
) -> None:
    """Run the ECG Aggregator server.

    Starts both the gRPC server (for collectors) and HTTP/WebSocket server (for API/dashboard).
    By default, shows plain logs. Use --tui for interactive dashboard.
    """
    # Load configuration
    try:
        if config.exists():
            settings = AggregatorSettings.from_yaml(config)
            console.print(f"[green]✓[/green] Loaded configuration from {config}")
        else:
            console.print(f"[yellow]⚠[/yellow] Config file {config} not found, using defaults")
            settings = AggregatorSettings()
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load configuration: {e}")
        raise typer.Exit(1) from e

    # Setup logging with per-run timestamped files
    log_file, ble_debug_file = get_run_log_paths(
        settings.logging.file, settings.logging.ble_debug_file, "aggregator"
    )
    setup_logging(
        level=settings.logging.level,
        log_file=log_file,
        ble_debug_file=ble_debug_file,
        log_format=settings.logging.format,
    )
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_error.handlers.clear()
    uvicorn_access.handlers.clear()
    uvicorn_error.propagate = True
    uvicorn_access.propagate = True

    # Add buffer handler for TUI logs (if --tui enabled)
    if tui:
        buffer_handler = BufferHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        buffer_handler.setFormatter(formatter)
        logging.getLogger().addHandler(buffer_handler)

    # Create aggregator
    aggregator = ECGAggregator(settings)

    # Define async main function
    async def run_with_tui() -> None:
        """Run aggregator with live TUI."""
        # Start aggregator in background task
        aggregator_task = asyncio.create_task(aggregator.start())

        # Wait a bit for services to initialize
        await asyncio.sleep(2)

        # Create shutdown event and mode toggle
        shutdown_event = asyncio.Event()
        show_dashboard = True  # Toggle between dashboard and logs-only

        def signal_handler() -> None:
            logger.info("Received shutdown signal")
            shutdown_event.set()

        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        # Keyboard input handler
        async def keyboard_listener() -> None:
            """Listen for keyboard input to toggle view mode."""
            nonlocal show_dashboard
            loop = asyncio.get_event_loop()

            while not shutdown_event.is_set():
                try:
                    # Read from stdin asynchronously
                    key = await loop.run_in_executor(None, sys.stdin.read, 1)
                    if key.lower() == "d":
                        show_dashboard = not show_dashboard
                        logger.info(
                            f"Toggled to {'dashboard' if show_dashboard else 'logs-only'} mode"
                        )
                    elif key.lower() == "q":
                        shutdown_event.set()
                except Exception:
                    pass
                await asyncio.sleep(0.1)

        # Start keyboard listener
        keyboard_task = asyncio.create_task(keyboard_listener())

        # Run live display
        try:
            console.print("[dim]Press 'd' to toggle dashboard/logs-only view, 'q' to quit[/dim]")

            with Live(console=console, refresh_per_second=2, screen=False) as live:
                while not shutdown_event.is_set():
                    if show_dashboard:
                        # Generate combined display with dashboard + logs
                        layout = Layout()

                        # Split into left (dashboard) and right (logs)
                        layout.split_row(
                            Layout(name="dashboard", ratio=2),
                            Layout(name="logs", ratio=1),
                        )

                        # Dashboard: status + collectors
                        dashboard = Layout()
                        dashboard.split_column(
                            Layout(generate_status_table(aggregator), name="status"),
                            Layout(generate_collectors_table(aggregator), name="collectors"),
                        )

                        layout["dashboard"].update(dashboard)
                        layout["logs"].update(generate_log_panel())

                        live.update(layout)
                    else:
                        # Logs-only mode
                        live.update(generate_log_panel())

                    await asyncio.sleep(0.5)

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")

        finally:
            # Stop keyboard listener
            keyboard_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keyboard_task

            # Stop aggregator
            await aggregator.stop()
            aggregator_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await aggregator_task

    async def run_without_tui() -> None:
        """Run aggregator without TUI (just logs)."""
        try:
            await aggregator.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
        finally:
            await aggregator.stop()

    # Run
    try:
        if tui:
            asyncio.run(run_with_tui())
        else:
            asyncio.run(run_without_tui())
    except Exception as e:
        console.print(f"[red]✗[/red] Aggregator error: {e}")
        raise typer.Exit(1) from e


@app.command()
def status(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to configuration file",
        ),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Show aggregator status (requires aggregator to be running).

    This command is a placeholder for now - in the future it could connect
    to the running aggregator via HTTP API to show status.
    """
    console.print("[yellow]Status command not yet implemented[/yellow]")
    console.print("Use the live display when starting: [cyan]ecg-aggregator run[/cyan]")
    console.print("Or check the API: [cyan]http://localhost:8000/api/status[/cyan]")


def main() -> None:
    """Main entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
