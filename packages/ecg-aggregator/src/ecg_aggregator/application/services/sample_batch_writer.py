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
        max_buffered_rows: int = 500_000,
    ) -> None:
        self.database = database
        self._ecg_batch_buffer: list[ECGBatchRow] = []
        self._acc_batch_buffer: list[AccBatchRow] = []
        self._max_buffered_rows = max_buffered_rows
        self._dropped_rows = 0
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
                # Swap the buffer out before awaiting so samples appended during the
                # DB write land in a fresh list instead of being cleared unwritten.
                ecg_rows = self._ecg_batch_buffer
                self._ecg_batch_buffer = []
                try:
                    flush_start = time.time()
                    await asyncio.get_running_loop().run_in_executor(
                        None, self.database.add_ecg_samples_batch, ecg_rows
                    )
                    flush_duration = time.time() - flush_start
                    logger.info(
                        "Flushed %d ECG samples to DB in %.3fs (buffer wait: %.2fs)",
                        len(ecg_rows),
                        flush_duration,
                        time_since_flush,
                    )
                except Exception as exc:
                    # Failed rows go back ahead of rows buffered during the await
                    # so chronological order is preserved for the retry.
                    self._ecg_batch_buffer[:0] = ecg_rows
                    self._enforce_backlog_cap(self._ecg_batch_buffer, "ECG")
                    logger.error(
                        "Error flushing ECG batch, %d rows kept for retry: %s",
                        len(self._ecg_batch_buffer),
                        exc,
                    )

            if self._acc_batch_buffer:
                acc_rows = self._acc_batch_buffer
                self._acc_batch_buffer = []
                try:
                    flush_start = time.time()
                    await asyncio.get_running_loop().run_in_executor(
                        None,
                        self.database.add_acc_samples_batch,
                        acc_rows,
                    )
                    flush_duration = time.time() - flush_start
                    logger.info(
                        "Flushed %d ACC samples to DB in %.3fs",
                        len(acc_rows),
                        flush_duration,
                    )
                except Exception as exc:
                    self._acc_batch_buffer[:0] = acc_rows
                    self._enforce_backlog_cap(self._acc_batch_buffer, "ACC")
                    logger.error(
                        "Error flushing ACC batch, %d rows kept for retry: %s",
                        len(self._acc_batch_buffer),
                        exc,
                    )

            self._last_flush_time = current_time

    def _enforce_backlog_cap(
        self, buffer: list[ECGBatchRow] | list[AccBatchRow], kind: str
    ) -> None:
        overflow = len(buffer) - self._max_buffered_rows
        if overflow > 0:
            del buffer[:overflow]
            self._dropped_rows += overflow
            logger.error(
                "%s flush backlog exceeded %d rows; dropped %d oldest (%d dropped total)",
                kind,
                self._max_buffered_rows,
                overflow,
                self._dropped_rows,
            )

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
