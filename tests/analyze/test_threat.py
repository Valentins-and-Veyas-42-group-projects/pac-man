from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.state import GhostDistance
from pacman.analyze.threat import (
    NO_THREAT,
    ThreatError,
    build_threat_field,
)
from pacman.replay.models import Direction, Ghost, TileIndex
from typed_errs import Err, Nothing, Some


def corridor_graph() -> MazeGraph:
    return MazeGraph(
        width=5,
        height=1,
        moves=(
            (Move(TileIndex(1), Direction.RIGHT),),
            (
                Move(TileIndex(0), Direction.LEFT),
                Move(TileIndex(2), Direction.RIGHT),
            ),
            (
                Move(TileIndex(1), Direction.LEFT),
                Move(TileIndex(3), Direction.RIGHT),
            ),
            (
                Move(TileIndex(2), Direction.LEFT),
                Move(TileIndex(4), Direction.RIGHT),
            ),
            (Move(TileIndex(3), Direction.LEFT),),
        ),
    )


def test_threat_field_combines_dangerous_ghost_arrivals() -> None:
    ghosts = (
        GhostDistance(Ghost.BLINKY, TileIndex(0), 2, True),
        GhostDistance(Ghost.PINKY, TileIndex(4), 2, True),
        GhostDistance(Ghost.INKY, TileIndex(2), 0, False),
    )
    threat = build_threat_field(corridor_graph(), ghosts).unwrap()

    assert threat.etas == (0, 1, 2, 1, 0)
    assert threat.eta(TileIndex(2)) == Some(2)
    assert threat.owners(TileIndex(0)) == (Ghost.BLINKY,)
    assert threat.owners(TileIndex(2)) == (Ghost.BLINKY, Ghost.PINKY)
    assert threat.owners(TileIndex(4)) == (Ghost.PINKY,)
    assert Ghost.INKY not in {ghost for tile_owners in threat.ghosts for ghost in tile_owners}


def test_threat_field_without_dangerous_ghosts_has_no_arrivals() -> None:
    ghosts = (GhostDistance(Ghost.INKY, TileIndex(2), 0, False),)
    threat = build_threat_field(corridor_graph(), ghosts).unwrap()

    assert threat.etas == (NO_THREAT,) * 5
    assert threat.ghosts == ((),) * 5
    assert isinstance(threat.eta(TileIndex(0)), Nothing)
    assert isinstance(threat.eta(TileIndex(-1)), Nothing)
    assert threat.owners(TileIndex(5)) == ()


def test_threat_field_rejects_invalid_dangerous_ghost_tile() -> None:
    ghosts = (GhostDistance(Ghost.CLYDE, TileIndex(5), 0, True),)
    result = build_threat_field(corridor_graph(), ghosts)

    assert isinstance(result, Err)
    assert result.error is ThreatError.INVALID_GHOST_TILE
