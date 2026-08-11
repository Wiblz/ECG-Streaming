"""Replay collector: re-emits recorded session data from the aggregator SQLite database."""

import asyncio
import contextlib
import heapq
import signal
import sqlite3
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import grpc
import typer
from ecg_common.proto import collector_aggregator_pb2, collector_aggregator_pb2_grpc, common_pb2
from rich.console import Console
from rich.table import Table

from ecg_simulator import __version__
from ecg_simulator.config import DeviceStats, ReplayConfig, ReplayDevice, ReplayStream

console = Console()

ECG_COLUMNS = """raw_value, global_time, wall_clock_us, receiver_clock_us,
                 device_timestamp, time_verified"""
ACC_COLUMNS = """x, y, z, global_time, wall_clock_us, receiver_clock_us,
                 device_timestamp, time_verified"""

DEFAULT_ECG_RATE = 130
DEFAULT_ACC_RATE = 100

# Fraction of the requested speed below which playback is reported as lagging;
# leaves room for scheduler jitter without flagging healthy replays.
SPEED_LAG_THRESHOLD = 0.95

# Outbound message cap: put() blocks when the aggregator falls behind, so replay
# is paced by actual delivery and memory stays bounded at any --speed.
OUTBOUND_QUEUE_MAXSIZE = 64


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open the database read-only, so a bad path fails instead of creating an empty file."""
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_stream_meta(
    conn: sqlite3.Connection, table: str, session_id: int, db_device_id: int
) -> ReplayStream | None:
    """Return counts and time bounds for one device's stream, or None if it has no samples."""
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS n, MIN(global_time) AS first_t, MAX(global_time) AS last_t
        FROM {table}
        WHERE session_id = ? AND device_id = ?
        """,  # noqa: S608 - table name is a module constant, not user input
        (session_id, db_device_id),
    ).fetchone()
    if row is None or not row["n"]:
        return None
    return ReplayStream(count=row["n"], first_time=row["first_t"], last_time=row["last_t"])


def load_session_devices(db_path: Path, session_id: int) -> list[ReplayDevice]:
    """Return one ReplayDevice per device in the session, with metadata only."""
    conn = _connect_readonly(db_path)
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

        return [
            ReplayDevice(
                device_id=dr["device_id"],
                db_device_id=dr["db_id"],
                nickname=dr["nickname"],
                ecg=_load_stream_meta(conn, "ecg_samples", session_id, dr["db_id"]),
                acc=_load_stream_meta(conn, "accelerometer_samples", session_id, dr["db_id"]),
            )
            for dr in device_rows
        ]
    finally:
        conn.close()


def iter_sample_batches(
    conn: sqlite3.Connection,
    table: str,
    columns: str,
    session_id: int,
    db_device_id: int,
    batch_size: int,
) -> Generator[list[sqlite3.Row]]:
    """Yield successive batches of one device's samples in chronological order.

    The ORDER BY is served by idx_device_time / idx_acc_device_time, so SQLite
    streams rows without materializing a temp b-tree.
    """
    cursor = conn.execute(
        f"""
        SELECT {columns}
        FROM {table}
        WHERE session_id = ? AND device_id = ?
        ORDER BY global_time
        """,  # noqa: S608 - table and columns are module constants, not user input
        (session_id, db_device_id),
    )
    try:
        while batch := cursor.fetchmany(batch_size):
            yield batch
    finally:
        cursor.close()


def list_sessions(db_path: Path) -> None:
    """Print a table of all sessions in the database."""
    conn = _connect_readonly(db_path)
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
            asyncio.Queue(maxsize=OUTBOUND_QUEUE_MAXSIZE)
        )
        self._tasks: list[asyncio.Task[None]] = []
        self._connected = asyncio.Event()
        self._stop_requested = False
        self._stream_error: Exception | None = None
        self._channel: grpc.aio.Channel | None = None
        self._stub: collector_aggregator_pb2_grpc.ECGStreamingServiceStub | None = None
        # Session seconds emitted by the ECG loop; drives the observed-speed readout.
        self.ecg_session_position = 0.0
        # True once a non-looping ECG replay has emitted its last batch.
        self.ecg_replay_done = False
        # Both modalities anchor to the same session start and wall-clock epoch,
        # so ECG and ACC (and successive --loop cycles) stay mutually aligned.
        streams = [s for d in devices for s in (d.ecg, d.acc) if s is not None]
        self._session_start_time = min((s.first_time for s in streams), default=0.0)
        session_end_time = max((s.last_time for s in streams), default=0.0)
        self._session_duration = max(session_end_time - self._session_start_time, 0.0)
        self._replay_epoch = 0.0

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
        self._replay_epoch = time.monotonic()
        self._tasks.append(asyncio.create_task(self._replay_loop("ecg")))
        if any(d.acc for d in self.devices):
            self._tasks.append(asyncio.create_task(self._replay_loop("acc")))

    async def stop(self) -> None:
        """Stop background work and disconnect."""
        self._stop_requested = True

        for task in self._tasks[1:]:
            task.cancel()
        for task in self._tasks[1:]:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                console.print(f"[dim]{self.collector_id} task error during stop: {exc}[/dim]")

        self._drain_pending_messages()

        for device in self.devices:
            await self._send_status(device, common_pb2.DEVICE_STATUS_DISCONNECTED)

        await self._message_queue.put(None)

        if self._tasks:
            try:
                await self._tasks[0]
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                console.print(f"[dim]{self.collector_id} stream error during stop: {exc}[/dim]")

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

    def _build_ecg_message(
        self, device: ReplayDevice, batch_rows: list[sqlite3.Row], now_us: int, sample_rate: int
    ) -> collector_aggregator_pb2.CollectorMessage:
        proto_samples = [
            common_pb2.ECGSample(
                value=row["raw_value"],
                # device_timestamp is stored in microseconds already
                polar_clock_us=int(row["device_timestamp"]),
                device_id=device.device_id,
                wall_clock_us=now_us,
                receiver_clock_us=row["receiver_clock_us"] or now_us,
                time_verified=(i == len(batch_rows) - 1),
            )
            for i, row in enumerate(batch_rows)
        ]
        return collector_aggregator_pb2.CollectorMessage(
            ecg_batch=collector_aggregator_pb2.ECGBatch(
                device_id=device.device_id,
                wall_clock_us=now_us,
                batch_timestamp_us=now_us,
                sample_rate=sample_rate,
                samples=proto_samples,
            )
        )

    def _build_acc_message(
        self, device: ReplayDevice, batch_rows: list[sqlite3.Row], now_us: int, sample_rate: int
    ) -> collector_aggregator_pb2.CollectorMessage:
        proto_samples = [
            common_pb2.AccelerometerSample(
                x=row["x"],
                y=row["y"],
                z=row["z"],
                polar_clock_us=int(row["device_timestamp"]),
                device_id=device.device_id,
                wall_clock_us=now_us,
                receiver_clock_us=row["receiver_clock_us"] or now_us,
                time_verified=(i == len(batch_rows) - 1),
            )
            for i, row in enumerate(batch_rows)
        ]
        return collector_aggregator_pb2.CollectorMessage(
            acc_batch=collector_aggregator_pb2.AccelerometerBatch(
                device_id=device.device_id,
                wall_clock_us=now_us,
                batch_timestamp_us=now_us,
                sample_rate=sample_rate,
                samples=proto_samples,
            )
        )

    async def _replay_loop(self, kind: str) -> None:
        """Stream one modality's samples in chronological order across all devices.

        Devices are scheduled through a heap keyed on each pending batch's session
        time, keeping each emission O(log devices). Batch wall-clock targets are
        absolute offsets from the shared replay epoch, so the ECG and ACC loops
        (and successive --loop cycles) stay mutually aligned.
        """
        is_ecg = kind == "ecg"
        table = "ecg_samples" if is_ecg else "accelerometer_samples"
        columns = ECG_COLUMNS if is_ecg else ACC_COLUMNS
        default_rate = DEFAULT_ECG_RATE if is_ecg else DEFAULT_ACC_RATE
        build_message = self._build_ecg_message if is_ecg else self._build_acc_message

        streamed = [d for d in self.devices if (d.ecg if is_ecg else d.acc) is not None]
        if not streamed:
            return

        batch_size = self.config.batch_size
        speed = self.config.speed

        conn = _connect_readonly(self.config.db_path)
        try:
            cycle = 0
            while not self._stop_requested:
                for device in streamed:
                    if is_ecg:
                        device.stats.ecg_samples_sent = 0
                    else:
                        device.stats.acc_samples_sent = 0

                # heap entries: (batch session time, tiebreaker, device index, batch, generator)
                heap: list[
                    tuple[float, int, int, list[sqlite3.Row], Generator[list[sqlite3.Row]]]
                ] = []
                # Generators hold open cursors, so close them before the connection.
                with contextlib.ExitStack() as generators:
                    for index, device in enumerate(streamed):
                        batches = iter_sample_batches(
                            conn,
                            table,
                            columns,
                            self.config.session_id,
                            device.db_device_id,
                            batch_size,
                        )
                        generators.callback(batches.close)
                        first = next(batches, None)
                        if first:
                            heapq.heappush(
                                heap, (first[0]["global_time"], index, index, first, batches)
                            )

                    tiebreaker = len(streamed)
                    while heap and not self._stop_requested:
                        batch_time, _, index, batch_rows, batches = heapq.heappop(heap)
                        device = streamed[index]

                        session_offset = batch_time - self._session_start_time
                        cycle_offset = cycle * self._session_duration + session_offset
                        target_mono = self._replay_epoch + cycle_offset / speed
                        wait = target_mono - time.monotonic()
                        if wait > 0:
                            await asyncio.sleep(wait)

                        if self._stop_requested:
                            break  # type: ignore[unreachable]  # set by stop() in a concurrent coroutine

                        if len(batch_rows) >= 2:
                            dt = batch_rows[-1]["global_time"] - batch_rows[0]["global_time"]
                            sample_rate = (
                                int(round((len(batch_rows) - 1) / dt)) if dt > 0 else default_rate
                            )
                        else:
                            sample_rate = default_rate

                        now_us = int(time.time() * 1_000_000)
                        await self._message_queue.put(
                            build_message(device, batch_rows, now_us, sample_rate)
                        )
                        if is_ecg:
                            device.stats.ecg_samples_sent += len(batch_rows)
                            self.ecg_session_position = session_offset
                        else:
                            device.stats.acc_samples_sent += len(batch_rows)

                        next_batch = next(batches, None)
                        if next_batch:
                            heapq.heappush(
                                heap,
                                (
                                    next_batch[0]["global_time"],
                                    tiebreaker,
                                    index,
                                    next_batch,
                                    batches,
                                ),
                            )
                            tiebreaker += 1

                        await asyncio.sleep(0)  # yield to event loop between batches

                if not self.config.loop or self._stop_requested:
                    break
                cycle += 1
                console.print(
                    f"[dim]{self.collector_id} {kind.upper()} replay complete — looping[/dim]"
                )

            if is_ecg and not self._stop_requested:
                self.ecg_replay_done = True
        finally:
            conn.close()


async def run_replay(config: ReplayConfig) -> None:
    """Load a session from SQLite and replay it through the gRPC pipeline."""
    console.print(
        f"[bold]Loading session {config.session_id}[/bold] from [cyan]{config.db_path}[/cyan]…"
    )
    devices = load_session_devices(config.db_path, config.session_id)

    if not devices:
        console.print("[red]No ECG data found for that session.[/red]")
        raise typer.Exit(code=1)

    total_ecg = sum(d.ecg.count for d in devices if d.ecg)
    total_acc = sum(d.acc.count for d in devices if d.acc)
    console.print(f"  {len(devices)} device(s), {total_ecg} ECG samples, {total_acc} ACC samples")
    if total_ecg >= 2:
        with_ecg = [d.ecg for d in devices if d.ecg]
        duration = max(s.last_time for s in with_ecg) - min(s.first_time for s in with_ecg)
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
        prev_position = collector.ecg_session_position
        prev_mono = time.monotonic()
        while not stop_event.is_set():
            await asyncio.sleep(report_interval)
            total_e = sum(d.stats.ecg_samples_sent for d in devices)
            total_a = sum(d.stats.acc_samples_sent for d in devices)
            ecg_rate = (total_e - prev_ecg) / report_interval
            acc_rate = (total_a - prev_acc) / report_interval

            # Session seconds emitted per wall-clock second: the speed actually
            # achieved, which falls below --speed once emission cannot keep up.
            position = collector.ecg_session_position
            now_mono = time.monotonic()
            elapsed = now_mono - prev_mono
            advanced = position - prev_position
            if not collector.ecg_replay_done and advanced >= 0 and elapsed > 0:
                observed = advanced / elapsed
                lagging = observed < config.speed * SPEED_LAG_THRESHOLD
                speed_style = "yellow" if lagging else "dim"
                speed_text = (
                    f" [{speed_style}]speed {observed:.2f}×/{config.speed:g}×[/{speed_style}]"
                )
            else:
                # Hide the readout once replay has finished (0.00× would read as
                # lag), and skip the interval spanning a --loop position rewind.
                speed_text = ""

            console.print(
                f"[dim]sent ECG={total_e} ({ecg_rate:.0f}/s), "
                f"ACC={total_a} ({acc_rate:.0f}/s)[/dim]{speed_text}"
            )
            prev_ecg, prev_acc = total_e, total_a
            prev_position, prev_mono = position, now_mono

    reporter = asyncio.create_task(progress_reporter())
    await stop_event.wait()

    console.print("[yellow]Stopping replay…[/yellow]")
    reporter.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await reporter
    await collector.stop()


# Suppress unused import — DeviceStats is re-exported for use by replay.py consumers
__all__ = ["ReplayCollector", "load_session_devices", "list_sessions", "run_replay", "DeviceStats"]
