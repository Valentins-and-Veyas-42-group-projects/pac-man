"""Persist and inspect results from synthetic analysis experiments."""

from dataclasses import dataclass
from pathlib import Path
from typing import NewType, cast

from sqlite_callback_store import SQLiteStore, StorageError, Transaction
from typed_errs import Err, Ok, Result

ExperimentId = NewType("ExperimentId", int)

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_experiment (
    id INTEGER PRIMARY KEY,
    seed INTEGER NOT NULL,
    seconds INTEGER NOT NULL,
    speed REAL NOT NULL,
    fumble_probability REAL NOT NULL,
    frames INTEGER NOT NULL,
    score INTEGER NOT NULL,
    pickups INTEGER NOT NULL,
    fumbles INTEGER NOT NULL,
    deaths INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
) STRICT;

CREATE TABLE IF NOT EXISTS analysis_bad_play (
    experiment_id INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    PRIMARY KEY (experiment_id, tick),
    FOREIGN KEY (experiment_id) REFERENCES analysis_experiment(id) ON DELETE CASCADE
) WITHOUT ROWID, STRICT;
"""


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """Result saved after one synthetic pipeline run."""

    seed: int
    seconds: int
    speed: float
    fumble_probability: float
    frames: int
    score: int
    pickups: int
    fumbles: int
    deaths: int
    wins: int
    losses: int
    bad_play_ticks: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StoredExperiment:
    """Persisted experiment with its assigned identifier."""

    id: ExperimentId
    result: ExperimentResult


class ExperimentStore(SQLiteStore):
    """Store repeatable fake-game outcomes separately from replay frames."""

    def __init__(self, path: Path) -> None:
        """Create a store targeting one history database."""
        super().__init__(path)

    def initialize_experiments(self) -> Result[None, StorageError]:
        """Create experiment tables when absent.

        Returns:
            Success or a typed storage error.
        """
        return self.initialize(SCHEMA)

    def save(self, result: ExperimentResult) -> Result[ExperimentId, StorageError]:
        """Persist one experiment and its bad-play ticks.

        Returns:
            Assigned experiment identifier or a typed storage error.
        """

        def insert(transaction: Transaction) -> Result[ExperimentId, StorageError]:
            row = cast(
                "tuple[int] | None",
                transaction.connection.execute(
                    """
                    INSERT INTO analysis_experiment (
                        seed, seconds, speed, fumble_probability, frames, score,
                        pickups, fumbles, deaths, wins, losses
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
                    """,
                    (
                        result.seed,
                        result.seconds,
                        result.speed,
                        result.fumble_probability,
                        result.frames,
                        result.score,
                        result.pickups,
                        result.fumbles,
                        result.deaths,
                        result.wins,
                        result.losses,
                    ),
                ).fetchone(),
            )
            if row is None:
                return Err(StorageError.OPERATION_FAILED, context_msg="Experiment insert returned no id")
            experiment_id = ExperimentId(row[0])
            transaction.connection.executemany(
                "INSERT INTO analysis_bad_play (experiment_id, tick) VALUES (?, ?)",
                ((int(experiment_id), tick) for tick in result.bad_play_ticks),
            )
            return Ok(experiment_id)

        return self.transaction(insert)

    def recent(self, limit: int = 10) -> Result[tuple[StoredExperiment, ...], StorageError]:
        """Load the newest experiments and their bad plays.

        Returns:
            Experiments in newest-first order or a typed storage error.
        """
        if limit <= 0:
            return Err(StorageError.OPERATION_FAILED, context_msg="History limit must be positive")

        def select(transaction: Transaction) -> Result[tuple[StoredExperiment, ...], StorageError]:
            rows = transaction.connection.execute(
                """
                SELECT id, seed, seconds, speed, fumble_probability, frames, score,
                       pickups, fumbles, deaths, wins, losses
                FROM analysis_experiment ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            experiments: list[StoredExperiment] = []
            for row in rows:
                bad_plays = transaction.connection.execute(
                    "SELECT tick FROM analysis_bad_play WHERE experiment_id = ? ORDER BY tick",
                    (row[0],),
                ).fetchall()
                experiments.append(
                    StoredExperiment(
                        ExperimentId(row[0]),
                        ExperimentResult(
                            seed=row[1],
                            seconds=row[2],
                            speed=row[3],
                            fumble_probability=row[4],
                            frames=row[5],
                            score=row[6],
                            pickups=row[7],
                            fumbles=row[8],
                            deaths=row[9],
                            wins=row[10],
                            losses=row[11],
                            bad_play_ticks=tuple(item[0] for item in bad_plays),
                        ),
                    )
                )
            return Ok(tuple(experiments))

        return self.transaction(select)
