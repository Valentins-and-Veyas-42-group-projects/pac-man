from pacman.analyze.event_extractor import extract_batch_events, initial_extractor_state
from pacman.analyze.events import (
    BatchFinished,
    CollectibleObserved,
    DeathStarted,
    FrameObserved,
    GhostStateChanged,
    PlayerTurned,
    event_tick,
)
from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Coord,
    Direction,
    Frame,
    FrameBatch,
    GamePhase,
    Ghost,
    GhostFrame,
    GhostState,
    Maze,
    MazeId,
    PlayerFrame,
    Position,
    ReplayId,
    Score,
    Tick,
    TileIndex,
)


def maze() -> Maze:
    return Maze(MazeId(1), 3, 1, b"", b"", b"events-test")


def frame(
    tick: int,
    direction: Direction = Direction.RIGHT,
    phase: GamePhase = GamePhase.PLAYING,
    ghost_state: GhostState = GhostState.CHASE,
) -> Frame:
    return Frame(
        Tick(tick),
        PlayerFrame(Position(Coord(1), Coord(0)), direction),
        (
            GhostFrame(
                Ghost.BLINKY,
                Position(Coord(2), Coord(0)),
                Direction.LEFT,
                ghost_state,
            ),
        ),
        Score(0),
        3,
        phase,
    )


def batch(*frames: Frame) -> FrameBatch:
    return FrameBatch(ReplayId(1), frames, ())


def test_first_frame_is_observed_and_batch_is_finished() -> None:
    current = frame(10)

    state, events = extract_batch_events(initial_extractor_state(), batch(current), maze())

    assert events == (
        FrameObserved(ReplayId(1), current),
        BatchFinished(ReplayId(1), Tick(10)),
    )
    assert state.previous_frame.unwrap() == current


def test_transitions_continue_across_batch_boundaries() -> None:
    state, _ = extract_batch_events(initial_extractor_state(), batch(frame(10)), maze())
    changed = frame(11, Direction.DOWN, ghost_state=GhostState.FRIGHTENED)

    _, events = extract_batch_events(state, batch(changed), maze())

    assert events == (
        FrameObserved(ReplayId(1), changed),
        PlayerTurned(
            ReplayId(1),
            Tick(11),
            TileIndex(1),
            Direction.RIGHT,
            Direction.DOWN,
        ),
        GhostStateChanged(
            ReplayId(1),
            Tick(11),
            Ghost.BLINKY,
            GhostState.CHASE,
            GhostState.FRIGHTENED,
        ),
        BatchFinished(ReplayId(1), Tick(11)),
    )


def test_death_transition_is_emitted_once() -> None:
    _, events = extract_batch_events(
        initial_extractor_state(),
        batch(
            frame(10),
            frame(11, phase=GamePhase.DYING),
            frame(12, phase=GamePhase.DYING),
            frame(13, phase=GamePhase.LOST),
        ),
        maze(),
    )

    assert sum(isinstance(event, DeathStarted) for event in events) == 1


def test_frames_and_collectibles_are_globally_tick_ordered() -> None:
    replay_batch = FrameBatch(
        ReplayId(1),
        (frame(12), frame(14)),
        (
            CollectibleChange(Tick(13), TileIndex(0), Collectible.NONE),
            CollectibleChange(Tick(11), TileIndex(1), Collectible.NONE),
        ),
    )

    _, events = extract_batch_events(initial_extractor_state(), replay_batch, maze())

    assert tuple(int(event_tick(event)) for event in events) == (11, 12, 13, 14, 14)
    assert isinstance(events[0], CollectibleObserved)
    assert isinstance(events[-1], BatchFinished)
