"""Evaluate Pac-Man's legal first moves against a ghost threat field."""

from collections import deque
from dataclasses import dataclass
from enum import Enum

from typed_errs import Err, Nothing, Ok, Option, Result, Some

from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.threat import NO_THREAT, ThreatField
from pacman.analyze.topology import TileKind, classify_tile
from pacman.replay.models import Direction, TileIndex


class OptionsError(Enum):
    """Failures encountered while evaluating player actions."""

    INVALID_PLAYER_TILE = "invalid_player_tile"
    ILLEGAL_ACTION = "illegal_action"
    FIELD_SIZE_MISMATCH = "field_size_mismatch"


@dataclass(frozen=True, slots=True)
class ActionEvaluation:
    """Safe territory available after committing to one first action."""

    action: Direction
    first_tile: TileIndex
    reachable_tiles: tuple[TileIndex, ...]
    safe_tiles: int
    safe_intersections: int
    horizon_ticks: int
    minimum_margin: Option[int]


def options_err(error: OptionsError) -> Err[OptionsError]:
    """Create an action-evaluation error with consistent context.

    Returns:
        A contextual action-evaluation error.
    """
    return Err(
        error=error,
        namespace="options",
        context_msg="Failed to evaluate player actions",
    )


def _is_safe_arrival(threats: ThreatField, tile: TileIndex, arrival: int) -> bool:
    ghost_eta = threats.etas[int(tile)]
    return ghost_eta == NO_THREAT or arrival < ghost_eta


def evaluate_action(
    graph: MazeGraph,
    threats: ThreatField,
    player_tile: TileIndex,
    action: Direction,
) -> Result[ActionEvaluation, OptionsError]:
    """Measure safe reachability after one chosen legal action.

    Returns:
        The action evaluation or a typed validation error.
    """
    if not graph.contains(player_tile):
        return options_err(OptionsError.INVALID_PLAYER_TILE)
    if len(threats.etas) != len(graph.moves) or len(threats.ghosts) != len(graph.moves):
        return options_err(OptionsError.FIELD_SIZE_MISMATCH)

    first_move: Option[Move] = Nothing()
    for move in graph.neighbors(player_tile):
        if move.direction is action:
            first_move = Some(move)
            break

    if isinstance(first_move, Nothing):
        return options_err(OptionsError.ILLEGAL_ACTION)

    first_tile = first_move.value.destination
    if not _is_safe_arrival(threats, first_tile, 1):
        return Ok(ActionEvaluation(action, first_tile, (), 0, 0, 0, Nothing()))

    arrivals = [-1] * len(graph.moves)
    arrivals[int(first_tile)] = 1
    queue: deque[TileIndex] = deque([first_tile])
    reachable: list[TileIndex] = []
    minimum_margin: Option[int] = Nothing()

    while queue:
        current = queue.popleft()
        reachable.append(current)
        arrival = arrivals[int(current)]
        ghost_eta = threats.etas[int(current)]
        if ghost_eta != NO_THREAT:
            margin = ghost_eta - arrival
            if isinstance(minimum_margin, Nothing):
                minimum_margin = Some(margin)
            else:
                minimum_margin = Some(min(minimum_margin.value, margin))

        for move in graph.neighbors(current):
            neighbor = move.destination
            neighbor_arrival = arrival + 1
            if arrivals[int(neighbor)] != -1:
                continue
            if not _is_safe_arrival(threats, neighbor, neighbor_arrival):
                continue
            arrivals[int(neighbor)] = neighbor_arrival
            queue.append(neighbor)

    intersections = 0
    for tile in reachable:
        tile_kind = classify_tile(graph, tile)
        if isinstance(tile_kind, Some) and tile_kind.value is TileKind.INTERSECTION:
            intersections += 1
    horizon = max(arrivals[int(tile)] for tile in reachable)
    return Ok(
        ActionEvaluation(
            action=action,
            first_tile=first_tile,
            reachable_tiles=tuple(reachable),
            safe_tiles=len(reachable),
            safe_intersections=intersections,
            horizon_ticks=horizon,
            minimum_margin=minimum_margin,
        )
    )


def evaluate_actions(
    graph: MazeGraph,
    threats: ThreatField,
    player_tile: TileIndex,
) -> Result[tuple[ActionEvaluation, ...], OptionsError]:
    """Evaluate every legal action from one player tile.

    Returns:
        Evaluations in graph move order or a typed validation error.
    """
    if not graph.contains(player_tile):
        return options_err(OptionsError.INVALID_PLAYER_TILE)
    if len(threats.etas) != len(graph.moves) or len(threats.ghosts) != len(graph.moves):
        return options_err(OptionsError.FIELD_SIZE_MISMATCH)

    evaluations: list[ActionEvaluation] = []
    for move in graph.neighbors(player_tile):
        evaluation = evaluate_action(graph, threats, player_tile, move.direction)
        if isinstance(evaluation, Err):
            return evaluation
        evaluations.append(evaluation.value)
    return Ok(tuple(evaluations))
