"""Tests for ghost mode transitions and per-tick movement."""

from pacman.game.board import Board
from pacman.game.ghosts import (
    FRIGHTENED_TICKS,
    RESPAWN_TICKS,
    _best_direction,
    _legal_directions,
    eat_ghost,
    respawn_ghost,
    set_frightened,
    update_ghost,
)
from pacman.maze_loader import Maze
from pacman.models import Direction, Ghost, GhostMode, GhostName, Player, Position

OPEN_3X3 = Maze(cells=((0, 0, 0), (0, 0, 0), (0, 0, 0)), entry=(0, 0), exit=(2, 2))

# A 3x1 corridor: only LEFT/RIGHT are ever in bounds, UP/DOWN never are.
CORRIDOR = Maze(cells=((0, 0, 0),), entry=(0, 0), exit=(2, 0))

# 3x3 maze whose center cell has every wall bit set (mask 15), boxing a
# ghost in even though the rest of the maze is open around it.
BOXED_CENTER = Maze(cells=((0, 0, 0), (0, 15, 0), (0, 0, 0)), entry=(0, 0), exit=(2, 2))


def _ghost(
    position: Position = Position(0, 0),
    facing: Direction = Direction.DOWN,
    mode: GhostMode = GhostMode.CHASING,
    home: Position = Position(0, 2),
    frightened_timer: int = 0,
    eaten_timer: int = 0,
) -> Ghost:
    return Ghost(
        name=GhostName.BLINKY,
        position=position,
        facing_direction=facing,
        mode=mode,
        home_pos=home,
        frightened_timer=frightened_timer,
        eaten_timer=eaten_timer,
    )


# --- mode transitions -------------------------------------------------


def test_set_frightened_starts_the_edible_window() -> None:
    """Eating a super-pacgum flips the ghost to FRIGHTENED with a full timer."""
    ghost = _ghost(mode=GhostMode.CHASING)

    result = set_frightened(ghost)

    assert result.mode is GhostMode.FRIGHTENED
    assert result.frightened_timer == FRIGHTENED_TICKS


def test_eat_ghost_switches_to_eaten_and_clears_fright_timer() -> None:
    """Eating a frightened ghost starts the respawn delay and stops fright."""
    ghost = _ghost(mode=GhostMode.FRIGHTENED, frightened_timer=120)

    result = eat_ghost(ghost)

    assert result.mode is GhostMode.EATEN
    assert result.eaten_timer == RESPAWN_TICKS
    assert result.frightened_timer == 0


def test_respawn_ghost_returns_home_chasing_with_timers_cleared() -> None:
    """Respawning always lands on the ghost's own home corner."""
    ghost = _ghost(position=Position(2, 2), mode=GhostMode.EATEN, eaten_timer=30, home=Position(0, 2))

    result = respawn_ghost(ghost)

    assert result.position == ghost.home_pos
    assert result.mode is GhostMode.CHASING
    assert result.eaten_timer == 0
    assert result.frightened_timer == 0


# --- chasing / fleeing movement ----------------------------------------


def test_update_ghost_chasing_moves_toward_the_player() -> None:
    """A chasing ghost steps toward the player along the shorter axis."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(2, 0), score=0)
    ghost = _ghost(position=Position(0, 0), facing=Direction.DOWN, mode=GhostMode.CHASING)

    result = update_ghost(ghost, player, board, dt=1 / 60)

    assert result.position == Position(1, 0)
    assert result.facing_direction is Direction.RIGHT
    assert result.mode is GhostMode.CHASING


def test_update_ghost_frightened_moves_away_from_the_player() -> None:
    """A frightened ghost steps away from the player instead of toward it."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(2, 0), score=0)
    ghost = _ghost(
        position=Position(0, 0),
        facing=Direction.DOWN,
        mode=GhostMode.FRIGHTENED,
        frightened_timer=120,
    )

    result = update_ghost(ghost, player, board, dt=1 / 60)

    assert result.position == Position(0, 1)
    assert result.mode is GhostMode.FRIGHTENED
    assert result.frightened_timer == 120 - 1


def test_update_ghost_frightened_timer_expiry_returns_to_chasing() -> None:
    """The tick that empties the fright timer flips mode without moving."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(2, 0), score=0)
    ghost = _ghost(position=Position(0, 0), mode=GhostMode.FRIGHTENED, frightened_timer=1)

    result = update_ghost(ghost, player, board, dt=1 / 60)

    assert result.mode is GhostMode.CHASING
    assert result.frightened_timer == 0
    assert result.position == ghost.position


def test_update_ghost_frightened_large_dt_clamps_instead_of_going_negative() -> None:
    """A huge dt can't drive the fright timer below zero."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(2, 0), score=0)
    ghost = _ghost(position=Position(0, 0), mode=GhostMode.FRIGHTENED, frightened_timer=10)

    result = update_ghost(ghost, player, board, dt=1000)

    assert result.frightened_timer == 0
    assert result.mode is GhostMode.CHASING


# --- eaten / respawn timing --------------------------------------------


def test_update_ghost_eaten_counts_down_without_moving() -> None:
    """While eaten, only the respawn timer changes each tick."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(2, 0), score=0)
    ghost = _ghost(position=Position(1, 1), mode=GhostMode.EATEN, eaten_timer=RESPAWN_TICKS)

    result = update_ghost(ghost, player, board, dt=1 / 60)

    assert result.mode is GhostMode.EATEN
    assert result.eaten_timer == RESPAWN_TICKS - 1
    assert result.position == ghost.position


def test_update_ghost_eaten_large_dt_respawns_at_home() -> None:
    """A huge dt still safely lands the ghost back home, not mid-corridor."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(2, 0), score=0)
    ghost = _ghost(position=Position(1, 1), mode=GhostMode.EATEN, eaten_timer=5, home=Position(0, 2))

    result = update_ghost(ghost, player, board, dt=1000)

    assert result.position == ghost.home_pos
    assert result.mode is GhostMode.CHASING
    assert result.eaten_timer == 0
    assert result.frightened_timer == 0


# --- dead ends, boxed-in ghosts, determinism ----------------------------


def test_legal_directions_excludes_reversal_when_an_alternative_exists() -> None:
    """A ghost mid-corridor should not double back on itself."""
    board = Board(maze=CORRIDOR)
    ghost = _ghost(position=Position(1, 0), facing=Direction.LEFT)

    assert _legal_directions(ghost, board) == [Direction.LEFT]


def test_legal_directions_allows_reversal_at_a_dead_end() -> None:
    """At a dead end, reversing is the only way out, so it must be allowed."""
    board = Board(maze=CORRIDOR)
    ghost = _ghost(position=Position(0, 0), facing=Direction.LEFT)

    assert _legal_directions(ghost, board) == [Direction.RIGHT]


def test_update_ghost_with_no_legal_moves_stays_put_instead_of_crashing() -> None:
    """A ghost walled in on every side must not raise -- it just waits."""
    board = Board(maze=BOXED_CENTER)
    player = Player(position=Position(2, 2), score=0)
    chasing = _ghost(position=Position(1, 1), mode=GhostMode.CHASING)
    frightened = _ghost(position=Position(1, 1), mode=GhostMode.FRIGHTENED, frightened_timer=60)

    chasing_result = update_ghost(chasing, player, board, dt=1 / 60)
    frightened_result = update_ghost(frightened, player, board, dt=1 / 60)

    assert chasing_result.position == Position(1, 1)
    assert frightened_result.position == Position(1, 1)
    assert frightened_result.frightened_timer == 59


def test_best_direction_breaks_ties_deterministically() -> None:
    """Equal-distance candidates resolve to the first in Direction order."""
    ghost = _ghost(position=Position(1, 1))
    target = Position(2, 2)
    # DOWN -> (1, 2), distance 1; RIGHT -> (2, 1), distance 1: a tie.
    directions = [Direction.UP, Direction.DOWN, Direction.RIGHT]

    assert _best_direction(ghost, directions, target, minimize=True) is Direction.DOWN


def test_update_ghost_is_deterministic() -> None:
    """The same inputs always produce the same result -- no hidden state."""
    board = Board(maze=OPEN_3X3)
    player = Player(position=Position(2, 0), score=0)
    ghost = _ghost(position=Position(0, 0))

    first = update_ghost(ghost, player, board, dt=1 / 60)
    second = update_ghost(ghost, player, board, dt=1 / 60)

    assert first == second
