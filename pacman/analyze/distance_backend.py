"""Route distance searches to native code with a Python fallback."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Protocol, cast

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.models import MazeGraph, PathfindingError
from pacman.analyze.pathfinding import bfs, pathfinding_err
from pacman.replay.models import TileIndex


class DistanceBackend(Protocol):
    """Small contract shared by optional distance implementations."""

    def distances(
        self,
        graph: MazeGraph,
        origin: TileIndex,
    ) -> Option[tuple[int, ...]]:
        """Return distances when this backend can complete the search."""
        ...


class DistanceBackendKind(Enum):
    """Available implementations in runtime preference order."""

    NATIVE = "native"
    WASM = "wasm"
    PYTHON = "python"


@lru_cache(maxsize=1)
def _accelerated_backend() -> tuple[DistanceBackendKind, Option[DistanceBackend]]:
    """Load the platform accelerator once.

    Returns:
        The loaded backend, or ``Nothing`` when native code is unavailable.
    """
    try:
        from pacman.analyze.wasm_pathfinding import load_wasm_pathfinding

        loaded_wasm = load_wasm_pathfinding()
        if isinstance(loaded_wasm, Some):
            return DistanceBackendKind.WASM, Some(cast(DistanceBackend, loaded_wasm.value))
    except (ImportError, OSError):
        pass

    try:
        from pacman.analyze.native_pathfinding import load_native_pathfinding

        loaded = load_native_pathfinding()
        if isinstance(loaded, Some):
            return DistanceBackendKind.NATIVE, Some(cast(DistanceBackend, loaded.value))
    except (ImportError, OSError):
        pass
    return DistanceBackendKind.PYTHON, Nothing()


def native_pathfinding_available() -> bool:
    """Report whether a compatible native distance backend was loaded.

    Returns:
        Whether calls can currently use the native implementation.
    """
    kind, backend = _accelerated_backend()
    return kind is DistanceBackendKind.NATIVE and isinstance(backend, Some)


def active_distance_backend() -> DistanceBackendKind:
    """Report the accelerator selected for new distance searches.

    Returns:
        The active native, WASM, or Python backend kind.
    """
    return _accelerated_backend()[0]


def distances(
    graph: MazeGraph,
    origin: TileIndex,
) -> Result[tuple[int, ...], PathfindingError]:
    """Compute distances natively when possible, otherwise use Python BFS.

    Args:
        graph: Immutable maze graph to search.
        origin: Tile from which distances are measured.

    Returns:
        Distances matching the Python reference or an invalid-origin error.
    """
    if not graph.contains(origin):
        return pathfinding_err(PathfindingError.INVALID_ORIGIN)

    _, backend = _accelerated_backend()
    if isinstance(backend, Some):
        native = backend.value.distances(graph, origin)
        if isinstance(native, Some):
            return Ok(native.value)

    reference = bfs(graph, origin)
    if isinstance(reference, Err):
        return pathfinding_err(reference.error)

    return Ok(reference.value.distances)
