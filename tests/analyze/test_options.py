from pacman.analyze.models import MazeGraph, Move
from pacman.analyze.options import OptionsError, evaluate_action, evaluate_actions
from pacman.analyze.threat import NO_THREAT, ThreatField
from pacman.replay.models import Direction, TileIndex
from typed_errs import Err, Nothing, Some


def options_graph() -> MazeGraph:
    return MazeGraph(
        width=3,
        height=2,
        moves=(
            (
                Move(TileIndex(1), Direction.RIGHT),
                Move(TileIndex(3), Direction.DOWN),
            ),
            (
                Move(TileIndex(0), Direction.LEFT),
                Move(TileIndex(2), Direction.RIGHT),
            ),
            (Move(TileIndex(1), Direction.LEFT),),
            (
                Move(TileIndex(0), Direction.UP),
                Move(TileIndex(4), Direction.RIGHT),
            ),
            (
                Move(TileIndex(3), Direction.LEFT),
                Move(TileIndex(5), Direction.RIGHT),
            ),
            (Move(TileIndex(4), Direction.LEFT),),
        ),
    )


def threats(etas: tuple[int, ...]) -> ThreatField:
    return ThreatField(etas=etas, ghosts=((),) * len(etas))


def test_actions_compare_safe_territory_after_first_move() -> None:
    result = evaluate_actions(
        options_graph(),
        threats((0, 3, 2, 10, 10, 10)),
        TileIndex(0),
    ).unwrap()

    right, down = result
    assert right.action is Direction.RIGHT
    assert right.reachable_tiles == (TileIndex(1),)
    assert right.safe_tiles == 1
    assert right.horizon_ticks == 1
    assert right.minimum_margin == Some(2)
    assert down.action is Direction.DOWN
    assert down.reachable_tiles == (TileIndex(3), TileIndex(4), TileIndex(5))
    assert down.safe_tiles == 3
    assert down.horizon_ticks == 3
    assert down.minimum_margin == Some(7)


def test_action_with_ghost_arriving_first_has_no_safe_reachability() -> None:
    result = evaluate_action(
        options_graph(),
        threats((NO_THREAT, 1, NO_THREAT, NO_THREAT, NO_THREAT, NO_THREAT)),
        TileIndex(0),
        Direction.RIGHT,
    ).unwrap()

    assert result.safe_tiles == 0
    assert result.reachable_tiles == ()
    assert result.horizon_ticks == 0
    assert isinstance(result.minimum_margin, Nothing)


def test_action_evaluation_rejects_invalid_inputs() -> None:
    graph = options_graph()
    valid_threats = threats((NO_THREAT,) * 6)

    invalid_tile = evaluate_actions(graph, valid_threats, TileIndex(6))
    illegal_action = evaluate_action(
        graph,
        valid_threats,
        TileIndex(0),
        Direction.LEFT,
    )
    wrong_size = evaluate_actions(
        graph,
        threats((NO_THREAT,)),
        TileIndex(0),
    )

    assert isinstance(invalid_tile, Err)
    assert invalid_tile.error is OptionsError.INVALID_PLAYER_TILE
    assert isinstance(illegal_action, Err)
    assert illegal_action.error is OptionsError.ILLEGAL_ACTION
    assert isinstance(wrong_size, Err)
    assert wrong_size.error is OptionsError.FIELD_SIZE_MISMATCH
