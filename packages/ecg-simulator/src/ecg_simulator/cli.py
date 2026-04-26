"""CLI entry point for the ECG simulator."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ecg_simulator import __version__
from ecg_simulator.config import ReplayConfig, SimulatorConfig
from ecg_simulator.replay import list_sessions, run_replay
from ecg_simulator.synthetic import run_simulation

app = typer.Typer(
    name="ecg-simulator",
    help="Synthetic collector simulator for ECG-Streaming",
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"ecg-simulator version {__version__}")
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
    """ECG simulator CLI."""


@app.command()
def run(
    host: Annotated[str, typer.Option("--host", help="Aggregator host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Aggregator gRPC port")] = 50051,
    collectors: Annotated[
        int, typer.Option("--collectors", min=1, help="Simulated collectors")
    ] = 1,
    devices: Annotated[int, typer.Option("--devices", min=1, help="Total simulated devices")] = 20,
    ecg_rate: Annotated[int, typer.Option("--ecg-rate", min=1, help="ECG Hz per device")] = 130,
    acc_rate: Annotated[
        int, typer.Option("--acc-rate", min=1, help="Accelerometer Hz per device")
    ] = 100,
    batch_size: Annotated[
        int, typer.Option("--batch-size", min=1, help="Samples per outbound batch")
    ] = 13,
    connect_timeout: Annotated[
        float, typer.Option("--connect-timeout", min=0.1, help="Aggregator connect timeout seconds")
    ] = 5.0,
    heartbeat_interval: Annotated[
        float, typer.Option("--heartbeat-interval", min=0.1, help="Heartbeat seconds")
    ] = 5.0,
    report_interval: Annotated[
        float, typer.Option("--report-interval", min=0.5, help="Progress report seconds")
    ] = 5.0,
    acc: Annotated[bool, typer.Option("--acc", help="Enable accelerometer streaming")] = False,
    startup_stagger_ms: Annotated[
        int,
        typer.Option("--startup-stagger-ms", min=0, help="Delay between initial device statuses"),
    ] = 50,
    verbose_sync: Annotated[
        bool, typer.Option("--verbose-sync", help="Print per-device sync-ready events once")
    ] = False,
    duration: Annotated[
        float | None, typer.Option("--duration", min=0.1, help="Optional auto-stop seconds")
    ] = None,
) -> None:
    """Run the gRPC simulator against an aggregator."""
    config = SimulatorConfig(
        host=host,
        port=port,
        collectors=collectors,
        devices=devices,
        ecg_rate=ecg_rate,
        acc_rate=acc_rate,
        batch_size=batch_size,
        connect_timeout=connect_timeout,
        heartbeat_interval=heartbeat_interval,
        report_interval=report_interval,
        include_acc=acc,
        startup_stagger_ms=startup_stagger_ms,
        duration=duration,
        verbose_sync=verbose_sync,
    )
    try:
        asyncio.run(run_simulation(config))
    except KeyboardInterrupt:
        console.print("[yellow]Simulation interrupted.[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as exc:
        console.print(f"[red]Simulation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def sessions(
    db: Annotated[
        Path,
        typer.Option(
            "--db", help="Path to aggregator SQLite database", exists=True, dir_okay=False
        ),
    ] = Path("ecg_data.db"),
) -> None:
    """List recorded sessions available for replay."""
    list_sessions(db)


@app.command()
def replay(
    session_id: Annotated[
        int, typer.Argument(help="Session ID to replay (use 'sessions' to list)")
    ],
    db: Annotated[
        Path,
        typer.Option(
            "--db", help="Path to aggregator SQLite database", exists=True, dir_okay=False
        ),
    ] = Path("ecg_data.db"),
    host: Annotated[str, typer.Option("--host", help="Aggregator host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Aggregator gRPC port")] = 50051,
    speed: Annotated[
        float, typer.Option("--speed", min=0.1, help="Playback speed multiplier (1.0 = real-time)")
    ] = 1.0,
    batch_size: Annotated[
        int, typer.Option("--batch-size", min=1, help="Samples per outbound batch")
    ] = 13,
    connect_timeout: Annotated[
        float, typer.Option("--connect-timeout", min=0.1, help="Aggregator connect timeout seconds")
    ] = 5.0,
    heartbeat_interval: Annotated[
        float, typer.Option("--heartbeat-interval", min=0.1, help="Heartbeat seconds")
    ] = 5.0,
    report_interval: Annotated[
        float, typer.Option("--report-interval", min=0.5, help="Progress report seconds")
    ] = 5.0,
    loop: Annotated[bool, typer.Option("--loop", help="Loop the session continuously")] = False,
) -> None:
    """Replay a recorded session from the aggregator database."""
    config = ReplayConfig(
        host=host,
        port=port,
        db_path=db,
        session_id=session_id,
        batch_size=batch_size,
        speed=speed,
        connect_timeout=connect_timeout,
        heartbeat_interval=heartbeat_interval,
        report_interval=report_interval,
        loop=loop,
    )
    try:
        asyncio.run(run_replay(config))
    except KeyboardInterrupt:
        console.print("[yellow]Replay interrupted.[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as exc:
        console.print(f"[red]Replay failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
