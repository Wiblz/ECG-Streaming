"""Replay collector: re-emits recorded session data from the aggregator SQLite database."""

import asyncio
import contextlib
import signal
import sqlite3
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import grpc
import typer
from ecg_common.proto import collector_aggregator_pb2, collector_aggregator_pb2_grpc, common_pb2
from rich.console import Console
from rich.table import Table

from ecg_simulator import __version__
from ecg_simulator.config import DeviceStats, ReplayConfig, ReplayDevice

console = Console()


def load_session_devices(db_path: Path, session_id: int) -> list[ReplayDevice]:
    """Query the DB and return one ReplayDevice per device present in the session."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise ValueError(f"Session {session_id} not found in {db_path}")

        device_rows = conn.execute(
            """
            SELECT DISTINCT d.id AS db_id, d.device_id, COALESCE(d.nickname, d.device_id) AS nickname
            FROM ecg_samples e
            JOIN devices d ON e.device_id = d.id
            WHERE e.session_id = ?
            ORDER BY d.id
            """,
            (session_id,),
        ).fetchall()

        devices: list[ReplayDevice] = []
        for dr in device_rows:
            ecg = conn.execute(
                """
                SELECT raw_value, global_time, wall_clock_us, receiver_clock_us,
                       device_timestamp, time_verified
                FROM ecg_samples
                WHERE session_id = ? AND device_id = ?
                ORDER BY global_time
                """,
                (session_id, dr["db_id"]),
            ).fetchall()

            acc = conn.execute(
                """
                SELECT x, y, z, global_time, wall_clock_us, receiver_clock_us,
                       device_timestamp, time_verified
                FROM accelerometer_samples
                WHERE session_id = ? AND device_id = ?
                ORDER BY global_time
                """,
                (session_id, dr["db_id"]),
            ).fetchall()

            devices.append(
                ReplayDevice(
                    device_id=dr["device_id"],
                    db_device_id=dr["db_id"],
                    nickname=dr["nickname"],
                    ecg_samples=list(ecg),
                    acc_samples=list(acc),
                )
            )
        return devices
    finally:
        conn.close()


def list_sessions(db_path: Path) -> None:
    """Print a table of all sessions in the database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, start_time, end_time, device_count, sample_count, notes FROM sessions ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        console.print("[yellow]No sessions found.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Sessions in {db_path}")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Start", style="white")
    table.add_column("Duration", justify="right")
    table.add_column("Devices", justify="right")
    table.add_column("Samples", justify="right")
    table.add_column("Notes")

    for row in rows:
        start = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["start_time"]))
        dur = f"{row['end_time'] - row['start_time']:.0f}s" if row["end_time"] else "ongoing"
        table.add_row(
            str(row["id"]),
            start,
            dur,
            str(row["device_count"] or "?"),
            str(row["sample_count"] or "?"),
            row["notes"] or "",
        )

    console.print(table)


class ReplayCollector:
    """Single collector that replays recorded session data through the gRPC pipeline."""

    def __init__(
        self,
        collector_id: str,
        devices: list[ReplayDevice],
        config: ReplayConfig,
    ) -> None:
        self.collector_id = collector_id
        self.display_name = collector_id.replace("-", " ").title()
        self.devices = devices
        self.config = config
        self._message_queue: asyncio.Queue[collector_aggregator_pb2.CollectorMessage | None] = (
            asyncio.Queue()
        )
        self._tasks: list[asyncio.Task[None]] = []
        self._connected = asyncio.Event()
        self._stop_requested = False
        self._stream_error: Exception | None = None
        self._channel: grpc.aio.Channel | None = None
        self._stub: collector_aggregator_pb2_grpc.ECGStreamingServiceStub | None = None

    async def start(self) -> None:
        """Connect and start streaming."""
        target = f"{self.config.host}:{self.config.port}"
        self._channel = grpc.aio.insecure_channel(target)
        try:
            await asyncio.wait_for(
                self._channel.channel_ready(), timeout=self.config.connect_timeout
            )
        except TimeoutError as exc:
            await self._channel.close()
            raise RuntimeError(
                f"Timed out connecting {self.collector_id} to aggregator at {target}"
            ) from exc
        self._stub = collector_aggregator_pb2_grpc.ECGStreamingServiceStub(self._channel)

        stream_task = asyncio.create_task(self._run_stream())
        self._tasks.append(stream_task)

        await self._connected.wait()
        if self._stream_error is not None:
            raise RuntimeError(
                f"Collector {self.collector_id} failed to start: {self._stream_error}"
            ) from self._stream_error

        await self._send_initial_statuses()

        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._tasks.append(asyncio.create_task(self._ecg_replay_loop()))
        if any(d.acc_samples for d in self.devices):
            self._tasks.append(asyncio.create_task(self._acc_replay_loop()))

    async def stop(self) -> None:
        """Stop background work and disconnect."""
        self._stop_requested = True

        for task in self._tasks[1:]:
            task.cancel()
        for task in self._tasks[1:]:
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self._drain_pending_messages()

        for device in self.devices:
            await self._send_status(device, common_pb2.DEVICE_STATUS_DISCONNECTED)

        await self._message_queue.put(None)

        if self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await self._tasks[0]

        if self._channel is not None:
            await self._channel.close()

    async def _run_stream(self) -> None:
        if self._stub is None:
            raise RuntimeError("gRPC stub not initialized")
        try:
            async for response in self._stub.StreamECG(self._message_generator()):
                msg_type = response.WhichOneof("message")
                if msg_type == "registration_ack":
                    ack = response.registration_ack
                    if not ack.accepted:
                        raise RuntimeError(
                            f"Aggregator rejected registration for {self.collector_id}: {ack.message}"
                        )
                    self._connected.set()
                    console.print(
                        f"[green]{self.collector_id}[/green] registered: {ack.message}",
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._stream_error = exc
            if not self._stop_requested:
                console.print(f"[red]{self.collector_id} stream error:[/red] {exc}")
            raise
        finally:
            self._connected.set()

    async def _message_generator(
        self,
    ) -> AsyncGenerator[collector_aggregator_pb2.CollectorMessage]:
        registration = collector_aggregator_pb2.CollectorRegistration(
            collector_id=self.collector_id,
            device_ids=[d.device_id for d in self.devices],
            version=__version__,
            metadata={
                "type": "simulator",
                "simulated": "true",
                "replay": "true",
                "device_count": str(len(self.devices)),
            },
            display_name=self.display_name,
            device_nicknames={d.device_id: d.nickname for d in self.devices},
        )
        yield collector_aggregator_pb2.CollectorMessage(registration=registration)

        while True:
            message = await self._message_queue.get()
            if message is None:
                break
            yield message

    async def _send_initial_statuses(self) -> None:
        for device in self.devices:
            await self._send_status(device, common_pb2.DEVICE_STATUS_CONNECTING)
            await asyncio.sleep(0.05)
            await self._send_status(device, common_pb2.DEVICE_STATUS_CONNECTED)
            await self._send_status(device, common_pb2.DEVICE_STATUS_STREAMING)

    async def _send_status(self, device: ReplayDevice, status: int) -> None:
        status_update = collector_aggregator_pb2.DeviceStatusUpdate(
            device_id=device.device_id,
            status=status,
            battery_level=80,
            device_info={"nickname": device.nickname, "source": "replay"},
        )
        await self._message_queue.put(
            collector_aggregator_pb2.CollectorMessage(status_update=status_update)
        )

    def _drain_pending_messages(self) -> None:
        while True:
            try:
                self._message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _heartbeat_loop(self) -> None:
        while not self._stop_requested:
            await asyncio.sleep(self.config.heartbeat_interval)
            heartbeat = collector_aggregator_pb2.CollectorHeartbeat(
                timestamp_ms=int(time.time() * 1000),
                samples_sent=sum(
                    d.stats.ecg_samples_sent + d.stats.acc_samples_sent for d in self.devices
                ),
                active_devices=len(self.devices),
            )
            await self._message_queue.put(
                collector_aggregator_pb2.CollectorMessage(heartbeat=heartbeat)
            )

    async def _ecg_replay_loop(self) -> None:
        """Stream ECG samples in chronological order, preserving original inter-batch gaps."""
        batch_size = self.config.batch_size
        speed = self.config.speed

        device_samples: dict[str, list] = {d.device_id: d.ecg_samples for d in self.devices}

        if not any(device_samples.values()):
            return

        session_start_time = min(s[0]["global_time"] for s in device_samples.values() if s)

        while not self._stop_requested:
            replay_start_wall = time.monotonic()
            device_cursors: dict[str, int] = {d.device_id: 0 for d in self.devices}

            for device in self.devices:
                device.stats.ecg_samples_sent = 0

            while not self._stop_requested:
                # Find the device whose next batch starts earliest.
                earliest_time: float | None = None
                for device in self.devices:
                    cursor = device_cursors[device.device_id]
                    samples = device_samples[device.device_id]
                    if cursor < len(samples):
                        t = samples[cursor]["global_time"]
                        if earliest_time is None or t < earliest_time:
                            earliest_time = t

                if earliest_time is None:
                    break

                # Sleep until the wall-clock moment corresponding to this sample's session time.
                session_offset = earliest_time - session_start_time
                target_mono = replay_start_wall + session_offset / speed
                wait = target_mono - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)

                if self._stop_requested:
                    break  # type: ignore[unreachable]  # set by stop() in a concurrent coroutine

                # Emit one batch for every device whose next sample is at or before earliest_time.
                # Using earliest_time (not a horizon) ensures we emit exactly the devices that are
                # due now, without skipping any due to floating-point horizon drift.
                now_us = int(time.time() * 1_000_000)
                for device in self.devices:
                    cursor = device_cursors[device.device_id]
                    samples = device_samples[device.device_id]
                    if cursor >= len(samples) or samples[cursor]["global_time"] > earliest_time:
                        continue

                    batch_rows: list[sqlite3.Row] = []
                    while cursor < len(samples) and len(batch_rows) < batch_size:
                        batch_rows.append(samples[cursor])
                        cursor += 1
                    device_cursors[device.device_id] = cursor

                    proto_samples = [
                        common_pb2.ECGSample(
                            value=row["raw_value"],
                            polar_clock_us=int(row["device_timestamp"] * 1_000_000),
                            device_id=device.device_id,
                            wall_clock_us=now_us,
                            receiver_clock_us=row["receiver_clock_us"] or now_us,
                            time_verified=(i == len(batch_rows) - 1),
                        )
                        for i, row in enumerate(batch_rows)
                    ]

                    if len(batch_rows) >= 2:
                        dt = batch_rows[-1]["global_time"] - batch_rows[0]["global_time"]
                        sample_rate = int(round((len(batch_rows) - 1) / dt)) if dt > 0 else 130
                    else:
                        sample_rate = 130

                    await self._message_queue.put(
                        collector_aggregator_pb2.CollectorMessage(
                            ecg_batch=collector_aggregator_pb2.ECGBatch(
                                device_id=device.device_id,
                                wall_clock_us=now_us,
                                batch_timestamp_us=now_us,
                                sample_rate=sample_rate,
                                samples=proto_samples,
                            )
                        )
                    )
                    device.stats.ecg_samples_sent += len(batch_rows)

                await asyncio.sleep(0)  # yield to event loop between iterations

            if not self.config.loop or self._stop_requested:
                break
            console.print(f"[dim]{self.collector_id} ECG replay complete — looping[/dim]")

    async def _acc_replay_loop(self) -> None:
        """Stream accelerometer samples in chronological order."""
        batch_size = self.config.batch_size
        speed = self.config.speed

        device_samples: dict[str, list] = {d.device_id: d.acc_samples for d in self.devices}

        if not any(device_samples.values()):
            return

        session_start_time = min(s[0]["global_time"] for s in device_samples.values() if s)

        while not self._stop_requested:
            replay_start_wall = time.monotonic()
            device_cursors: dict[str, int] = {d.device_id: 0 for d in self.devices}

            for device in self.devices:
                device.stats.acc_samples_sent = 0

            while not self._stop_requested:
                earliest_time: float | None = None
                for device in self.devices:
                    cursor = device_cursors[device.device_id]
                    samples = device_samples[device.device_id]
                    if cursor < len(samples):
                        t = samples[cursor]["global_time"]
                        if earliest_time is None or t < earliest_time:
                            earliest_time = t

                if earliest_time is None:
                    break

                session_offset = earliest_time - session_start_time
                target_mono = replay_start_wall + session_offset / speed
                wait = target_mono - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)

                if self._stop_requested:
                    break  # type: ignore[unreachable]  # set by stop() in a concurrent coroutine

                now_us = int(time.time() * 1_000_000)
                for device in self.devices:
                    cursor = device_cursors[device.device_id]
                    samples = device_samples[device.device_id]
                    if cursor >= len(samples) or samples[cursor]["global_time"] > earliest_time:
                        continue

                    batch_rows: list[sqlite3.Row] = []
                    while cursor < len(samples) and len(batch_rows) < batch_size:
                        batch_rows.append(samples[cursor])
                        cursor += 1
                    device_cursors[device.device_id] = cursor

                    proto_samples = [
                        common_pb2.AccelerometerSample(
                            x=row["x"],
                            y=row["y"],
                            z=row["z"],
                            polar_clock_us=int(row["device_timestamp"] * 1_000_000),
                            device_id=device.device_id,
                            wall_clock_us=now_us,
                            receiver_clock_us=row["receiver_clock_us"] or now_us,
                            time_verified=(i == len(batch_rows) - 1),
                        )
                        for i, row in enumerate(batch_rows)
                    ]

                    if len(batch_rows) >= 2:
                        dt = batch_rows[-1]["global_time"] - batch_rows[0]["global_time"]
                        sample_rate = int(round((len(batch_rows) - 1) / dt)) if dt > 0 else 100
                    else:
                        sample_rate = 100

                    await self._message_queue.put(
                        collector_aggregator_pb2.CollectorMessage(
                            acc_batch=collector_aggregator_pb2.AccelerometerBatch(
                                device_id=device.device_id,
                                wall_clock_us=now_us,
                                batch_timestamp_us=now_us,
                                sample_rate=sample_rate,
                                samples=proto_samples,
                            )
                        )
                    )
                    device.stats.acc_samples_sent += len(batch_rows)

                await asyncio.sleep(0)

            if not self.config.loop or self._stop_requested:
                break
            console.print(f"[dim]{self.collector_id} ACC replay complete — looping[/dim]")


async def run_replay(config: ReplayConfig) -> None:
    """Load a session from SQLite and replay it through the gRPC pipeline."""
    console.print(
        f"[bold]Loading session {config.session_id}[/bold] from [cyan]{config.db_path}[/cyan]…"
    )
    devices = load_session_devices(config.db_path, config.session_id)

    if not devices:
        console.print("[red]No ECG data found for that session.[/red]")
        raise typer.Exit(code=1)

    total_ecg = sum(len(d.ecg_samples) for d in devices)
    total_acc = sum(len(d.acc_samples) for d in devices)
    console.print(f"  {len(devices)} device(s), {total_ecg} ECG samples, {total_acc} ACC samples")
    if total_ecg >= 2:
        duration = max(d.ecg_samples[-1]["global_time"] for d in devices if d.ecg_samples) - min(
            d.ecg_samples[0]["global_time"] for d in devices if d.ecg_samples
        )
        console.print(
            f"  Session duration: {duration:.1f}s "
            f"→ replay at {config.speed}× = {duration / config.speed:.1f}s"
        )

    collector = ReplayCollector(
        collector_id="replay-collector-01",
        devices=devices,
        config=config,
    )
    await collector.start()

    console.print("[bold green]Replay running[/bold green] — press Ctrl-C to stop.")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    report_interval = config.report_interval

    async def progress_reporter() -> None:
        prev_ecg = 0
        prev_acc = 0
        while not stop_event.is_set():
            await asyncio.sleep(report_interval)
            total_e = sum(d.stats.ecg_samples_sent for d in devices)
            total_a = sum(d.stats.acc_samples_sent for d in devices)
            ecg_rate = (total_e - prev_ecg) / report_interval
            acc_rate = (total_a - prev_acc) / report_interval
            console.print(
                f"[dim]sent ECG={total_e} ({ecg_rate:.0f}/s), "
                f"ACC={total_a} ({acc_rate:.0f}/s)[/dim]"
            )
            prev_ecg, prev_acc = total_e, total_a

    reporter = asyncio.create_task(progress_reporter())
    await stop_event.wait()

    console.print("[yellow]Stopping replay…[/yellow]")
    reporter.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await reporter
    await collector.stop()


# Suppress unused import — DeviceStats is re-exported for use by replay.py consumers
__all__ = ["ReplayCollector", "load_session_devices", "list_sessions", "run_replay", "DeviceStats"]
