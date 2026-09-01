"""Background replay persistence worker."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TypeAlias, cast, final

from python_crimes import match_, type_
from typed_concurrency import Channel, thread

from .models import FrameBatch, ReplayId
from .store import ReplayStore


@dataclass(frozen=True, slots=True)
class Append:
    """Persist a replay batch."""

    batch: FrameBatch


@dataclass(frozen=True, slots=True)
class Finish:
    """Finish a replay."""

    replay_id: ReplayId


WriterCommand: TypeAlias = Append | Finish
WriterChannel: TypeAlias = Channel[WriterCommand]


@final
class ReplayWriter:
    """Serialize replay persistence on a background worker."""

    def __init__(
        self,
        store: ReplayStore,
        channel: WriterChannel,
    ) -> None:
        """Create a writer for one store and command channel."""
        self._store = store
        self._channel = channel

    async def _append(self, command: Append) -> None:
        _ = await thread(self._store.append, command.batch)

    async def _finish(self, command: Finish) -> None:
        _ = await thread(self._store.finish, command.replay_id)

    async def run(self) -> None:
        """Process commands until the channel closes."""
        async for command in self._channel:
            action = cast(
                Awaitable[None],
                (
                    match_(command)
                    .case(type_(Append))
                    .then(self._append)
                    .case(type_(Finish))
                    .then(self._finish)
                    .value
                ),
            )

            await action
