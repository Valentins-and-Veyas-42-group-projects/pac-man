"""Buffer replay state and dispatch persistence commands."""

from dataclasses import dataclass, field
from typing import final

from .models import CollectibleChange, Frame, FrameBatch, ReplayId
from .writer import Append, Finish, WriterChannel

DEFAULT_BUFFER_SIZE = 256


@final
@dataclass(slots=True)
class Recorder:
    """Buffer replay events and dispatch work to the replay writer."""

    replay_id: ReplayId
    chan: WriterChannel
    buf_size: int = DEFAULT_BUFFER_SIZE

    _frames: list[Frame] = field(
        default_factory=list,
        init=False,
    )

    _collectible_changes: list[CollectibleChange] = field(
        default_factory=list,
        init=False,
    )

    async def on_frame(self, frame: Frame) -> None:
        """Append one frame, flushing when the buffer reaches capacity."""
        self._frames.append(frame)
        if len(self._frames) >= self.buf_size:
            await self.flush()

    def on_collectible_change(
        self,
        change: CollectibleChange,
    ) -> None:
        """Record one collectible change."""
        self._collectible_changes.append(change)

    async def flush(self) -> None:
        """Dispatch buffered replay data as one immutable batch."""
        if not self._frames and not self._collectible_changes:
            return

        batch = FrameBatch(
            replay_id=self.replay_id,
            frames=tuple(self._frames),
            collectible_changes=tuple(self._collectible_changes),
        )

        self._frames.clear()
        self._collectible_changes.clear()

        await self.chan.send(Append(batch))

    async def finish(self) -> None:
        """Flush remaining data and finish the replay."""
        await self.flush()

        await self.chan.send(Finish(self.replay_id))
