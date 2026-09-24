"""Optional ctypes bridge to the native distance engine."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import threading
from collections.abc import Iterable
from pathlib import Path

from typed_errs import Nothing, Option, Some

from pacman.analyze.distance_backend import (
    AcceleratedAction,
    AcceleratedSimulation,
    AcceleratedThreatAnalysis,
    AcceleratedThreatField,
    GhostOriginLike,
    PredictedGhostOrigin,
    PreparedSimulation,
)
from pacman.analyze.models import MazeGraph
from pacman.replay.models import Direction, TileIndex

PACMAN_ABI_VERSION = 3
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


class PacGhostOrigin(ctypes.Structure):
    """C representation of one ghost used by threat analysis."""

    _fields_ = [
        ("tile", ctypes.c_uint16),
        ("ghost", ctypes.c_uint8),
        ("dangerous", ctypes.c_uint8),
    ]


class PacPredictedGhost(ctypes.Structure):
    """C representation of one direction-aware predicted ghost."""

    _fields_ = [
        ("tile", ctypes.c_uint16),
        ("direction", ctypes.c_uint8),
        ("ghost", ctypes.c_uint8),
        ("dangerous", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8 * 3),
    ]


class PacActionEvaluation(ctypes.Structure):
    """C representation of one safe first-move evaluation."""

    _fields_ = [
        ("safe_tiles", ctypes.c_uint32),
        ("safe_intersections", ctypes.c_uint32),
        ("horizon_ticks", ctypes.c_uint32),
        ("minimum_margin", ctypes.c_int32),
        ("first_tile", ctypes.c_uint16),
        ("direction", ctypes.c_uint8),
        ("has_minimum_margin", ctypes.c_uint8),
    ]


class PacSimulationInput(ctypes.Structure):
    """Caller-owned buffers and rules for one bounded branch search."""

    _fields_ = [
        ("collectibles", ctypes.POINTER(ctypes.c_uint8)),
        ("collectible_count", ctypes.c_size_t),
        ("prediction_grid", ctypes.POINTER(ctypes.c_uint8)),
        ("prediction_count", ctypes.c_size_t),
        ("ghost_combo_scores", ctypes.POINTER(ctypes.c_uint32)),
        ("ghost_combo_score_count", ctypes.c_size_t),
        ("horizon", ctypes.c_uint32),
        ("state_capacity", ctypes.c_uint32),
        ("pacgum_score", ctypes.c_uint32),
        ("power_pellet_score", ctypes.c_uint32),
        ("frightened_ticks", ctypes.c_uint32),
        ("origin", ctypes.c_uint16),
        ("action", ctypes.c_uint8),
        ("ghost_count", ctypes.c_uint8),
        ("ghost_order", ctypes.c_uint8 * 4),
        ("reserved", ctypes.c_uint8 * 2),
    ]


class PacSimulationResult(ctypes.Structure):
    """Fixed-width summary of the strongest terminal branch."""

    _fields_ = [
        ("score_gained", ctypes.c_uint64),
        ("survival_horizon", ctypes.c_uint32),
        ("pacgums_eaten", ctypes.c_uint32),
        ("power_pellets_eaten", ctypes.c_uint32),
        ("ghosts_eaten", ctypes.c_uint32),
        ("remaining_power_ticks", ctypes.c_uint32),
        ("path_length", ctypes.c_uint32),
        ("died", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8 * 3),
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
        for name in (
            "pac_topology_bfs_distances_graph",
            "pac_topology_bfs_distances_masked",
        ):
            function = getattr(library, name)
            function.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint16,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.c_size_t,
            ]
            function.restype = ctypes.c_int
        library.pac_topology_bfs_many.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t,
        ]
        library.pac_topology_bfs_many.restype = ctypes.c_int
        library.pac_topology_analyze_distances.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.POINTER(PacGhostOrigin),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        library.pac_topology_analyze_distances.restype = ctypes.c_int
        library.pac_topology_threat_field.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(PacGhostOrigin),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        library.pac_topology_threat_field.restype = ctypes.c_int
        library.pac_topology_predict_threat.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(PacPredictedGhost),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        library.pac_topology_predict_threat.restype = ctypes.c_int
        library.pac_topology_evaluate_actions.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t,
            ctypes.POINTER(PacActionEvaluation),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        library.pac_topology_evaluate_actions.restype = ctypes.c_int
        library.pac_topology_simulate_action.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(PacSimulationInput),
            ctypes.POINTER(PacSimulationResult),
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.c_size_t,
        ]
        library.pac_topology_simulate_action.restype = ctypes.c_int
        self._topologies: dict[int, tuple[MazeGraph, ctypes.c_void_p]] = {}
        self._topology_lock = threading.Lock()

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
    def _decode(output: Iterable[int]) -> tuple[int, ...]:
        """Translate the native unreachable sentinel into the Python value.

        Returns:
            Distances using negative one for unreachable tiles.
        """
        return tuple(-1 if value == NATIVE_UNREACHABLE else int(value) for value in output)

    def _topology_for(self, graph: MazeGraph) -> Option[ctypes.c_void_p]:
        """Return a cached owned topology, constructing it only once."""
        with self._topology_lock:
            cached = self._topologies.get(id(graph))
            if cached is not None:
                cached_graph, pointer = cached
                if cached_graph is graph:
                    return Some(pointer)
            encoded = self._encode(graph)
            if isinstance(encoded, Nothing):
                return Nothing()
            pointer = ctypes.c_void_p()
            status = self._library.pac_topology_create(
                encoded.value, len(graph.moves), graph.width, ctypes.byref(pointer)
            )
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

    def cached_distances(self, graph: MazeGraph, origin: TileIndex, *, masked: bool) -> Option[tuple[int, ...]]:
        """Run one explicit kernel through an already cached topology.

        Returns:
            Computed distances, or Nothing when the native call fails.
        """
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            count = len(graph.moves)
            output = (ctypes.c_uint32 * count)()
            function = (
                self._library.pac_topology_bfs_distances_masked
                if masked
                else self._library.pac_topology_bfs_distances_graph
            )
            status = function(topology.value, int(origin), output, count)
            return Some(self._decode(output)) if status == PAC_OK else Nothing()
        except Exception:
            return Nothing()

    def distances_many(self, graph: MazeGraph, origins: tuple[TileIndex, ...]) -> Option[tuple[tuple[int, ...], ...]]:
        """Compute several distance fields through one native call.

        Returns:
            One field per origin, or Nothing when the batch fails.
        """
        if not origins:
            return Some(())
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            tile_count = len(graph.moves)
            encoded_origins = (ctypes.c_uint16 * len(origins))(*(int(origin) for origin in origins))
            output_count = tile_count * len(origins)
            output = (ctypes.c_uint32 * output_count)()
            status = self._library.pac_topology_bfs_many(
                topology.value,
                encoded_origins,
                len(origins),
                output,
                output_count,
            )
            if status != PAC_OK:
                return Nothing()
            return Some(
                tuple(
                    self._decode(output[index * tile_count : (index + 1) * tile_count]) for index in range(len(origins))
                )
            )
        except Exception:
            return Nothing()

    def analyze_distances(
        self,
        graph: MazeGraph,
        player_origin: TileIndex,
        ghosts: tuple[GhostOriginLike, ...],
    ) -> Option[AcceleratedThreatAnalysis]:
        """Compute player and dangerous-ghost distance data together.

        Returns:
            Combined native results, or Nothing when native execution fails.
        """
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            tile_count = len(graph.moves)
            encoded_ghosts = (PacGhostOrigin * len(ghosts))(
                *(PacGhostOrigin(int(ghost.tile), int(ghost.ghost), int(ghost.dangerous)) for ghost in ghosts)
            )
            player_distances = (ctypes.c_uint32 * tile_count)()
            threat_etas = (ctypes.c_uint32 * tile_count)()
            threat_owners = (ctypes.c_uint8 * tile_count)()
            status = self._library.pac_topology_analyze_distances(
                topology.value,
                int(player_origin),
                encoded_ghosts,
                len(ghosts),
                player_distances,
                tile_count,
                threat_etas,
                threat_owners,
                tile_count,
            )
            if status != PAC_OK:
                return Nothing()
            return Some(
                AcceleratedThreatAnalysis(
                    player_distances=self._decode(player_distances),
                    threat_etas=self._decode(threat_etas),
                    threat_owner_masks=tuple(int(owner) for owner in threat_owners),
                )
            )
        except Exception:
            return Nothing()

    def threat_field(
        self,
        graph: MazeGraph,
        ghosts: tuple[GhostOriginLike, ...],
    ) -> Option[AcceleratedThreatField]:
        """Compute dangerous-ghost arrivals without an unused player BFS.

        Returns:
            The native threat field, or Nothing when native execution fails.
        """
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            tile_count = len(graph.moves)
            encoded_ghosts = (PacGhostOrigin * len(ghosts))(
                *(PacGhostOrigin(int(ghost.tile), int(ghost.ghost), int(ghost.dangerous)) for ghost in ghosts)
            )
            etas = (ctypes.c_uint32 * tile_count)()
            owners = (ctypes.c_uint8 * tile_count)()
            status = self._library.pac_topology_threat_field(
                topology.value,
                encoded_ghosts,
                len(ghosts),
                etas,
                owners,
                tile_count,
            )
            if status != PAC_OK:
                return Nothing()
            return Some(
                AcceleratedThreatField(
                    etas=self._decode(etas),
                    owner_masks=tuple(int(owner) for owner in owners),
                )
            )
        except Exception:
            return Nothing()

    def predict_threat(
        self,
        graph: MazeGraph,
        ghosts: tuple[PredictedGhostOrigin, ...],
        horizon: int,
    ) -> Option[AcceleratedThreatField]:
        """Compute bounded direction-aware ghost threats.

        Returns:
            The native predicted threat field, or Nothing on failure.
        """
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            encoded = (PacPredictedGhost * len(ghosts))(
                *(
                    PacPredictedGhost(
                        int(ghost.tile),
                        int(ghost.direction),
                        int(ghost.ghost),
                        int(ghost.dangerous),
                    )
                    for ghost in ghosts
                )
            )
            tile_count = len(graph.moves)
            etas = (ctypes.c_uint32 * tile_count)()
            owners = (ctypes.c_uint8 * tile_count)()
            status = self._library.pac_topology_predict_threat(
                topology.value,
                encoded,
                len(ghosts),
                horizon,
                etas,
                owners,
                tile_count,
            )
            if status != PAC_OK:
                return Nothing()
            return Some(
                AcceleratedThreatField(
                    etas=self._decode(etas),
                    owner_masks=tuple(int(owner) for owner in owners),
                )
            )
        except Exception:
            return Nothing()

    def evaluate_actions(
        self, graph: MazeGraph, player_tile: TileIndex, threat_etas: tuple[int, ...]
    ) -> Option[tuple[AcceleratedAction, ...]]:
        """Return safe first-move facts from the cached topology.

        Returns:
            Action facts, or Nothing when the native call fails.
        """
        if len(threat_etas) != len(graph.moves):
            return Nothing()
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            count = len(graph.moves)
            etas = (ctypes.c_uint32 * count)(*(NATIVE_UNREACHABLE if eta < 0 else eta for eta in threat_etas))
            actions = (PacActionEvaluation * 4)()
            reachable = (ctypes.c_uint16 * (count * 4))()
            action_count = ctypes.c_size_t()
            status = self._library.pac_topology_evaluate_actions(
                topology.value,
                int(player_tile),
                etas,
                count,
                actions,
                4,
                reachable,
                count * 4,
                ctypes.byref(action_count),
            )
            if status != PAC_OK or action_count.value > 4:
                return Nothing()
            from typed_errs import Some

            return Some(
                tuple(
                    AcceleratedAction(
                        direction=Direction(actions[index].direction),
                        first_tile=TileIndex(actions[index].first_tile),
                        reachable_tiles=tuple(
                            TileIndex(reachable[index * count + tile]) for tile in range(actions[index].safe_tiles)
                        ),
                        safe_tiles=actions[index].safe_tiles,
                        safe_intersections=actions[index].safe_intersections,
                        horizon_ticks=actions[index].horizon_ticks,
                        minimum_margin=(
                            Some(actions[index].minimum_margin) if actions[index].has_minimum_margin else Nothing()
                        ),
                    )
                    for index in range(action_count.value)
                )
            )
        except Exception:
            return Nothing()

    def simulate_action(
        self, graph: MazeGraph, prepared: PreparedSimulation, direction: Direction
    ) -> Option[AcceleratedSimulation]:
        """Return the best native branch, or Nothing when Python must search."""
        if len(prepared.collectibles) != len(graph.moves) or prepared.horizon < 1:
            return Nothing()
        try:
            topology = self._topology_for(graph)
            if isinstance(topology, Nothing):
                return Nothing()
            collectible_bytes = (ctypes.c_uint8 * len(prepared.collectibles)).from_buffer_copy(prepared.collectibles)
            prediction_bytes = (ctypes.c_uint8 * len(prepared.prediction_grid)).from_buffer_copy(
                prepared.prediction_grid
            )
            combo_scores = (ctypes.c_uint32 * len(prepared.ghost_combo_scores))(*prepared.ghost_combo_scores)
            request = PacSimulationInput(
                collectible_bytes,
                len(collectible_bytes),
                prediction_bytes,
                len(prediction_bytes),
                combo_scores,
                len(combo_scores),
                prepared.horizon,
                4096,
                prepared.pacgum_score,
                prepared.power_pellet_score,
                prepared.frightened_ticks,
                int(prepared.origin),
                int(direction),
                len(prepared.ghost_order),
                (ctypes.c_uint8 * 4)(*prepared.ghost_order),
                (ctypes.c_uint8 * 2)(),
            )
            path = (ctypes.c_uint16 * (prepared.horizon + 1))()
            result = PacSimulationResult()
            status = self._library.pac_topology_simulate_action(
                topology.value, ctypes.byref(request), ctypes.byref(result), path, len(path)
            )
            if status != PAC_OK or result.path_length > len(path):
                return Nothing()
            return Some(
                AcceleratedSimulation(
                    died=bool(result.died),
                    survival_horizon=result.survival_horizon,
                    score_gained=result.score_gained,
                    pacgums_eaten=result.pacgums_eaten,
                    power_pellets_eaten=result.power_pellets_eaten,
                    ghosts_eaten=result.ghosts_eaten,
                    remaining_power_ticks=result.remaining_power_ticks,
                    path=tuple(TileIndex(path[index]) for index in range(result.path_length)),
                )
            )
        except (AttributeError, MemoryError, OverflowError, TypeError, ValueError):
            return Nothing()

    def close(self) -> None:
        """Release every cached native topology."""
        with self._topology_lock:
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
