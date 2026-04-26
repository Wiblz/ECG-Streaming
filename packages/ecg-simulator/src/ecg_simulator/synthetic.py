"""Synthetic collector: generates and streams mathematically modelled ECG/ACC data."""

import asyncio
import contextlib
import math
import signal
import time
from collections.abc import AsyncGenerator

import grpc
from ecg_common.proto import collector_aggregator_pb2, collector_aggregator_pb2_grpc, common_pb2
from rich.console import Console

from ecg_simulator import __version__
from ecg_simulator.config import SimulatedDevice, SimulatorConfig
from ecg_simulator.waveforms import build_collectors, square_wave, tent_pulse, triangle_wave

console = Console()


class SimulatedCollector:
    """Single simulated collector connection."""

    def __init__(
        self,
        collector_id: str,
        devices: list[SimulatedDevice],
        config: SimulatorConfig,
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
        self._sync_ready_seen: set[str] = set()
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
        self._tasks.append(asyncio.create_task(self._ecg_loop()))
        if self.config.include_acc:
            self._tasks.append(asyncio.create_task(self._acc_loop()))

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
        """Run the bidirectional gRPC stream."""
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
                elif msg_type == "sync_status":
                    sync = response.sync_status
                    if sync.sync_ready and self.config.verbose_sync:
                        if sync.device_id in self._sync_ready_seen:
                            continue
                        self._sync_ready_seen.add(sync.device_id)
                        console.print(
                            f"[cyan]{self.collector_id}[/cyan] sync ready for {sync.device_id} "
                            f"(confidence={sync.confidence:.3f}, offset={sync.offset_s:.6f}s)"
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
        """Yield collector messages into the gRPC stream."""
        registration = collector_aggregator_pb2.CollectorRegistration(
            collector_id=self.collector_id,
            device_ids=[device.device_id for device in self.devices],
            version=__version__,
            metadata={
                "type": "simulator",
                "simulated": "true",
                "device_count": str(len(self.devices)),
            },
            display_name=self.display_name,
            device_nicknames={device.device_id: device.nickname for device in self.devices},
        )
        yield collector_aggregator_pb2.CollectorMessage(registration=registration)

        while True:
            message = await self._message_queue.get()
            if message is None:
                break
            yield message

    async def _send_initial_statuses(self) -> None:
        """Register devices as connected and streaming."""
        for device in self.devices:
            await self._send_status(device, common_pb2.DEVICE_STATUS_CONNECTING)
            await asyncio.sleep(self.config.startup_stagger_ms / 1000.0)
            await self._send_status(device, common_pb2.DEVICE_STATUS_CONNECTED)
            await self._send_status(device, common_pb2.DEVICE_STATUS_STREAMING)

    async def _send_status(
        self,
        device: SimulatedDevice,
        status: int,
        error_message: str | None = None,
    ) -> None:
        """Queue a device status update."""
        status_update = collector_aggregator_pb2.DeviceStatusUpdate(
            device_id=device.device_id,
            status=status,
            battery_level=device.battery_level,
            device_info={"nickname": device.nickname, "source": "simulator"},
        )
        if error_message:
            status_update.error_message = error_message

        await self._message_queue.put(
            collector_aggregator_pb2.CollectorMessage(status_update=status_update)
        )
        device.stats.status_sent = True

    def _drain_pending_messages(self) -> None:
        """Discard queued data so shutdown is not blocked behind backlog."""
        while True:
            try:
                self._message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _heartbeat_loop(self) -> None:
        """Emit collector heartbeats periodically."""
        while not self._stop_requested:
            await asyncio.sleep(self.config.heartbeat_interval)
            heartbeat = collector_aggregator_pb2.CollectorHeartbeat(
                timestamp_ms=int(time.time() * 1000),
                samples_sent=sum(
                    device.stats.ecg_samples_sent + device.stats.acc_samples_sent
                    for device in self.devices
                ),
                active_devices=len(self.devices),
            )
            await self._message_queue.put(
                collector_aggregator_pb2.CollectorMessage(heartbeat=heartbeat)
            )

    async def _ecg_loop(self) -> None:
        """Emit ECG batches for all devices."""
        batch_duration_s = self.config.batch_size / self.config.ecg_rate
        loop_start_time = time.time()

        while not self._stop_requested:
            cycle_start = time.monotonic()
            elapsed_real_time = time.time() - loop_start_time

            for device in self.devices:
                samples = self._build_ecg_samples(device, self.config.batch_size, elapsed_real_time)
                current_time_us = int(time.time() * 1_000_000)
                batch = collector_aggregator_pb2.ECGBatch(
                    device_id=device.device_id,
                    wall_clock_us=current_time_us,
                    batch_timestamp_us=current_time_us,
                    sample_rate=self.config.ecg_rate,
                    samples=samples,
                )
                await self._message_queue.put(
                    collector_aggregator_pb2.CollectorMessage(ecg_batch=batch)
                )

            sleep_for = batch_duration_s - (time.monotonic() - cycle_start)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

    async def _acc_loop(self) -> None:
        """Emit accelerometer batches for all devices."""
        batch_duration_s = self.config.batch_size / self.config.acc_rate
        loop_start_time = time.time()

        while not self._stop_requested:
            cycle_start = time.monotonic()
            elapsed_real_time = time.time() - loop_start_time

            for device in self.devices:
                samples = self._build_acc_samples(device, self.config.batch_size, elapsed_real_time)
                current_time_us = int(time.time() * 1_000_000)
                batch = collector_aggregator_pb2.AccelerometerBatch(
                    device_id=device.device_id,
                    wall_clock_us=current_time_us,
                    batch_timestamp_us=current_time_us,
                    sample_rate=self.config.acc_rate,
                    samples=samples,
                )
                await self._message_queue.put(
                    collector_aggregator_pb2.CollectorMessage(acc_batch=batch)
                )

            sleep_for = batch_duration_s - (time.monotonic() - cycle_start)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

    def _build_ecg_samples(
        self,
        device: SimulatedDevice,
        sample_count: int,
        elapsed_real_time: float,
    ) -> list[common_pb2.ECGSample]:
        """Generate synthetic ECG samples."""
        now_us = int(time.time() * 1_000_000)
        step_us = int(1_000_000 / self.config.ecg_rate)

        # Polar clock counts up from device boot; last sample timestamp is most accurate
        base_polar_us = 10_000_000  # Initial device uptime
        last_sample_polar_us = base_polar_us + int(elapsed_real_time * 1_000_000)
        wall_clock_us = now_us
        receiver_clock_us = last_sample_polar_us + device.receiver_clock_offset_us

        samples: list[common_pb2.ECGSample] = []
        for i in range(sample_count):
            # Timestamps count backwards from last sample — matches real collector parser
            polar_clock_us = last_sample_polar_us - (sample_count - i - 1) * step_us

            t = (device.stats.ecg_samples_sent + i) / self.config.ecg_rate
            baseline = 1100.0 * math.sin((2 * math.pi * 1.1 * t) + device.ecg_phase)
            harmonic = 240.0 * math.sin((2 * math.pi * 2.9 * t) + device.ecg_phase * 0.5)
            qrs = 1800.0 * max(0.0, math.sin((2 * math.pi * 1.1 * t) * 3.0)) ** 8
            drift = 80.0 * math.sin(2 * math.pi * 0.08 * t)

            samples.append(
                common_pb2.ECGSample(
                    value=int(baseline + harmonic + qrs + drift),
                    polar_clock_us=polar_clock_us,
                    device_id=device.device_id,
                    wall_clock_us=wall_clock_us,
                    receiver_clock_us=receiver_clock_us,
                    time_verified=(i == sample_count - 1),  # only last sample is verified
                )
            )

        device.stats.ecg_samples_sent += sample_count
        return samples

    def _build_acc_samples(
        self,
        device: SimulatedDevice,
        sample_count: int,
        elapsed_real_time: float,
    ) -> list[common_pb2.AccelerometerSample]:
        """Generate synthetic accelerometer samples with a gait-like pattern."""
        now_us = int(time.time() * 1_000_000)
        step_us = int(1_000_000 / self.config.acc_rate)

        base_polar_us = 10_000_000
        last_sample_polar_us = base_polar_us + int(elapsed_real_time * 1_000_000)
        wall_clock_us = now_us
        receiver_clock_us = last_sample_polar_us + device.receiver_clock_offset_us

        samples: list[common_pb2.AccelerometerSample] = []
        for i in range(sample_count):
            polar_clock_us = last_sample_polar_us - (sample_count - i - 1) * step_us

            t = (device.stats.acc_samples_sent + i) / self.config.acc_rate
            cadence_hz = 1.6 + ((device.acc_phase / (2 * math.pi)) * 0.25)
            cycle = (t * cadence_hz + (device.acc_phase / (2 * math.pi))) % 1.0

            primary_step = tent_pulse(cycle, center=0.18, width=0.10)
            secondary_step = 0.65 * tent_pulse(cycle, center=0.64, width=0.12)
            lateral = triangle_wave(cycle)
            sway = square_wave((cycle + 0.18) % 1.0)
            fine_motion = math.sin((2 * math.pi * 6.0 * t) + device.acc_phase) * 0.015

            samples.append(
                common_pb2.AccelerometerSample(
                    x=0.16 * lateral + fine_motion,
                    y=0.10 * sway + fine_motion * 0.6,
                    z=1.0 + 0.34 * primary_step + 0.20 * secondary_step + 0.025 * lateral,
                    polar_clock_us=polar_clock_us,
                    device_id=device.device_id,
                    wall_clock_us=wall_clock_us,
                    receiver_clock_us=receiver_clock_us,
                    time_verified=(i == sample_count - 1),  # only last sample is verified
                )
            )

        device.stats.acc_samples_sent += sample_count
        return samples


async def run_simulation(config: SimulatorConfig) -> None:
    """Run all simulated collectors until interrupted or duration expires."""
    collector_specs = build_collectors(config)
    collectors = [
        SimulatedCollector(collector_id=collector_id, devices=devices, config=config)
        for collector_id, devices in collector_specs
    ]

    for collector in collectors:
        await collector.start()

    console.print(
        "[bold green]Simulation running[/bold green] "
        f"({config.devices} devices across {config.collectors} collectors)"
    )
    console.print("[dim]Press Ctrl-C to stop.[/dim]")

    stop_event = asyncio.Event()

    def request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, request_stop)

    if config.duration is not None:
        _duration = config.duration

        async def timed_stop() -> None:
            await asyncio.sleep(_duration)
            stop_event.set()

        asyncio.create_task(timed_stop())

    async def progress_reporter() -> None:
        previous_ecg = 0
        previous_acc = 0
        while not stop_event.is_set():
            await asyncio.sleep(config.report_interval)
            total_ecg = sum(
                device.stats.ecg_samples_sent
                for collector in collectors
                for device in collector.devices
            )
            total_acc = sum(
                device.stats.acc_samples_sent
                for collector in collectors
                for device in collector.devices
            )
            ecg_rate = (total_ecg - previous_ecg) / config.report_interval
            acc_rate = (total_acc - previous_acc) / config.report_interval
            previous_ecg = total_ecg
            previous_acc = total_acc
            console.print(
                f"[dim]sent ECG={total_ecg} ({ecg_rate:.0f}/s), "
                f"ACC={total_acc} ({acc_rate:.0f}/s)[/dim]"
            )

    reporter_task = asyncio.create_task(progress_reporter())

    await stop_event.wait()

    console.print("[yellow]Stopping simulation...[/yellow]")
    reporter_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await reporter_task
    for collector in collectors:
        await collector.stop()
