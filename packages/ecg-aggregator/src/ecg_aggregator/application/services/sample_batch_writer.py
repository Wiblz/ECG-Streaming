"""Batched sample persistence support."""

import asyncio
import contextlib
import time

from ecg_common.logging import get_logger

from ecg_aggregator.infrastructure.persistence.batch_rows import AccBatchRow, ECGBatchRow
from ecg_aggregator.infrastructure.persistence.sqlite_database import ECGDatabase

logger = get_logger(__name__)


class SampleBatchWriter:
    """Own batched sample accumulation and periodic flush."""

    def __init__(
        self,
        database: ECGDatabase | None,
        *,
        batch_size_threshold: int = 750,
        batch_time_threshold: float = 0.5,
    ) -> None:
        self.database = database
        self._ecg_batch_buffer: list[ECGBatchRow] = []
        self._acc_batch_buffer: list[AccBatchRow] = []
        self._last_flush_time = time.time()
        self._flush_lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._batch_size_threshold = batch_size_threshold
        self._batch_time_threshold = batch_time_threshold

    def add_ecg_sample(self, row: ECGBatchRow) -> None:
        """Buffer an ECG sample for the next flush."""
        self._ecg_batch_buffer.append(row)

    def add_acc_sample(self, row: AccBatchRow) -> None:
        """Buffer an accelerometer sample for the next flush."""
        self._acc_batch_buffer.append(row)

    async def flush(self, force: bool = False) -> None:
        """Flush accumulated samples to the database."""
        if not self.database:
            return

        async with self._flush_lock:
            current_time = time.time()
            time_since_flush = current_time - self._last_flush_time
            should_flush = force or (
                (len(self._ecg_batch_buffer) + len(self._acc_batch_buffer))
                >= self._batch_size_threshold
                or time_since_flush >= self._batch_time_threshold
            )
            if not should_flush:
                return

            if self._ecg_batch_buffer:
                ecg_count = len(self._ecg_batch_buffer)
                try:
                    flush_start = time.time()
                    await asyncio.get_running_loop().run_in_executor(
                        None, self.database.add_ecg_samples_batch, self._ecg_batch_buffer.copy()
                    )
                    flush_duration = time.time() - flush_start
                    self._ecg_batch_buffer.clear()
                    logger.info(
                        "Flushed %d ECG samples to DB in %.3fs (buffer wait: %.2fs)",
                        ecg_count,
                        flush_duration,
                        time_since_flush,
                    )
                except Exception as exc:
                    logger.error("Error flushing ECG batch: %s", exc)

            if self._acc_batch_buffer:
                acc_count = len(self._acc_batch_buffer)
                try:
                    flush_start = time.time()
                    await asyncio.get_running_loop().run_in_executor(
                        None,
                        self.database.add_acc_samples_batch,
                        self._acc_batch_buffer.copy(),
                    )
                    flush_duration = time.time() - flush_start
                    self._acc_batch_buffer.clear()
                    logger.info(
                        "Flushed %d ACC samples to DB in %.3fs",
                        acc_count,
                        flush_duration,
                    )
                except Exception as exc:
                    logger.error("Error flushing ACC batch: %s", exc)

            self._last_flush_time = current_time

    async def _periodic_flush_task(self) -> None:
        """Flush the sample buffers periodically."""
        try:
            while True:
                await asyncio.sleep(self._batch_time_threshold)
                await self.flush()
        except asyncio.CancelledError:
            logger.info("Periodic flush task cancelled, flushing remaining samples...")
            await self.flush(force=True)
            raise

    def start(self) -> None:
        """Start periodic flushing."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._periodic_flush_task())
            logger.info("Started periodic flush task")

    async def stop(self) -> None:
        """Stop periodic flushing and flush any remaining samples."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
            logger.info("Stopped periodic flush task")
