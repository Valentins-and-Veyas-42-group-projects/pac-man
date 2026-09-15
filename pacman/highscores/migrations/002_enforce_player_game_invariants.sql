BEGIN IMMEDIATE;

-- Version 1 existed briefly without rebuilding every pre-existing schema.
-- Rebuild once more so databases already marked at version 1 are verified.
CREATE TABLE player_v2 (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE game_v2 (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES player_v2(id),
    score INTEGER NOT NULL CHECK (score >= 0),
    played_at INTEGER NOT NULL
);

INSERT INTO player_v2(id, name)
SELECT id, name FROM player;
INSERT INTO game_v2(id, player_id, score, played_at)
SELECT id, player_id, score, played_at FROM game;

-- Validate the relationship independently of the connection's PRAGMA state.
CREATE TEMP TABLE migration_fk_guard_v2 (
    violations INTEGER NOT NULL CHECK (violations = 0)
);
INSERT INTO migration_fk_guard_v2
SELECT COUNT(*)
FROM game_v2
LEFT JOIN player_v2 ON player_v2.id = game_v2.player_id
WHERE player_v2.id IS NULL;
DROP TABLE migration_fk_guard_v2;

DROP VIEW IF EXISTS player_highscores;
DROP VIEW IF EXISTS global_highscores;
DROP TABLE game;
DROP TABLE player;
ALTER TABLE player_v2 RENAME TO player;
ALTER TABLE game_v2 RENAME TO game;

CREATE INDEX game_global_score_idx
ON game(score DESC, id ASC);
CREATE INDEX game_player_score_idx
ON game(player_id, score DESC, id ASC);

CREATE VIEW global_highscores AS
SELECT
    game.id AS game_id,
    player.id AS player_id,
    player.name AS name,
    game.score AS score,
    game.played_at AS played_at
FROM game JOIN player ON player.id = game.player_id;

CREATE VIEW player_highscores AS
SELECT
    game.id AS game_id,
    player.id AS player_id,
    player.name AS name,
    game.score AS score,
    game.played_at AS played_at,
    ROW_NUMBER() OVER (
        PARTITION BY player.id ORDER BY game.score DESC, game.id ASC
    ) AS player_rank
FROM game JOIN player ON player.id = game.player_id;

INSERT INTO schema_migrations(version, name, applied_at)
VALUES (2, 'enforce-player-game-invariants', unixepoch());

COMMIT;
