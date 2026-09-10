"""Optional ctypes bridge to the native distance engine."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path

from typed_errs import Nothing, Option, Some

from pacman.analyze.models import MazeGraph
from pacman.replay.models import TileIndex

PACMAN_ABI_VERSION = 2
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
            ctypes.c_size_t,
            ctypes.c_uint16,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t,
        ]
        library.pac_bfs_distances.restype = ctypes.c_int
        library.pac_bfs_distances_graph.argtypes = [
            ctypes.POINTER(PacTileNeighbors),
            ctypes.c_size_t,
            ctypes.c_uint16,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t,
        ]
        library.pac_bfs_distances_graph.restype = ctypes.c_int
        library.pac_topology_create.argtypes = [
            ctypes.POINTER(PacTileNeighbors),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        library.pac_topology_create.restype = ctypes.c_int
        library.pac_topology_destroy.argtypes = [ctypes.c_void_p]
        library.pac_topology_destroy.restype = None
        library.pac_topology_bfs_distances.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t,
        ]
        library.pac_topology_bfs_distances.restype = ctypes.c_int
        self._topologies: dict[int, tuple[MazeGraph, ctypes.c_void_p]] = {}

    @staticmethod
    def _encode(graph: MazeGraph) -> Option[ctypes.Array[PacTileNeighbors]]:
        """Encode one immutable Python graph for the C boundary.

        Returns:
            Encoded C records, or Nothing for an unsupported graph.
        """
        tile_count = len(graph.moves)
        encoded = (PacTileNeighbors * tile_count)()
        for tile, moves in enumerate(graph.moves):
            if len(moves) > 4:
                return Nothing()
            encoded[tile].count = len(moves)
            for index, move in enumerate(moves):
                encoded[tile].moves[index] = PacMove(int(move.destination), int(move.direction), int(move.wraparound))
        return Some(encoded)

    @staticmethod
    def _decode(output: ctypes.Array[ctypes.c_uint32]) -> tuple[int, ...]:
        """Translate the native unreachable sentinel into the Python value.

        Returns:
            Distances using negative one for unreachable tiles.
        """
        return tuple(-1 if value == NATIVE_UNREACHABLE else int(value) for value in output)

    def _topology_for(self, graph: MazeGraph) -> Option[ctypes.c_void_p]:
        """Return a cached owned topology, constructing it only once."""
        cached = self._topologies.get(id(graph))
        if cached is not None:
            cached_graph, pointer = cached
            if cached_graph is graph:
                return Some(pointer)
        encoded = self._encode(graph)
        if isinstance(encoded, Nothing):
            return Nothing()
        pointer = ctypes.c_void_p()
        status = self._library.pac_topology_create(encoded.value, len(graph.moves), graph.width, ctypes.byref(pointer))
        if status != PAC_OK or pointer.value is None:
            return Nothing()
        self._topologies[id(graph)] = (graph, pointer)
        return Some(pointer)

    def distances(
        self,
        graph: MazeGraph,
        origin: TileIndex,
    ) -> Option[tuple[int, ...]]:
        """Return native distances, or Nothing when native execution fails."""
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            tile_count = len(graph.moves)
            output = (ctypes.c_uint32 * tile_count)()
            status = self._library.pac_topology_bfs_distances(topology.value, int(origin), output, tile_count)
            if status != PAC_OK:
                return Nothing()
            return Some(self._decode(output))
        except Exception:
            return Nothing()

    def one_shot_distances(self, graph: MazeGraph, origin: TileIndex, *, masked: bool) -> Option[tuple[int, ...]]:
        """Run an uncached graph or masked implementation for benchmarks.

        Returns:
            Computed distances, or Nothing when the native call fails.
        """
        try:
            encoded = self._encode(graph)
            if isinstance(encoded, Nothing):
                return Nothing()
            count = len(graph.moves)
            output = (ctypes.c_uint32 * count)()
            if masked:
                status = self._library.pac_bfs_distances(encoded.value, count, graph.width, int(origin), output, count)
            else:
                status = self._library.pac_bfs_distances_graph(encoded.value, count, int(origin), output, count)
            return Some(self._decode(output)) if status == PAC_OK else Nothing()
        except Exception:
            return Nothing()

    def close(self) -> None:
        """Release every cached native topology."""
        for _, topology in self._topologies.values():
            self._library.pac_topology_destroy(topology)
        self._topologies.clear()

    def __del__(self) -> None:
        """Release cached native ownership during interpreter cleanup."""
        try:
            self.close()
        except Exception:
            pass


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
            candidates.extend(str(path) for path in directory.glob("**/libpacman-native.*"))
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
