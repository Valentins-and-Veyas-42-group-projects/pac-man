BEGIN IMMEDIATE;

-- The original project stored a destructive top-ten cache in this table.
-- Creating it here makes the migration work for both new and legacy files.
CREATE TABLE IF NOT EXISTS highscores (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 0)
);

CREATE TABLE IF NOT EXISTS player (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE
);

CREATE TABLE IF NOT EXISTS game (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES player(id),
    score INTEGER NOT NULL CHECK (score >= 0),
    played_at INTEGER NOT NULL
);

-- This insert intentionally aborts instead of ignoring malformed legacy rows.
-- Any failure rolls back the whole migration and leaves `highscores` untouched.
INSERT INTO player(name)
SELECT MIN(name)
FROM highscores
GROUP BY name COLLATE NOCASE;

INSERT INTO game(player_id, score, played_at)
SELECT player.id, highscores.score, 0
FROM highscores
JOIN player ON player.name = highscores.name COLLATE NOCASE;

DROP TABLE highscores;

CREATE INDEX IF NOT EXISTS game_global_score_idx
ON game(score DESC, id ASC);
CREATE INDEX IF NOT EXISTS game_player_score_idx
ON game(player_id, score DESC, id ASC);

CREATE VIEW IF NOT EXISTS global_highscores AS
SELECT
    game.id AS game_id,
    player.id AS player_id,
    player.name AS name,
    game.score AS score,
    game.played_at AS played_at
FROM game JOIN player ON player.id = game.player_id;

CREATE VIEW IF NOT EXISTS player_highscores AS
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
