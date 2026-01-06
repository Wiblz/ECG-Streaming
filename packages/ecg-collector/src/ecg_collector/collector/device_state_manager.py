"""Device state management with automatic reconnection."""

import asyncio
import contextlib
import time
from enum import Enum

from ecg_common.logging import get_logger
from ecg_common.models import DeviceStatus

from ecg_collector.collector.device_driver import DeviceDriver

logger = get_logger(__name__)


class DeviceConnectionState(Enum):
    """Device connection lifecycle states."""

    IDLE = "idle"  # Not yet attempted
    DISCOVERING = "discovering"  # Scanning for device
    CONNECTING = "connecting"  # Attempting connection
    CONNECTED = "connected"  # Connected but not streaming
    STREAMING = "streaming"  # Connected and streaming
    DISCONNECTED = "disconnected"  # Lost connection
    FAILED = "failed"  # Connection failed, will retry
    ERROR = "error"  # Permanent error


class ManagedDevice:
    """Wrapper for a device with connection state management."""

    def __init__(self, driver: DeviceDriver, max_retry_delay: float = 60.0):
        """Initialize managed device.

        Args:
            driver: Device driver instance
            max_retry_delay: Maximum retry delay in seconds
        """
        self.driver = driver
        self.state = DeviceConnectionState.IDLE
        self.max_retry_delay = max_retry_delay

        # Retry tracking
        self.retry_count = 0
        self.last_connection_attempt = 0.0
        self.last_connected_time = 0.0

        # Sampling task
        self.sampling_task: asyncio.Task | None = None

    @property
    def device_id(self) -> str:
        """Get device ID."""
        return self.driver.device_id

    @property
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self.state in (DeviceConnectionState.CONNECTED, DeviceConnectionState.STREAMING)

    @property
    def should_retry(self) -> bool:
        """Check if device should retry connection."""
        if self.state not in (DeviceConnectionState.FAILED, DeviceConnectionState.DISCONNECTED):
            return False

        # Calculate backoff delay: 2^retry_count seconds, capped at max_retry_delay
        delay = min(float(2**self.retry_count), self.max_retry_delay)
        time_since_attempt = time.time() - self.last_connection_attempt

        return bool(time_since_attempt >= delay)

    def get_retry_delay(self) -> float:
        """Get current retry delay in seconds."""
        return float(min(2**self.retry_count, self.max_retry_delay))


class DeviceStateManager:
    """Manages device connection lifecycle with automatic reconnection."""

    def __init__(self, monitor_interval: float = 5.0):
        """Initialize device state manager.

        Args:
            monitor_interval: How often to check device states (seconds)
        """
        self.monitor_interval = monitor_interval
        self._devices: dict[str, ManagedDevice] = {}
        self._monitor_task: asyncio.Task | None = None
        self._running = False

    def add_device(self, driver: DeviceDriver) -> None:
        """Add a device to manage.

        Args:
            driver: Device driver instance
        """
        if driver.device_id in self._devices:
            logger.warning(f"Device {driver.device_id} already managed")
            return

        managed = ManagedDevice(driver)
        self._devices[driver.device_id] = managed
        logger.info(f"Added device {driver.device_id} to state manager")

    def get_device(self, device_id: str) -> ManagedDevice | None:
        """Get managed device by ID.

        Args:
            device_id: Device ID

        Returns:
            ManagedDevice or None
        """
        return self._devices.get(device_id)

    def get_all_devices(self) -> list[ManagedDevice]:
        """Get all managed devices."""
        return list(self._devices.values())

    def get_connected_devices(self) -> list[ManagedDevice]:
        """Get all currently connected devices."""
        return [d for d in self._devices.values() if d.is_connected]

    async def start(self) -> None:
        """Start the device state monitor."""
        if self._running:
            logger.warning("Device state manager already running")
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Device state manager started")

    async def stop(self) -> None:
        """Stop the device state monitor."""
        logger.info("Stopping device state manager...")
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task

        # Stop all sampling tasks
        for device in self._devices.values():
            if device.sampling_task:
                device.sampling_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await device.sampling_task

        logger.info("Device state manager stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        logger.info("Device monitor loop started")

        while self._running:
            try:
                # Check all devices
                for device in self._devices.values():
                    await self._check_device(device)

                await asyncio.sleep(self.monitor_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(self.monitor_interval)

        logger.info("Device monitor loop stopped")

    async def _check_device(self, device: ManagedDevice) -> None:
        """Check and manage device state.

        Args:
            device: Managed device to check
        """
        # Handle devices that need retry
        if device.state == DeviceConnectionState.IDLE:
            await self._attempt_connection(device)

        elif device.state in (DeviceConnectionState.FAILED, DeviceConnectionState.DISCONNECTED):
            if device.should_retry:
                logger.info(
                    f"Retrying connection for {device.device_id} (attempt {device.retry_count + 1})"
                )
                await self._attempt_connection(device)

        # Check if connected device is actually still connected
        elif (
            device.state in (DeviceConnectionState.CONNECTED, DeviceConnectionState.STREAMING)
            and device.driver._status == DeviceStatus.DISCONNECTED
        ):
            logger.warning(f"Device {device.device_id} disconnected unexpectedly")
            await self._handle_disconnection(device)

    async def _attempt_connection(self, device: ManagedDevice) -> None:
        """Attempt to connect to a device.

        Args:
            device: Managed device
        """
        device.state = DeviceConnectionState.DISCOVERING
        device.last_connection_attempt = time.time()

        try:
            # Try to connect
            success = await device.driver.connect()

            if success:
                device.state = DeviceConnectionState.CONNECTED
                device.retry_count = 0  # Reset retry counter on success
                device.last_connected_time = time.time()
                logger.info(f"Successfully connected to {device.device_id}")

                # Start streaming
                await self._start_streaming(device)

            else:
                device.state = DeviceConnectionState.FAILED
                device.retry_count += 1
                logger.warning(
                    f"Failed to connect to {device.device_id}, "
                    f"will retry in {device.get_retry_delay():.0f}s"
                )

        except Exception as e:
            device.state = DeviceConnectionState.FAILED
            device.retry_count += 1
            logger.error(
                f"Error connecting to {device.device_id}: {e}, "
                f"will retry in {device.get_retry_delay():.0f}s"
            )

    async def _start_streaming(self, device: ManagedDevice) -> None:
        """Start streaming on a device.

        Args:
            device: Managed device
        """
        try:
            success = await device.driver.start_streaming()

            if success:
                device.state = DeviceConnectionState.STREAMING
                logger.info(f"Started streaming on {device.device_id}")
            else:
                logger.error(f"Failed to start streaming on {device.device_id}")
                device.state = DeviceConnectionState.CONNECTED

        except Exception as e:
            logger.error(f"Error starting streaming on {device.device_id}: {e}")
            device.state = DeviceConnectionState.CONNECTED

    async def _handle_disconnection(self, device: ManagedDevice) -> None:
        """Handle device disconnection.

        Args:
            device: Managed device that disconnected
        """
        logger.warning(f"Handling disconnection for {device.device_id}")

        # Cancel sampling task if running
        if device.sampling_task and not device.sampling_task.done():
            device.sampling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await device.sampling_task
            device.sampling_task = None

        device.state = DeviceConnectionState.DISCONNECTED
        device.retry_count = 0  # Reset retry counter for disconnections
        logger.info(f"Device {device.device_id} will attempt reconnection")

    def get_stats(self) -> dict[str, object]:
        """Get device state statistics."""
        stats: dict[str, object] = {
            "total_devices": len(self._devices),
            "connected": sum(1 for d in self._devices.values() if d.is_connected),
            "streaming": sum(
                1 for d in self._devices.values() if d.state == DeviceConnectionState.STREAMING
            ),
            "failed": sum(
                1 for d in self._devices.values() if d.state == DeviceConnectionState.FAILED
            ),
            "disconnected": sum(
                1 for d in self._devices.values() if d.state == DeviceConnectionState.DISCONNECTED
            ),
        }

        devices_info = []
        for device in self._devices.values():
            devices_info.append(
                {
                    "device_id": device.device_id,
                    "state": device.state.value,
                    "retry_count": device.retry_count,
                    "next_retry_seconds": (
                        device.get_retry_delay() - (time.time() - device.last_connection_attempt)
                        if device.state
                        in (DeviceConnectionState.FAILED, DeviceConnectionState.DISCONNECTED)
                        else None
                    ),
                }
            )

        stats["devices"] = devices_info
        return stats
