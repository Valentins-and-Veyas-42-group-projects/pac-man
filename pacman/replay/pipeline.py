"""Game-facing replay persistence and live-analysis pipeline."""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import final

from typed_concurrency import Channel, thread
from typed_errs import Err, Ok, Result

from pacman.analyze.messages import AnalysisMessage
from pacman.analyze.runtime.worker import AnalysisOffer, AnalysisWorker
from pacman.analyze.simulation import SimulationRules

from .models import CollectibleChange, Frame, Maze, ReplayId
from .recorder import DEFAULT_BUFFER_SIZE, Recorder
from .store import ReplayStore
from .writer import Append, ReplayWriter, WriterCommand


class ReplayPipelineError(Enum):
    """Failures while creating or closing a replay pipeline."""

    INVALID_CAPACITY = "invalid_capacity"
    ANALYSIS_CREATE_FAILED = "analysis_create_failed"
    ANALYSIS_START_FAILED = "analysis_start_failed"
    ANALYSIS_CLOSE_FAILED = "analysis_close_failed"


def pipeline_err(error: ReplayPipelineError) -> Err[ReplayPipelineError]:
    """Create a consistently contextualized pipeline error.

    Returns:
        Pipeline error with stable context.
    """
    return Err(
        error=error,
        namespace="replay_pipeline",
        context_msg="Failed to manage replay pipeline",
    )


@dataclass(frozen=True, slots=True)
class ReplayPipelineReport:
    """Summary produced after storage and analysis have drained."""

    replay_id: ReplayId
    frames: int
    batches: int
    analyzed_batches: int
    rejected_offers: tuple[AnalysisOffer, ...]
    messages: tuple[AnalysisMessage, ...]


@final
class ReplayPipeline:
    """Fan replay batches out to durable storage and live analysis."""

    def __init__(
        self,
        replay_id: ReplayId,
        store: ReplayStore,
        maze: Maze,
        rules: SimulationRules,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        writer_capacity: int = 4,
        analysis_capacity: int = 32,
    ) -> None:
        """Use :meth:`create` so allocation failures remain typed."""
        self._replay_id = replay_id
        self._channel = Channel[WriterCommand](writer_capacity)
        self._writer = ReplayWriter(store, self._channel)
        self._worker_result = AnalysisWorker.create(maze, rules, analysis_capacity)
        self._recorder = Recorder(replay_id, self, buffer_size)
        self._writer_finished = asyncio.Event()
        self._frames = 0
        self._batches = 0
        self._analyzed_batches = 0
        self._rejected_offers: list[AnalysisOffer] = []
        self._messages: list[AnalysisMessage] = []

    @classmethod
    def create(
        cls,
        replay_id: ReplayId,
        store: ReplayStore,
        maze: Maze,
        rules: SimulationRules,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        writer_capacity: int = 4,
        analysis_capacity: int = 32,
    ) -> Result["ReplayPipeline", ReplayPipelineError]:
        """Allocate a pipeline without starting its worker process.

        Returns:
            Created pipeline or a typed capacity/allocation error.
        """
        if buffer_size <= 0 or writer_capacity <= 0 or analysis_capacity <= 0:
            return pipeline_err(ReplayPipelineError.INVALID_CAPACITY)
        pipeline = cls(
            replay_id,
            store,
            maze,
            rules,
            buffer_size,
            writer_capacity,
            analysis_capacity,
        )
        if isinstance(pipeline._worker_result, Err):
            return pipeline_err(ReplayPipelineError.ANALYSIS_CREATE_FAILED)
        return Ok(pipeline)

    def start(self) -> Result[None, ReplayPipelineError]:
        """Start live analysis before frames enter the pipeline.

        Returns:
            Success or a typed worker startup error.
        """
        if isinstance(self._worker_result, Err):
            return pipeline_err(ReplayPipelineError.ANALYSIS_CREATE_FAILED)
        started = self._worker_result.value.start()
        if isinstance(started, Err):
            return pipeline_err(ReplayPipelineError.ANALYSIS_START_FAILED)
        return Ok(None)

    async def run_storage(self) -> None:
        """Run the storage consumer under the caller's task group."""
        try:
            await self._writer.run()
        finally:
            self._writer_finished.set()

    async def send(self, command: WriterCommand, /) -> None:
        """Persist one recorder command and mirror batches to analysis."""
        await self._channel.send(command)
        if not isinstance(command, Append):
            return

        self._batches += 1
        self._frames += len(command.batch.frames)
        if isinstance(self._worker_result, Err):
            self._rejected_offers.append(AnalysisOffer.WORKER_DEAD)
            return

        offer = self._worker_result.value.offer(command.batch)
        if offer is AnalysisOffer.ACCEPTED:
            self._analyzed_batches += 1
        else:
            self._rejected_offers.append(offer)

    async def on_frame(self, frame: Frame) -> None:
        """Accept one frame from the game loop."""
        await self._recorder.on_frame(frame)

    def on_collectible_change(self, change: CollectibleChange) -> None:
        """Accept one collectible mutation from the game loop."""
        self._recorder.on_collectible_change(change)

    def drain_analysis(self) -> tuple[AnalysisMessage, ...]:
        """Collect analysis messages currently available to the game.

        Returns:
            Messages produced since the previous drain.
        """
        if isinstance(self._worker_result, Err):
            return ()
        messages = self._worker_result.value.drain()
        self._messages.extend(messages)
        return messages

    @property
    def rejected_offer_count(self) -> int:
        """Number of batches rejected by live analysis."""
        return len(self._rejected_offers)

    async def finish(self) -> Result[ReplayPipelineReport, ReplayPipelineError]:
        """Drain persistence, stop analysis, and return its report.

        Returns:
            Final counts and messages, or a typed analysis shutdown error.
        """
        await self._recorder.finish()
        await self._channel.close()
        await self._writer_finished.wait()

        if isinstance(self._worker_result, Err):
            return pipeline_err(ReplayPipelineError.ANALYSIS_CREATE_FAILED)
        closed = await thread(self._worker_result.value.close)
        if isinstance(closed, Err):
            return pipeline_err(ReplayPipelineError.ANALYSIS_CLOSE_FAILED)
        self.drain_analysis()

        return Ok(
            ReplayPipelineReport(
                replay_id=self._replay_id,
                frames=self._frames,
                batches=self._batches,
                analyzed_batches=self._analyzed_batches,
                rejected_offers=tuple(self._rejected_offers),
                messages=tuple(self._messages),
            )
        )
