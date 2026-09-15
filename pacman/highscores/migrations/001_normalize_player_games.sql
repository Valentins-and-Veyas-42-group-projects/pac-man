BEGIN IMMEDIATE;

-- The original project stored a destructive top-ten cache in this table.
-- Creating it here makes the migration work for both new and legacy files.
CREATE TABLE IF NOT EXISTS highscores (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 0)
);

-- These compatibility definitions let us rebuild both a new database and the
-- schema used by earlier revisions. Existing definitions are never trusted:
-- every row is copied through the constraints on the staging tables below.
CREATE TABLE IF NOT EXISTS player (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS game (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES player(id),
    score INTEGER NOT NULL CHECK (score >= 0),
    played_at INTEGER NOT NULL
);

CREATE TABLE player_v1 (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE game_v1 (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES player_v1(id),
    score INTEGER NOT NULL CHECK (score >= 0),
    played_at INTEGER NOT NULL
);

-- Copying through the staging constraints makes nullable/orphaned games,
-- duplicate players, negative scores, and malformed legacy rows abort the
-- entire migration instead of certifying an invalid schema.
INSERT INTO player_v1(id, name)
SELECT id, name FROM player;

INSERT INTO game_v1(id, player_id, score, played_at)
SELECT id, player_id, score, played_at FROM game;

INSERT INTO player_v1(name)
SELECT DISTINCT highscores.name
FROM highscores
WHERE NOT EXISTS (
    SELECT 1 FROM player_v1 WHERE player_v1.name = highscores.name
);

INSERT INTO game_v1(player_id, score, played_at)
SELECT player_v1.id, highscores.score, 0
FROM highscores
JOIN player_v1 ON player_v1.name = highscores.name;

DROP VIEW IF EXISTS player_highscores;
DROP VIEW IF EXISTS global_highscores;
DROP TABLE game;
DROP TABLE player;
DROP TABLE highscores;
ALTER TABLE player_v1 RENAME TO player;
ALTER TABLE game_v1 RENAME TO game;

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
VALUES (1, 'normalize-player-games', unixepoch());

COMMIT;
