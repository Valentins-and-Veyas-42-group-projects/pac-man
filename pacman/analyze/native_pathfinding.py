"""Optional ctypes bridge to the native distance engine."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path

from typed_errs import Nothing, Option, Some

from pacman.analyze.models import MazeGraph
from pacman.replay.models import TileIndex

PACMAN_ABI_VERSION = 1
PAC_OK = 0
NATIVE_UNREACHABLE = (1 << 32) - 1


class PacMove(ctypes.Structure):
    """C representation of one directed maze move."""

    _fields_ = [
        ("destination", ctypes.c_uint16),
        ("direction", ctypes.c_uint8),
        ("wraparound", ctypes.c_uint8),
    ]


class PacTileNeighbors(ctypes.Structure):
    """C representation of the four possible moves from one tile."""

    _fields_ = [
        ("moves", PacMove * 4),
        ("count", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8),
    ]


class NativePathfinding:
    """Loaded native library with its ctypes contract configured."""

    def __init__(self, library: ctypes.CDLL) -> None:
        """Configure the functions used from a compatible library."""
        self._library = library
        library.pac_abi_version.argtypes = []
        library.pac_abi_version.restype = ctypes.c_uint32
        library.pac_bfs_distances.argtypes = [
            ctypes.POINTER(PacTileNeighbors),
            ctypes.c_size_t,
            ctypes.c_uint16,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t,
        ]
        library.pac_bfs_distances.restype = ctypes.c_int

    def distances(
        self,
        graph: MazeGraph,
        origin: TileIndex,
    ) -> Option[tuple[int, ...]]:
        """Return native distances, or Nothing when native execution fails."""
        try:
            tile_count = len(graph.moves)
            encoded = (PacTileNeighbors * tile_count)()

            for tile, moves in enumerate(graph.moves):
                if len(moves) > 4:
                    return Nothing()

                encoded[tile].count = len(moves)
                for index, move in enumerate(moves):
                    encoded[tile].moves[index] = PacMove(
                        destination=int(move.destination),
                        direction=int(move.direction),
                        wraparound=int(move.wraparound),
                    )

            output = (ctypes.c_uint32 * tile_count)()
            status = self._library.pac_bfs_distances(
                encoded,
                tile_count,
                int(origin),
                output,
                tile_count,
            )

            if status != PAC_OK:
                return Nothing()

            return Some(
                tuple(
                    -1 if value == NATIVE_UNREACHABLE else int(value)
                    for value in output
                )
            )
        except (ArithmeticError, ctypes.ArgumentError, TypeError, ValueError):
            return Nothing()


def _library_candidates() -> tuple[str, ...]:
    """Return explicit, packaged, build-tree, and system library candidates."""
    candidates: list[str] = []
    configured = os.environ.get("PACMAN_NATIVE_LIBRARY")

    if configured:
        candidates.append(configured)

    repository = Path(__file__).resolve().parents[2]
    packaged = Path(__file__).resolve().parent / "lib"

    for directory in (packaged, repository / "build"):
        try:
            candidates.extend(
                str(path) for path in directory.glob("**/libpacman-native.*")
            )
        except OSError:
            continue

    discovered = ctypes.util.find_library("pacman-native")
    if discovered:
        candidates.append(discovered)

    return tuple(dict.fromkeys(candidates))


def load_native_pathfinding() -> Option[NativePathfinding]:
    """Load a compatible native library when one is available.

    Returns:
        The configured backend, or ``Nothing`` when loading is unavailable.
    """
    for candidate in _library_candidates():
        try:
            library = ctypes.CDLL(candidate)
            backend = NativePathfinding(library)

            if library.pac_abi_version() == PACMAN_ABI_VERSION:
                return Some(backend)
        except (AttributeError, OSError):
            continue

    return Nothing()
