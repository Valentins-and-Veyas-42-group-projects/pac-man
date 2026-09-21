"""Headless tests for the pure layout math."""

import pytest
from pacman.game.actor import CENTER, TILE
from pacman.visualizer.layout import HUD_HEIGHT, MARGIN, Layout


def test_maze_fits_inside_window_and_hud() -> None:
    layout = Layout.compute((900, 900), 21, 21)
    w, h = layout.surface_size
    assert layout.origin[0] >= MARGIN and layout.origin[0] + w <= 900 - MARGIN
    assert layout.origin[1] >= MARGIN and layout.origin[1] + h <= 900 - MARGIN - HUD_HEIGHT


def test_wide_maze_is_limited_by_width() -> None:
    assert Layout.compute((600, 900), 20, 5).cell == (600 - 2 * MARGIN) // 20


def test_screen_and_logical_are_inverses() -> None:
    layout = Layout.compute((900, 700), 15, 11)
    sx, sy = layout.to_screen(3 * TILE + CENTER, 2 * TILE + CENTER)
    lx, ly = layout.to_logical(sx, sy)
    assert lx == pytest.approx(3 * TILE + CENTER, abs=TILE / layout.cell)
    assert ly == pytest.approx(2 * TILE + CENTER, abs=TILE / layout.cell)


def test_tile_at_finds_the_tile_under_a_center() -> None:
    layout = Layout.compute((900, 900), 21, 21)
    assert layout.tile_at(*layout.to_screen(5 * TILE + CENTER, 7 * TILE + CENTER)) == (5, 7)
