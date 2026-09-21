"""Tests for delta-time actor movement."""

import pytest
from pacman.game.actor import CENTER, SPEED, TILE, Actor
from pacman.maze_loader import Maze, Wall
from pacman.models import Direction

N, E, S, W = Wall.NORTH, Wall.EAST, Wall.SOUTH, Wall.WEST
FRAME = 1 / 60


def corridor() -> Maze:
    """A 3x1 corridor: open east-west, walled north and south."""
    return Maze(cells=[[N | S | W, N | S, N | S | E]], entry=(0, 0), exit=(2, 0))


def corner() -> Maze:
    """An L: (0,0)-(1,0) open east-west, (1,0)-(1,1) open north-south."""
    return Maze(cells=[[N | S | W, N | E], [N | S | W, S | E | W]], entry=(0, 0), exit=(1, 1))


def test_spawns_centered_and_still() -> None:
    actor = Actor((1, 0))
    assert actor.pixel == (TILE + CENTER, CENTER)
    assert actor.aligned and actor.heading is None


def test_speed_is_pixels_per_second() -> None:
    maze, actor = corridor(), Actor((0, 0))
    actor.wanted = Direction.RIGHT
    actor.update(maze, 0.25)
    assert actor.pixel == pytest.approx((CENTER + SPEED * 0.25, CENTER))


def test_frame_rate_does_not_change_where_you_end_up() -> None:
    fast, slow = Actor((0, 0)), Actor((0, 0))
    fast.wanted = slow.wanted = Direction.RIGHT
    for _ in range(90):
        fast.update(corridor(), 1 / 240)
    for _ in range(30):
        slow.update(corridor(), 1 / 80)
    assert fast.tile == slow.tile
    assert fast.pixel == pytest.approx(slow.pixel)


def test_reports_every_tile_crossed_in_one_long_update() -> None:
    actor = Actor((0, 0))
    actor.wanted = Direction.RIGHT
    assert actor.update(corridor(), 10.0) == [(1, 0), (2, 0)]


def test_stops_exactly_at_wall_even_with_a_huge_dt() -> None:
    actor = Actor((0, 0))
    actor.wanted = Direction.RIGHT
    actor.update(corridor(), 100.0)
    assert actor.pixel == (2 * TILE + CENTER, CENTER)
    assert actor.aligned and actor.heading is None


def test_blocked_input_is_ignored() -> None:
    actor = Actor((0, 0))
    actor.wanted = Direction.UP
    assert actor.update(corridor(), 1.0) == []
    assert actor.pixel == (CENTER, CENTER) and actor.heading is None


def test_buffered_turn_happens_at_tile_center_not_before() -> None:
    maze, actor = corner(), Actor((0, 0))
    actor.wanted = Direction.RIGHT
    actor.update(maze, 5 / SPEED)
    actor.wanted = Direction.DOWN  # pressed early, mid-tile
    actor.update(maze, 5 / SPEED)
    assert actor.heading is Direction.RIGHT and actor.pixel[1] == CENTER
    actor.update(maze, 1.0)  # reaches (1, 0), turns south, walks to (1, 1)
    assert actor.tile == (1, 1) and actor.pixel == (TILE + CENTER, TILE + CENTER)


def test_can_reverse_between_tiles_without_moving_the_pixel() -> None:
    maze, actor = corridor(), Actor((0, 0))
    actor.wanted = Direction.RIGHT
    actor.update(maze, 5 / SPEED)
    before = actor.pixel
    actor.wanted = Direction.LEFT
    actor.update(maze, 0.0001)
    assert actor.heading is Direction.LEFT
    assert actor.pixel[0] == pytest.approx(before[0], abs=0.01)
    actor.update(maze, 1.0)
    assert actor.tile == (0, 0) and actor.aligned
