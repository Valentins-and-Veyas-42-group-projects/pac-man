"""Unit tests for compact replay maze encoding."""

from typing import cast

import pytest
from pacman.replay.maze_codec import (
    MazeCodecError,
    decode_collectibles,
    decode_topology,
    encode_collectibles,
    encode_topology,
)
from pacman.replay.models import Collectible
from typed_errs import Err, Ok


@pytest.mark.parametrize(
    ("cells", "encoded"),
    [
        ([[1]], b"\x01"),
        ([[1, 2], [3, 4]], b"\x21\x43"),
        ([[15, 0, 8]], b"\x0f\x08"),
    ],
)
def test_topology_roundtrip(cells: list[list[int]], encoded: bytes) -> None:
    """Topology packing preserves rectangular cell grids."""
    packed = encode_topology(cells)
    assert packed == Ok(encoded)
    assert decode_topology(encoded, len(cells[0]), len(cells)) == Ok(cells)


@pytest.mark.parametrize("cells", [[], [[]], [[1], [2, 3]]])
def test_encode_topology_rejects_invalid_dimensions(cells: list[list[int]]) -> None:
    """Empty and ragged topology grids are rejected."""
    result = encode_topology(cells)
    assert isinstance(result, Err)
    assert result.error == MazeCodecError.INVALID_DIMENSIONS


@pytest.mark.parametrize("cell", [-1, 16])
def test_encode_topology_rejects_invalid_cells(cell: int) -> None:
    """Only four-bit unsigned wall masks are accepted."""
    result = encode_topology([[cell]])
    assert isinstance(result, Err)
    assert result.error == MazeCodecError.INVALID_CELL


def test_decode_topology_rejects_wrong_length() -> None:
    """Topology data must exactly match its dimensions."""
    result = decode_topology(b"\x00", width=2, height=2)
    assert isinstance(result, Err)
    assert result.error == MazeCodecError.INVALID_DATA_LENGTH


def test_collectible_roundtrip() -> None:
    """Collectible packing preserves values across byte boundaries."""
    collectibles = [
        Collectible.NONE,
        Collectible.PACGUM,
        Collectible.POWER_PELLET,
        Collectible.NONE,
        Collectible.POWER_PELLET,
    ]
    packed = encode_collectibles(collectibles)
    assert isinstance(packed, Ok)
    assert decode_collectibles(packed.value, len(collectibles)) == Ok(tuple(collectibles))


def test_encode_collectibles_rejects_unknown_value() -> None:
    """Values outside the collectible enum are rejected at the boundary."""
    invalid = cast(Collectible, 3)
    result = encode_collectibles([invalid])
    assert isinstance(result, Err)
    assert result.error == MazeCodecError.INVALID_COLLECTIBLE


def test_decode_collectibles_rejects_unknown_value() -> None:
    """Reserved packed collectible values are rejected."""
    result = decode_collectibles(b"\x03", count=1)
    assert isinstance(result, Err)
    assert result.error == MazeCodecError.INVALID_COLLECTIBLE
