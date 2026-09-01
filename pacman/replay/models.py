"""
Typed replay-domain models.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import NewType


ReplayId = NewType("ReplayId", int)
MazeId = NewType("MazeId", int)
Tick = NewType("Tick", int)
Coord = NewType("Coord", int)
Score = NewType("Score", int)
TileIndex = NewType("TileIndex", int)


class Direction(IntEnum):
    UP = 0
    RIGHT = 1
    DOWN = 2
    LEFT = 3


class Ghost(IntEnum):
    BLINKY = 0
    PINKY = 1
    INKY = 2
    CLYDE = 3


class GhostState(IntEnum):
    SCATTER = 0
    CHASE = 1
    FRIGHTENED = 2
    EATEN = 3


class Collectible(IntEnum):
    NONE = 0
    PACGUM = 1
    POWER_PELLET = 2


class GamePhase(IntEnum):
    PLAYING = 0
    PAUSED = 1
    DYING = 2
    WON = 3
    LOST = 4


@dataclass(frozen=True, slots=True)
class Position:
    x: Coord
    y: Coord


@dataclass(frozen=True, slots=True)
class PlayerFrame:
    position: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class GhostFrame:
    ghost: Ghost
    position: Position
    direction: Direction
    state: GhostState


@dataclass(frozen=True, slots=True)
class CollectibleChange:
    tick: Tick
    tile: TileIndex
    collectible: Collectible


@dataclass(frozen=True, slots=True)
class Frame:
    tick: Tick
    player: PlayerFrame
    ghosts: tuple[GhostFrame, ...]
    score: Score
    lives: int
    phase: GamePhase


@dataclass(frozen=True, slots=True)
class Maze:
    id: MazeId
    width: int
    height: int
    topology: bytes
    initial_collectibles: bytes
    checksum: bytes

    def tile_index(self, position: Position) -> TileIndex:
        return TileIndex(int(position.y) * self.width + int(position.x))

    def position(self, tile: TileIndex) -> Position:
        value = int(tile)

        return Position(
            x=Coord(value % self.width),
            y=Coord(value // self.width),
        )


@dataclass(frozen=True, slots=True)
class GameSnapshot:
    replay_id: ReplayId
    tick: Tick
    maze: Maze
    player: PlayerFrame
    ghosts: tuple[GhostFrame, ...]
    collectibles: bytes
    score: Score
    lives: int
    phase: GamePhase


@dataclass(frozen=True, slots=True)
class FrameBatch:
    replay_id: ReplayId
    frames: tuple[Frame, ...]
    collectible_changes: tuple[CollectibleChange, ...]


@dataclass(frozen=True, slots=True)
class EncodedMaze:
    width: int
    height: int
    entry: tuple[int, int]
    exit: tuple[int, int]
    topology: bytes
    initial_collectibles: bytes
    checksum: bytes


@dataclass(frozen=True, slots=True)
class ReplayMetadata:
    id: ReplayId
    maze_id: MazeId
    started_at: int
    ended_at: int | None
    tick_hz: int
    level: int
    simulation_version: int
    config_hash: bytes
    rng_seed: int
