"""Flatten reference simulation inputs for the optional compact engines."""

from typed_errs import Nothing, Option, Some

from pacman.analyze.collectibles import CollectibleField
from pacman.analyze.distance_backend import (
    AcceleratedSimulation,
    PreparedSimulation,
    accelerated_simulation,
)
from pacman.analyze.models import MazeGraph
from pacman.analyze.options import ActionEvaluation
from pacman.analyze.outcomes import ActionOutcome
from pacman.analyze.prediction import GhostPrediction
from pacman.analyze.simulation import SimulationRules
from pacman.replay.models import Direction, GhostState, TileIndex


def prepare_simulation(
    collectibles: CollectibleField,
    predictions: tuple[GhostPrediction, ...],
    origin: TileIndex,
    rules: SimulationRules,
) -> Option[PreparedSimulation]:
    """Encode all ghost occupancy ticks once for four action searches.

    Returns:
        Flat inputs, or Nothing when acceleration cannot represent them.
    """
    tile_count = len(collectibles.tiles)
    horizon = rules.horizon_ticks
    scores = (
        rules.pacgum_score,
        rules.power_pellet_score,
        rules.frightened_ticks,
        *rules.ghost_combo_scores,
    )
    if (
        horizon < 1
        or horizon >= (1 << 32)
        or len(predictions) > 4
        or tile_count == 0
        or not 0 <= int(origin) < tile_count
        or any(score < 0 or score >= (1 << 32) for score in scores)
    ):
        return Nothing()
    try:
        grid = bytearray((horizon + 1) * 4 * tile_count)
        order: list[int] = []
        for prediction in predictions:
            ghost = int(prediction.ghost)
            if ghost < 0 or ghost >= 4 or ghost in order:
                return Nothing()
            order.append(ghost)
            for tick, states in enumerate(prediction.ticks[: horizon + 1]):
                for state in states:
                    tile = int(state.tile)
                    if tile < 0 or tile >= tile_count or state.ghost is not prediction.ghost:
                        return Nothing()
                    kind = (
                        3
                        if state.state is GhostState.EATEN
                        else 2 if state.state is GhostState.FRIGHTENED else 1
                    )
                    grid[(tick * 4 + ghost) * tile_count + tile] = kind
        return Some(
            PreparedSimulation(
                collectibles=bytes(int(item) for item in collectibles.tiles),
                prediction_grid=bytes(grid),
                ghost_order=tuple(order),
                origin=origin,
                horizon=horizon,
                pacgum_score=rules.pacgum_score,
                power_pellet_score=rules.power_pellet_score,
                frightened_ticks=rules.frightened_ticks,
                ghost_combo_scores=rules.ghost_combo_scores,
            )
        )
    except (MemoryError, OverflowError, ValueError):
        return Nothing()


def accelerated_outcome(
    graph: MazeGraph,
    prepared: PreparedSimulation,
    direction: Direction,
    safety: Option[ActionEvaluation],
) -> Option[ActionOutcome]:
    """Combine a compact branch result with the existing safety facts.

    Returns:
        Native or WASM outcome, or Nothing to use the Python reference.
    """
    result = accelerated_simulation(graph, prepared, direction)
    if isinstance(result, Nothing):
        return Nothing()
    branch: AcceleratedSimulation = result.value
    safe_tiles = 0
    safe_intersections = 0
    margin: Option[int] = Nothing()
    if isinstance(safety, Some):
        safe_tiles = safety.value.safe_tiles
        safe_intersections = safety.value.safe_intersections
        margin = safety.value.minimum_margin
    return Some(
        ActionOutcome(
            action=direction,
            died=branch.died,
            survival_horizon=branch.survival_horizon,
            safe_tiles=safe_tiles,
            safe_intersections=safe_intersections,
            score_gained=branch.score_gained,
            pacgums_eaten=branch.pacgums_eaten,
            power_pellets_eaten=branch.power_pellets_eaten,
            ghosts_eaten=branch.ghosts_eaten,
            remaining_power_ticks=branch.remaining_power_ticks,
            threat_margin=margin,
            path=branch.path,
        )
    )
