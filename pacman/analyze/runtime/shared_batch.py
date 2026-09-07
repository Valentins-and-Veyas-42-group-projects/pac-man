"""Own replay batches encoded into anonymous mmap-backed files."""

import mmap
import os
from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Ok, Result

from pacman.analyze.runtime.ipc_protocol import Sequence, TransferId
from pacman.replay.batch_codec import (
    decode_batch_from,
    encode_batch_into,
    encoded_batch_size,
)
from pacman.replay.models import FrameBatch


class SharedBatchStatus(Enum):
    """Ownership states of one mmap-backed batch."""

    WRITABLE = "writable"
    SEALED = "sealed"
    CLOSED = "closed"


class SharedBatchError(Enum):
    """Failures while owning an mmap-backed replay batch."""

    INVALID_SIZE = "invalid_size"
    CREATE_FAILED = "create_failed"
    ENCODE_FAILED = "encode_failed"
    DECODE_FAILED = "decode_failed"
    SEAL_FAILED = "seal_failed"
    CLOSE_FAILED = "close_failed"
    INVALID_STATE = "invalid_state"


def shared_batch_err(error: SharedBatchError) -> Err[SharedBatchError]:
    """Create a consistently contextualized shared-batch error.

    Returns:
        Shared-batch error with stable namespace and context.
    """
    return Err(
        error=error,
        namespace="shared_batch",
        context_msg="Failed to manage shared replay batch",
    )


def allocate_mapping(
    size: int,
) -> Result[tuple[int, mmap.mmap], SharedBatchError]:
    """Allocate one anonymous memory-backed file and writable mapping.

    Returns:
        Owned file descriptor and mapping or a typed allocation error.
    """
    if size <= 0:
        return shared_batch_err(SharedBatchError.INVALID_SIZE)

    try:
        fd = os.open(
            "/dev/shm",
            os.O_RDWR | os.O_TMPFILE | os.O_CLOEXEC,
            0o600,
        )
    except OSError:
        return shared_batch_err(SharedBatchError.CREATE_FAILED)

    try:
        os.ftruncate(fd, size)
        mapping = mmap.mmap(fd, size, access=mmap.ACCESS_WRITE)
    except (OSError, ValueError):
        try:
            os.close(fd)
        except OSError:
            pass
        return shared_batch_err(SharedBatchError.CREATE_FAILED)

    return Ok((fd, mapping))


@dataclass(slots=True)
class SharedBatch:
    """Own one encoded batch's file descriptor and memory mapping."""

    transfer_id: TransferId
    sequence: Sequence
    fd: int
    mapping: mmap.mmap
    payload_size: int
    status: SharedBatchStatus

    @classmethod
    def create(
        cls,
        transfer_id: TransferId,
        sequence: Sequence,
        batch: FrameBatch,
    ) -> Result["SharedBatch", SharedBatchError]:
        """Allocate shared memory and encode one replay batch into it.

        Returns:
            Writable shared batch or a typed allocation/encoding error.
        """
        size = encoded_batch_size(batch)
        allocated = allocate_mapping(size)
        if isinstance(allocated, Err):
            return allocated

        fd, mapping = allocated.value
        view = memoryview(mapping)
        try:
            encoded = encode_batch_into(batch, view)
        finally:
            view.release()

        if isinstance(encoded, Err):
            mapping.close()
            try:
                os.close(fd)
            except OSError:
                pass
            return shared_batch_err(SharedBatchError.ENCODE_FAILED)

        return Ok(
            cls(
                transfer_id=transfer_id,
                sequence=sequence,
                fd=fd,
                mapping=mapping,
                payload_size=encoded.value,
                status=SharedBatchStatus.WRITABLE,
            )
        )

    def seal(self) -> Result[None, SharedBatchError]:
        """Flush encoded bytes and prevent another logical write phase.

        Returns:
            Success or a typed state/flush error.
        """
        if self.status is not SharedBatchStatus.WRITABLE:
            return shared_batch_err(SharedBatchError.INVALID_STATE)

        try:
            self.mapping.flush()
        except (BufferError, OSError, ValueError):
            return shared_batch_err(SharedBatchError.SEAL_FAILED)

        self.status = SharedBatchStatus.SEALED
        return Ok(None)

    def decode(self) -> Result[FrameBatch, SharedBatchError]:
        """Decode the batch while its mapping remains owned.

        Returns:
            Decoded replay batch or a typed state/codec error.
        """
        if self.status is SharedBatchStatus.CLOSED:
            return shared_batch_err(SharedBatchError.INVALID_STATE)

        view = memoryview(self.mapping)
        try:
            decoded = decode_batch_from(view)
        finally:
            view.release()

        if isinstance(decoded, Err):
            return shared_batch_err(SharedBatchError.DECODE_FAILED)
        return Ok(decoded.value)

    def close(self) -> Result[None, SharedBatchError]:
        """Release the mapping and descriptor exactly once.

        Returns:
            Success, including repeated close, or a typed cleanup error.
        """
        if self.status is SharedBatchStatus.CLOSED:
            return Ok(None)

        try:
            self.mapping.close()
        except (BufferError, OSError, ValueError):
            return shared_batch_err(SharedBatchError.CLOSE_FAILED)

        try:
            os.close(self.fd)
        except OSError:
            return shared_batch_err(SharedBatchError.CLOSE_FAILED)

        self.status = SharedBatchStatus.CLOSED
        return Ok(None)
