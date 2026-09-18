"""Route distance searches to native code with a Python fallback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Protocol, cast, runtime_checkable

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.models import MazeGraph, Path, PathfindingError
from pacman.analyze.pathfinding import bfs, path_from_distances, pathfinding_err
from pacman.replay.models import Ghost, TileIndex


class GhostOriginLike(Protocol):
    """Ghost fields required by accelerated threat analysis."""

    @property
    def ghost(self) -> Ghost:
        """Ghost identity."""
        ...

    @property
    def tile(self) -> TileIndex:
        """Current tile."""
        ...

    @property
    def dangerous(self) -> bool:
        """Whether this ghost contributes to danger."""
        ...


@dataclass(frozen=True, slots=True)
class AcceleratedThreatAnalysis:
    """Distance data returned by a native or WASM engine."""

    player_distances: tuple[int, ...]
    threat_etas: tuple[int, ...]
    threat_owner_masks: tuple[int, ...]


class DistanceBackend(Protocol):
    """Small contract shared by optional distance implementations."""

    def distances(
        self,
        graph: MazeGraph,
        origin: TileIndex,
    ) -> Option[tuple[int, ...]]:
        """Return distances when this backend can complete the search."""
        ...


@runtime_checkable
class ThreatBackend(Protocol):
    """Optional coarse threat operation implemented by accelerators."""

    def analyze_distances(
        self,
        graph: MazeGraph,
        player_origin: TileIndex,
        ghosts: tuple[GhostOriginLike, ...],
    ) -> Option[AcceleratedThreatAnalysis]:
        """Return combined player and ghost distances when supported."""
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


def accelerated_threat_analysis(
    graph: MazeGraph,
    player_origin: TileIndex,
    ghosts: tuple[GhostOriginLike, ...],
) -> Option[AcceleratedThreatAnalysis]:
    """Run coarse threat analysis when the selected backend supports it.

    Returns:
        Accelerated results, or Nothing when the operation is unavailable.
    """
    _, backend = _accelerated_backend()
    if isinstance(backend, Some) and isinstance(backend.value, ThreatBackend):
        return backend.value.analyze_distances(graph, player_origin, ghosts)
    return Nothing()


def shortest_route(
    graph: MazeGraph,
    origin: TileIndex,
    destination: TileIndex,
) -> Result[Option[Path], PathfindingError]:
    """Find a shortest route through the selected distance backend.

    Accelerated backends return only distance fields. A route can be
    reconstructed by walking backwards to neighbours whose distance is one
    smaller, avoiding a second Python BFS.

    Args:
        graph: Immutable maze graph to search.
        origin: First tile in the route.
        destination: Last tile in the route.

    Returns:
        A routed shortest path, ``Nothing`` when unreachable, or an invalid
        origin error.
    """
    if not graph.contains(destination):
        return Ok(Nothing())

    searched = distances(graph, origin)
    if isinstance(searched, Err):
        return searched

    return Ok(path_from_distances(graph, origin, destination, searched.value))
