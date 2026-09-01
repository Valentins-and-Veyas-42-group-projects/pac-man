from pacman.analyze.models import DistanceField
from pacman.analyze.safety import (
    SafetyError,
    SafetyKind,
    build_safety_field,
)
from pacman.analyze.threat import NO_THREAT, ThreatField
from pacman.replay.models import Ghost, TileIndex
from typed_errs import Err, Nothing, Some


def test_safety_field_classifies_every_arrival_relationship() -> None:
    player = DistanceField(
        origin=TileIndex(0),
        distances=(0, 1, 2, 3, 4, -1),
        previous=(None,) * 6,
    )
    threats = ThreatField(
        etas=(4, 3, 2, 1, NO_THREAT, 0),
        ghosts=(
            (Ghost.BLINKY,),
            (Ghost.BLINKY,),
            (Ghost.BLINKY, Ghost.PINKY),
            (Ghost.PINKY,),
            (),
            (Ghost.CLYDE,),
        ),
    )
    safety = build_safety_field(player, threats).unwrap()

    assert tuple(tile.kind for tile in safety.tiles) == (
        SafetyKind.SAFE,
        SafetyKind.SAFE,
        SafetyKind.CONTESTED,
        SafetyKind.DANGEROUS,
        SafetyKind.UNTHREATENED,
        SafetyKind.UNREACHABLE,
    )
    assert safety.tiles[0].margin == Some(4)
    assert safety.tiles[2].margin == Some(0)
    assert safety.tiles[3].margin == Some(-2)
    assert isinstance(safety.tiles[4].ghost_eta, Nothing)
    assert isinstance(safety.tiles[4].margin, Nothing)
    assert isinstance(safety.tiles[5].pacman_eta, Nothing)
    assert safety.tiles[5].ghost_eta == Some(0)


def test_safety_field_lookup_rejects_invalid_tiles() -> None:
    player = DistanceField(TileIndex(0), (0,), (None,))
    threats = ThreatField((NO_THREAT,), ((),))
    safety = build_safety_field(player, threats).unwrap()

    assert safety.at(TileIndex(0)) == Some(safety.tiles[0])
    assert isinstance(safety.at(TileIndex(-1)), Nothing)
    assert isinstance(safety.at(TileIndex(1)), Nothing)


def test_safety_field_rejects_different_field_sizes() -> None:
    player = DistanceField(TileIndex(0), (0, 1), (None, None))
    threats = ThreatField((0,), ((Ghost.BLINKY,),))
    result = build_safety_field(player, threats)

    assert isinstance(result, Err)
    assert result.error is SafetyError.FIELD_SIZE_MISMATCH


def test_safety_field_rejects_internally_inconsistent_threat_field() -> None:
    player = DistanceField(TileIndex(0), (0,), (None,))
    threats = ThreatField((0,), ())
    result = build_safety_field(player, threats)

    assert isinstance(result, Err)
    assert result.error is SafetyError.FIELD_SIZE_MISMATCH
