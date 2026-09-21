"""Optional browser bridge to the WebAssembly distance engine."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, cast

from typed_errs import Nothing, Option, Some

from pacman.analyze.distance_backend import (
    AcceleratedAction,
    AcceleratedThreatAnalysis,
    AcceleratedThreatField,
    GhostOriginLike,
    PredictedGhostOrigin,
)
from pacman.analyze.models import MazeGraph
from pacman.replay.models import Direction, TileIndex

PACMAN_ABI_VERSION = 2
MOVES_PER_TILE = 4
MOVE_SIZE = 4
TILE_SIZE = MOVES_PER_TILE * MOVE_SIZE + 2


class WasmDistances(Protocol):
    """Iterable numeric result returned through Python/JavaScript interop."""

    def __iter__(self) -> Iterator[int]:
        """Iterate over returned distances."""
        ...


class WasmThreatAnalysis(Protocol):
    """Combined result returned through Python/JavaScript interop."""

    playerDistances: WasmDistances  # noqa: N815
    threatEtas: WasmDistances  # noqa: N815
    threatOwnerMasks: WasmDistances  # noqa: N815


class WasmThreatField(Protocol):
    """Threat-only result returned through Python/JavaScript interop."""

    etas: WasmDistances
    ownerMasks: WasmDistances  # noqa: N815


class WasmAction(Protocol):
    """One action record from the browser bridge."""

    direction: int
    firstTile: int  # noqa: N815
    reachableTiles: WasmDistances  # noqa: N815
    safeTiles: int  # noqa: N815
    safeIntersections: int  # noqa: N815
    horizonTicks: int  # noqa: N815
    minimumMargin: int | None  # noqa: N815


class WasmBridge(Protocol):
    """JavaScript contract installed by ``web/native-engine.mjs``."""

    def abiVersion(self) -> int:  # noqa: N802
        """Return the C ABI version exposed by the WASM module."""
        ...

    def bfsDistances(  # noqa: N802
        self, encoded: list[int], tile_count: int, width: int, origin: int
    ) -> WasmDistances | None:
        """Compute one distance field from a flattened C graph."""
        ...

    def createTopology(  # noqa: N802
        self, encoded: list[int], tile_count: int, width: int
    ) -> int:
        """Create and return an owned WASM topology handle."""
        ...

    def destroyTopology(self, topology: int) -> None:  # noqa: N802
        """Release an owned WASM topology handle."""
        ...

    def topologyBfsDistances(  # noqa: N802
        self, topology: int, tile_count: int, origin: int
    ) -> WasmDistances | None:
        """Search through a reusable topology handle."""
        ...

    def topologyAnalyzeDistances(  # noqa: N802
        self,
        topology: int,
        tile_count: int,
        player_origin: int,
        ghosts: list[int],
    ) -> WasmThreatAnalysis | None:
        """Compute player and dangerous-ghost fields together."""
        ...

    def topologyThreatField(  # noqa: N802
        self,
        topology: int,
        tile_count: int,
        ghosts: list[int],
    ) -> WasmThreatField | None:
        """Compute dangerous-ghost fields without a player search."""
        ...

    def topologyPredictThreat(  # noqa: N802
        self,
        topology: int,
        tile_count: int,
        ghosts: list[int],
        horizon: int,
    ) -> WasmThreatField | None:
        """Compute bounded direction-aware ghost threats."""
        ...

    def topologyEvaluateActions(  # noqa: N802
        self, topology: int, tile_count: int, player_tile: int, threat_etas: list[int]
    ) -> list[WasmAction] | None:
        """Evaluate safe first moves with the cached topology."""
        ...


def _browser_bridge() -> Option[WasmBridge]:
    """Find the bridge only available inside the browser Python runtime.

    Returns:
        A version-compatible bridge, or Nothing outside the browser.
    """
    try:
        import platform

        window = platform.__dict__["window"]
        bridge = cast(WasmBridge, window.pacmanWasm)
        if int(bridge.abiVersion()) != PACMAN_ABI_VERSION:
            return Nothing()
        return Some(bridge)
    except (AttributeError, ImportError, KeyError, TypeError, ValueError):
        return Nothing()


class WasmPathfinding:
    """Pathfinding backend backed by the browser's loaded WASM module."""

    def __init__(self, bridge: WasmBridge) -> None:
        """Retain a compatible browser bridge."""
        self._bridge = bridge
        self._topologies: dict[int, tuple[MazeGraph, int]] = {}

    @staticmethod
    def _encode(graph: MazeGraph) -> Option[list[int]]:
        """Encode a graph for one JavaScript boundary crossing.

        Returns:
            Flattened C records, or Nothing for an unsupported graph.
        """
        encoded = bytearray(len(graph.moves) * TILE_SIZE)
        for tile, moves in enumerate(graph.moves):
            if len(moves) > MOVES_PER_TILE:
                return Nothing()
            offset = tile * TILE_SIZE
            for index, move in enumerate(moves):
                move_offset = offset + index * MOVE_SIZE
                destination = int(move.destination)
                encoded[move_offset] = destination & 0xFF
                encoded[move_offset + 1] = destination >> 8
                encoded[move_offset + 2] = int(move.direction)
                encoded[move_offset + 3] = int(move.wraparound)
            encoded[offset + MOVES_PER_TILE * MOVE_SIZE] = len(moves)
        return Some(list(encoded))

    def distances(self, graph: MazeGraph, origin: TileIndex) -> Option[tuple[int, ...]]:
        """Return cached-topology WASM distances, or Nothing on failure."""
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            result = self._bridge.topologyBfsDistances(topology.value, len(graph.moves), int(origin))
            if result is None:
                return Nothing()
            values = tuple(int(value) for value in result)
            if len(values) != len(graph.moves):
                return Nothing()
            return Some(values)
        except Exception:
            return Nothing()

    def analyze_distances(
        self,
        graph: MazeGraph,
        player_origin: TileIndex,
        ghosts: tuple[GhostOriginLike, ...],
    ) -> Option[AcceleratedThreatAnalysis]:
        """Return combined cached-topology analysis, or Nothing on failure."""
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            encoded: list[int] = []
            for ghost in ghosts:
                tile = int(ghost.tile)
                encoded.extend((tile & 0xFF, tile >> 8, int(ghost.ghost), int(ghost.dangerous)))
            result = self._bridge.topologyAnalyzeDistances(
                topology.value, len(graph.moves), int(player_origin), encoded
            )
            if result is None:
                return Nothing()
            analysis = AcceleratedThreatAnalysis(
                player_distances=tuple(int(value) for value in result.playerDistances),
                threat_etas=tuple(int(value) for value in result.threatEtas),
                threat_owner_masks=tuple(int(value) for value in result.threatOwnerMasks),
            )
            if not all(
                len(values) == len(graph.moves)
                for values in (
                    analysis.player_distances,
                    analysis.threat_etas,
                    analysis.threat_owner_masks,
                )
            ):
                return Nothing()
            return Some(analysis)
        except Exception:
            return Nothing()

    def threat_field(
        self,
        graph: MazeGraph,
        ghosts: tuple[GhostOriginLike, ...],
    ) -> Option[AcceleratedThreatField]:
        """Return dangerous-ghost arrivals without a player search."""
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            encoded = self._encode_ghosts(ghosts)
            result = self._bridge.topologyThreatField(topology.value, len(graph.moves), encoded)
            if result is None:
                return Nothing()
            field = AcceleratedThreatField(
                etas=tuple(int(value) for value in result.etas),
                owner_masks=tuple(int(value) for value in result.ownerMasks),
            )
            if len(field.etas) != len(graph.moves) or len(field.owner_masks) != len(graph.moves):
                return Nothing()
            return Some(field)
        except Exception:
            return Nothing()

    def predict_threat(
        self,
        graph: MazeGraph,
        ghosts: tuple[PredictedGhostOrigin, ...],
        horizon: int,
    ) -> Option[AcceleratedThreatField]:
        """Return bounded direction-aware ghost threats."""
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            encoded: list[int] = []
            for ghost in ghosts:
                tile = int(ghost.tile)
                encoded.extend((
                    tile & 0xFF,
                    tile >> 8,
                    int(ghost.direction),
                    int(ghost.ghost),
                    int(ghost.dangerous),
                    0,
                    0,
                    0,
                ))
            result = self._bridge.topologyPredictThreat(topology.value, len(graph.moves), encoded, horizon)
            if result is None:
                return Nothing()
            field = AcceleratedThreatField(
                etas=tuple(int(value) for value in result.etas),
                owner_masks=tuple(int(value) for value in result.ownerMasks),
            )
            if len(field.etas) != len(graph.moves) or len(field.owner_masks) != len(graph.moves):
                return Nothing()
            return Some(field)
        except Exception:
            return Nothing()

    def evaluate_actions(
        self, graph: MazeGraph, player_tile: TileIndex, threat_etas: tuple[int, ...]
    ) -> Option[tuple[AcceleratedAction, ...]]:
        """Return safe first-move facts from the browser bridge."""
        if len(threat_etas) != len(graph.moves):
            return Nothing()
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            result = self._bridge.topologyEvaluateActions(
                topology.value, len(graph.moves), int(player_tile), list(threat_etas)
            )
            if result is None:
                return Nothing()
            return Some(
                tuple(
                    AcceleratedAction(
                        direction=Direction(item.direction),
                        first_tile=TileIndex(item.firstTile),
                        reachable_tiles=tuple(TileIndex(tile) for tile in item.reachableTiles),
                        safe_tiles=int(item.safeTiles),
                        safe_intersections=int(item.safeIntersections),
                        horizon_ticks=int(item.horizonTicks),
                        minimum_margin=Some(int(item.minimumMargin)) if item.minimumMargin is not None else Nothing(),
                    )
                    for item in result
                )
            )
        except Exception:
            return Nothing()

    @staticmethod
    def _encode_ghosts(ghosts: tuple[GhostOriginLike, ...]) -> list[int]:
        """Flatten ghost records to their four-byte C representation.

        Returns:
            Consecutive bytes matching ``pac_ghost_origin`` records.
        """
        encoded: list[int] = []
        for ghost in ghosts:
            tile = int(ghost.tile)
            encoded.extend((tile & 0xFF, tile >> 8, int(ghost.ghost), int(ghost.dangerous)))
        return encoded

    def _topology_for(self, graph: MazeGraph) -> Option[int]:
        """Return a cached WASM topology, constructing it once."""
        cached = self._topologies.get(id(graph))
        if cached is not None and cached[0] is graph:
            return Some(cached[1])
        encoded = self._encode(graph)
        if isinstance(encoded, Nothing):
            return Nothing()
        topology = int(self._bridge.createTopology(encoded.value, len(graph.moves), graph.width))
        if topology == 0:
            return Nothing()
        self._topologies[id(graph)] = (graph, topology)
        return Some(topology)

    def close(self) -> None:
        """Release every cached WASM topology."""
        for _, topology in self._topologies.values():
            self._bridge.destroyTopology(topology)
        self._topologies.clear()

    def __del__(self) -> None:
        """Release cached WASM ownership during interpreter cleanup."""
        try:
            self.close()
        except Exception:
            pass


def load_wasm_pathfinding() -> Option[WasmPathfinding]:
    """Load the browser WASM backend when its JavaScript bridge is ready.

    Returns:
        A usable WASM backend, or Nothing when the bridge is absent.
    """
    bridge = _browser_bridge()
    if isinstance(bridge, Some):
        return Some(WasmPathfinding(bridge.value))
    return Nothing()
