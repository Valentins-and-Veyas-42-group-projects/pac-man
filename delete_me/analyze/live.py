"""Disposable model of non-blocking live replay analysis."""

import asyncio
from collections import deque
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import final

from pacman.replay.models import (
    Frame,
    FrameBatch,
    GamePhase,
    Ghost,
    GhostState,
    ReplayId,
    Tick,
)
from typed_errs import Nothing, Option, Some


class AnalysisOffer(Enum):
    """Result of offering a replay batch to live analysis."""

    ACCEPTED = "accepted"
    NEEDS_BACKFILL = "needs_backfill"


class MomentKind(Enum):
    """Cheap events detected while consuming live frames."""

    GHOST_STATE_CHANGED = "ghost_state_changed"
    CONTACT = "contact"
    DEATH = "death"


class DeepJobKind(Enum):
    """Expensive analyses triggered by cheap live observations."""

    INVESTIGATE_CONTACT = "investigate_contact"
    ANALYZE_DEATH = "analyze_death"


class AnalysisPriority(IntEnum):
    """Relative priority of deferred analysis work."""

    HIGH = 0
    MEDIUM = 1
    LOW = 2


@dataclass(frozen=True, slots=True)
class LiveObservation:
    """Cheap derived facts calculated for one replay frame."""

    tick: Tick
    dangerous_ghosts: tuple[Ghost, ...]
    contacting_ghosts: tuple[Ghost, ...]
    phase: GamePhase


@dataclass(frozen=True, slots=True)
class CandidateMoment:
    """Interesting live event retained for later ranking."""

    tick: Tick
    kind: MomentKind


@dataclass(frozen=True, slots=True)
class DeepAnalysisJob:
    """Bounded replay window requiring expensive analysis."""

    replay_id: ReplayId
    kind: DeepJobKind
    priority: AnalysisPriority
    start_tick: Tick
    end_tick: Tick


@dataclass(frozen=True, slots=True)
class BackfillRange:
    """Persisted replay range skipped by the bounded live queue."""

    replay_id: ReplayId
    start_tick: Tick
    end_tick: Tick


@dataclass(frozen=True, slots=True)
class StopAnalysis:
    """Tell the disposable analysis worker to finish."""


AnalysisCommand = FrameBatch | StopAnalysis


@final
class BoundedAnalysisQueue:
    """Offer replay batches without ever blocking their producer."""

    def __init__(self, capacity: int) -> None:
        """Create a bounded analysis command queue."""
        self._queue = asyncio.Queue[AnalysisCommand](maxsize=capacity)
        self._backfills: list[BackfillRange] = []

    def offer(self, batch: FrameBatch) -> AnalysisOffer:
        """Offer a batch immediately, recording overflow for later backfill.

        Returns:
            Whether live analysis accepted the batch or needs a backfill.
        """
        try:
            self._queue.put_nowait(batch)
            return AnalysisOffer.ACCEPTED
        except asyncio.QueueFull:
            if batch.frames:
                self._backfills.append(
                    BackfillRange(
                        batch.replay_id,
                        batch.frames[0].tick,
                        batch.frames[-1].tick,
                    )
                )
            return AnalysisOffer.NEEDS_BACKFILL

    async def receive(self) -> AnalysisCommand:
        """Wait for the next analysis command.

        Returns:
            The next replay batch or stop command.
        """
        return await self._queue.get()

    async def close(self) -> None:
        """Close the mock worker after previously accepted work completes."""
        await self._queue.put(StopAnalysis())

    @property
    def backfills(self) -> tuple[BackfillRange, ...]:
        """Persisted ranges that the worker must reload."""
        return tuple(self._backfills)


@final
class MockLiveReplayAnalyzer:
    """Maintain cheap incremental observations from immutable replay batches."""

    def __init__(self, replay_id: ReplayId, recent_capacity: int = 120) -> None:
        """Create empty state for one replay."""
        self._replay_id = replay_id
        self._previous: Option[Frame] = Nothing()
        self._recent = deque[Frame](maxlen=recent_capacity)
        self._observations: list[LiveObservation] = []
        self._moments: list[CandidateMoment] = []
        self._jobs: list[DeepAnalysisJob] = []

    def consume(self, batch: FrameBatch) -> None:
        """Incrementally derive cheap facts from one replay batch."""
        for frame in batch.frames:
            dangerous = tuple(
                ghost.ghost
                for ghost in frame.ghosts
                if ghost.state not in (GhostState.FRIGHTENED, GhostState.EATEN)
            )
            contact = tuple(
                ghost.ghost
                for ghost in frame.ghosts
                if ghost.ghost in dangerous and ghost.position == frame.player.position
            )
            self._observations.append(LiveObservation(frame.tick, dangerous, contact, frame.phase))

            if self._ghost_states_changed(frame):
                self._moments.append(CandidateMoment(frame.tick, MomentKind.GHOST_STATE_CHANGED))

            if contact and not self._previous_has_contact():
                self._moments.append(CandidateMoment(frame.tick, MomentKind.CONTACT))
                self._jobs.append(
                    self._job(
                        frame.tick,
                        DeepJobKind.INVESTIGATE_CONTACT,
                        AnalysisPriority.MEDIUM,
                    )
                )

            if frame.phase in (GamePhase.DYING, GamePhase.LOST):
                self._moments.append(CandidateMoment(frame.tick, MomentKind.DEATH))
                self._jobs.append(
                    self._job(
                        frame.tick,
                        DeepJobKind.ANALYZE_DEATH,
                        AnalysisPriority.HIGH,
                    )
                )

            self._recent.append(frame)
            self._previous = Some(frame)

    def _previous_has_contact(self) -> bool:
        if isinstance(self._previous, Nothing):
            return False
        return any(
            ghost.position == self._previous.value.player.position
            and ghost.state not in (GhostState.FRIGHTENED, GhostState.EATEN)
            for ghost in self._previous.value.ghosts
        )

    def _ghost_states_changed(self, frame: Frame) -> bool:
        if isinstance(self._previous, Nothing):
            return False
        previous = {ghost.ghost: ghost.state for ghost in self._previous.value.ghosts}
        return any(previous.get(ghost.ghost) != ghost.state for ghost in frame.ghosts)

    def _job(
        self,
        tick: Tick,
        kind: DeepJobKind,
        priority: AnalysisPriority,
    ) -> DeepAnalysisJob:
        start = max(0, int(tick) - len(self._recent))
        return DeepAnalysisJob(
            self._replay_id,
            kind,
            priority,
            Tick(start),
            tick,
        )

    @property
    def observations(self) -> tuple[LiveObservation, ...]:
        """Every cheap observation produced so far."""
        return tuple(self._observations)

    @property
    def moments(self) -> tuple[CandidateMoment, ...]:
        """Candidate moments detected so far."""
        return tuple(self._moments)

    @property
    def jobs(self) -> tuple[DeepAnalysisJob, ...]:
        """Expensive jobs triggered by live observations."""
        return tuple(sorted(self._jobs, key=lambda job: job.priority))


@final
class MockAnalysisWorker:
    """Consume accepted batches independently of their producer."""

    def __init__(
        self,
        queue: BoundedAnalysisQueue,
        analyzer: MockLiveReplayAnalyzer,
    ) -> None:
        """Bind a queue to one incremental analyzer."""
        self._queue = queue
        self._analyzer = analyzer

    async def run(self) -> None:
        """Consume commands until explicitly stopped."""
        while True:
            command = await self._queue.receive()
            if isinstance(command, StopAnalysis):
                return
            self._analyzer.consume(command)
