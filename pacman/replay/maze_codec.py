"""Compact deterministic codec for persisted maze state.

Maze topology uses four bits per cell because the maze representation
contains four independent wall flags. Collectibles use two bits per
tile, allowing four possible values.

The codec contains no SQLite or replay lifecycle logic.
"""

from enum import Enum
from typing import cast

from python_crimes import match_
from typed_errs import (
    Diagnostic,
    Err,
    Nothing,
    Ok,
    Option,
    Result,
)

from .models import Collectible


CELL_MASK = 0b1111
COLLECTIBLE_MASK = 0b11

NO_CODEC_DIAGNOSTIC: Option[Diagnostic] = Nothing()


class MazeCodecError(Enum):
    """Enumerate failures while encoding or decoding maze state."""

    INVALID_DIMENSIONS = "invalid_dimensions"
    INVALID_CELL = "invalid_cell"
    INVALID_COLLECTIBLE = "invalid_collectible"
    INVALID_DATA_LENGTH = "invalid_data_length"


def codec_err(
    error: MazeCodecError,
    diagnostic: Option[Diagnostic] = NO_CODEC_DIAGNOSTIC,
) -> Err[MazeCodecError]:
    """Create a maze codec error with consistent diagnostic context.

    Args:
        error: Maze codec error category.
        diagnostic: Optional diagnostic information.

    Returns:
        A maze codec error.
    """
    return Err(
        error=error,
        diagnostic=diagnostic,
        namespace="maze_codec",
        context_msg="Maze state codec failed",
    )


def encoded_size(
    item_count: int,
    items_per_byte: int,
) -> int:
    """Return bytes required to encode a fixed number of packed items.

    Args:
        item_count: Number of values being encoded.
        items_per_byte: Number of values packed into each byte.

    Returns:
        Required byte count.
    """
    return (item_count + items_per_byte - 1) // items_per_byte


def valid_cell(cell: int) -> bool:
    """Return whether a maze cell contains only supported wall bits.

    Args:
        cell: Encoded wall flags.

    Returns:
        Whether the cell fits in the four-bit wall representation.
    """
    return cell >= 0 and not bool(cell & ~CELL_MASK)


def valid_collectible(value: int) -> bool:
    """Return whether a value represents a supported collectible.

    Args:
        value: Raw collectible integer.

    Returns:
        Whether the value maps to a known collectible.
    """
    return cast(
        bool,
        (
            match_(value)
            .case(int(Collectible.NONE))
            .then(True)
            .case(int(Collectible.PACGUM))
            .then(True)
            .case(int(Collectible.POWER_PELLET))
            .then(True)
            .default.then(False)
            .value
        ),
    )


def encode_topology(
    cells: list[list[int]],
) -> Result[bytes, MazeCodecError]:
    """Encode maze wall topology using four bits per cell.

    Cells are flattened in row-major order. Two cells are stored in
    each byte, with the first cell in the lower nibble and the second
    in the upper nibble.

    Args:
        cells: Rectangular maze grid containing four-bit wall masks.

    Returns:
        Packed topology bytes or a codec error.
    """
    if not cells or not cells[0]:
        return codec_err(MazeCodecError.INVALID_DIMENSIONS)

    width = len(cells[0])

    if any(len(row) != width for row in cells):
        return codec_err(MazeCodecError.INVALID_DIMENSIONS)

    flat = [cell for row in cells for cell in row]

    if not all(valid_cell(cell) for cell in flat):
        return codec_err(MazeCodecError.INVALID_CELL)

    encoded = bytearray()

    for offset in range(0, len(flat), 2):
        low = flat[offset]
        high = flat[offset + 1] if offset + 1 < len(flat) else 0

        encoded.append(low | (high << 4))

    return Ok(bytes(encoded))


def decode_topology(
    data: bytes,
    width: int,
    height: int,
) -> Result[list[list[int]], MazeCodecError]:
    """Decode packed four-bit maze wall topology.

    Args:
        data: Packed topology bytes.
        width: Maze width in cells.
        height: Maze height in cells.

    Returns:
        Rectangular maze grid or a codec error.
    """
    if width <= 0 or height <= 0:
        return codec_err(MazeCodecError.INVALID_DIMENSIONS)

    cell_count = width * height
    expected = encoded_size(cell_count, items_per_byte=2)

    if len(data) != expected:
        return codec_err(MazeCodecError.INVALID_DATA_LENGTH)

    cells: list[int] = []

    for value in data:
        cells.append(value & CELL_MASK)

        if len(cells) < cell_count:
            cells.append((value >> 4) & CELL_MASK)

    rows = [
        cells[offset : offset + width]
        for offset in range(0, cell_count, width)
    ]

    return Ok(rows)


def encode_collectibles(
    collectibles: list[Collectible],
) -> Result[bytes, MazeCodecError]:
    """Encode collectibles using two bits per tile.

    Four collectible values are packed into each byte in increasing
    two-bit positions.

    Args:
        collectibles: Collectibles in row-major tile order.

    Returns:
        Packed collectible bytes or a codec error.
    """
    encoded = bytearray()

    for offset in range(0, len(collectibles), 4):
        value = 0

        for index in range(4):
            position = offset + index

            if position >= len(collectibles):
                break

            collectible = int(collectibles[position])

            if not valid_collectible(collectible):
                return codec_err(MazeCodecError.INVALID_COLLECTIBLE)

            value |= collectible << (index * 2)

        encoded.append(value)

    return Ok(bytes(encoded))


def decode_collectibles(
    data: bytes,
    count: int,
) -> Result[tuple[Collectible, ...], MazeCodecError]:
    """Decode packed two-bit collectible values.

    Args:
        data: Packed collectible bytes.
        count: Number of collectible tiles expected.

    Returns:
        Decoded collectibles or a codec error.
    """
    if count < 0:
        return codec_err(MazeCodecError.INVALID_DIMENSIONS)

    expected = encoded_size(count, items_per_byte=4)

    if len(data) != expected:
        return codec_err(MazeCodecError.INVALID_DATA_LENGTH)

    collectibles: list[Collectible] = []

    for value in data:
        for shift in range(0, 8, 2):
            if len(collectibles) >= count:
                break

            raw = (value >> shift) & COLLECTIBLE_MASK

            if not valid_collectible(raw):
                return codec_err(MazeCodecError.INVALID_COLLECTIBLE)

            collectibles.append(Collectible(raw))

    return Ok(tuple(collectibles))
