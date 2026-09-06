from pacman.analyze.collectibles import CollectibleStateError, reconstruct_collectibles
from pacman.replay.maze_codec import encode_collectibles, encode_topology
from pacman.replay.models import (
    Collectible,
    CollectibleChange,
    Maze,
    MazeId,
    Tick,
    TileIndex,
)
from typed_errs import Err, Nothing, Some


def collectible_maze() -> Maze:
    return Maze(
        id=MazeId(1),
        width=3,
        height=1,
        topology=encode_topology([[13, 5, 7]]).unwrap(),
        initial_collectibles=encode_collectibles([
            Collectible.PACGUM,
            Collectible.POWER_PELLET,
            Collectible.NONE,
        ]).unwrap(),
        checksum=b"collectible-test",
    )


def test_reconstructs_collectibles_at_requested_tick() -> None:
    changes = (
        CollectibleChange(Tick(4), TileIndex(0), Collectible.NONE),
        CollectibleChange(Tick(8), TileIndex(1), Collectible.NONE),
    )

    field = reconstruct_collectibles(collectible_maze(), changes, Tick(5)).unwrap()

    assert field.tiles == (
        Collectible.NONE,
        Collectible.POWER_PELLET,
        Collectible.NONE,
    )
    assert field.at(TileIndex(1)) == Some(Collectible.POWER_PELLET)
    assert isinstance(field.at(TileIndex(3)), Nothing)


def test_reconstruction_rejects_invalid_change_tile() -> None:
    result = reconstruct_collectibles(
        collectible_maze(),
        (CollectibleChange(Tick(1), TileIndex(3), Collectible.NONE),),
        Tick(1),
    )

    assert isinstance(result, Err)
    assert result.error is CollectibleStateError.INVALID_TILE


def test_reconstruction_rejects_invalid_initial_encoding() -> None:
    maze = collectible_maze()
    invalid = Maze(
        maze.id,
        maze.width,
        maze.height,
        maze.topology,
        b"",
        maze.checksum,
    )

    result = reconstruct_collectibles(invalid, (), Tick(0))

    assert isinstance(result, Err)
    assert result.error is CollectibleStateError.INVALID_ENCODING
