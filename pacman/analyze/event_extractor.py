"""Extract deterministic factual events from immutable replay batches."""

from dataclasses import dataclass

from typed_errs import Nothing, Option, Some

from pacman.analyze.events import (
    AnalysisEvent,
    BatchFinished,
    CollectibleObserved,
    DeathStarted,
    FrameObserved,
    GhostStateChanged,
    PlayerTurned,
    event_tick,
)
from pacman.replay.models import Frame, FrameBatch, GamePhase, Ghost, GhostState, Maze


@dataclass(frozen=True, slots=True)
class EventExtractorState:
    """Frame retained for detecting transitions across batch boundaries."""

    previous_frame: Option[Frame]


def initial_extractor_state() -> EventExtractorState:
    """Create an extractor without previous replay state.

    Returns:
        Initial immutable extractor state.
    """
    return EventExtractorState(Nothing())


def is_death_phase(phase: GamePhase) -> bool:
    """Return whether a game phase represents player death."""
    return phase in (GamePhase.DYING, GamePhase.LOST)


def ghost_state(frame: Frame, ghost: Ghost) -> Option[GhostState]:
    """Find one ghost's state in a replay frame.

    Returns:
        Matching state or ``Nothing`` when the ghost is absent.
    """
    for value in frame.ghosts:
        if value.ghost is ghost:
            return Some(value.state)
    return Nothing()


def frame_transition_events(
    previous: Option[Frame],
    current: Frame,
    batch: FrameBatch,
    maze: Maze,
) -> tuple[AnalysisEvent, ...]:
    """Extract facts caused by the transition into one frame.

    Returns:
        Frame observation followed by derived transition events.
    """
    events: list[AnalysisEvent] = [FrameObserved(batch.replay_id, current)]
    if isinstance(previous, Nothing):
        if is_death_phase(current.phase):
            events.append(DeathStarted(batch.replay_id, current.tick))
        return tuple(events)

    old = previous.value
    if old.player.direction is not current.player.direction:
        events.append(
            PlayerTurned(
                batch.replay_id,
                current.tick,
                maze.tile_index(current.player.position),
                old.player.direction,
                current.player.direction,
            )
        )

    for ghost in current.ghosts:
        old_state = ghost_state(old, ghost.ghost)
        if isinstance(old_state, Some) and old_state.value is not ghost.state:
            events.append(
                GhostStateChanged(
                    batch.replay_id,
                    current.tick,
                    ghost.ghost,
                    old_state.value,
                    ghost.state,
                )
            )

    if is_death_phase(current.phase) and not is_death_phase(old.phase):
        events.append(DeathStarted(batch.replay_id, current.tick))
    return tuple(events)


def extract_batch_events(
    state: EventExtractorState,
    batch: FrameBatch,
    maze: Maze,
) -> tuple[EventExtractorState, tuple[AnalysisEvent, ...]]:
    """Extract a tick-ordered event stream and retain the final frame.

    Returns:
        Next extractor state and immutable factual events.
    """
    events: list[AnalysisEvent] = [
        CollectibleObserved(batch.replay_id, change) for change in batch.collectible_changes
    ]
    previous = state.previous_frame
    for frame in sorted(batch.frames, key=lambda value: int(value.tick)):
        events.extend(frame_transition_events(previous, frame, batch, maze))
        previous = Some(frame)

    events.sort(key=lambda event: int(event_tick(event)))
    if events:
        events.append(BatchFinished(batch.replay_id, event_tick(events[-1])))
    return EventExtractorState(previous), tuple(events)
