"""Optional browser bridge to the WebAssembly distance engine."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, cast

from typed_errs import Nothing, Option, Some

from pacman.analyze.models import MazeGraph
from pacman.replay.models import TileIndex

PACMAN_ABI_VERSION = 2
MOVES_PER_TILE = 4
MOVE_SIZE = 4
TILE_SIZE = MOVES_PER_TILE * MOVE_SIZE + 2


class WasmDistances(Protocol):
    """Iterable numeric result returned through Python/JavaScript interop."""

    def __iter__(self) -> Iterator[int]:
        """Iterate over returned distances."""
        ...


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

    def distances(self, graph: MazeGraph, origin: TileIndex) -> Option[tuple[int, ...]]:
        """Return WASM distances, or Nothing when interop fails."""
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

        try:
            result = self._bridge.bfsDistances(list(encoded), len(graph.moves), graph.width, int(origin))
            if result is None:
                return Nothing()
            values = tuple(int(value) for value in result)
            if len(values) != len(graph.moves):
                return Nothing()
            return Some(values)
        except Exception:
            return Nothing()


def load_wasm_pathfinding() -> Option[WasmPathfinding]:
    """Load the browser WASM backend when its JavaScript bridge is ready.

    Returns:
        A usable WASM backend, or Nothing when the bridge is absent.
    """
    bridge = _browser_bridge()
    if isinstance(bridge, Some):
        return Some(WasmPathfinding(bridge.value))
    return Nothing()
