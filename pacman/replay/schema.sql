PRAGMA foreign_keys = ON;

PRAGMA journal_mode = WAL;

PRAGMA synchronous = NORMAL;

CREATE TABLE maze (
    id INTEGER PRIMARY KEY,
    width INTEGER NOT NULL CHECK (width BETWEEN 1 AND 255),
    height INTEGER NOT NULL CHECK (height BETWEEN 1 AND 255),
    entry_x INTEGER NOT NULL,
    entry_y INTEGER NOT NULL,
    exit_x INTEGER NOT NULL,
    exit_y INTEGER NOT NULL,
    topology BLOB NOT NULL,
    initial_collectibles BLOB NOT NULL,
    CHECKSUM BLOB NOT NULL UNIQUE
) STRICT;

CREATE TABLE replay (
    id INTEGER PRIMARY KEY,
    maze_id INTEGER NOT NULL,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    tick_hz INTEGER NOT NULL CHECK (tick_hz BETWEEN 1 AND 255),
    LEVEL INTEGER NOT NULL CHECK (LEVEL > 0),
    simulation_version INTEGER NOT NULL CHECK (simulation_version >= 0),
    config_hash BLOB NOT NULL,
    rng_seed INTEGER NOT NULL,
    FOREIGN KEY (maze_id) REFERENCES maze(id)
) STRICT;

CREATE TABLE frame (
    replay_id INTEGER NOT NULL,
    tick INTEGER NOT NULL CHECK (tick >= 0),
    pac_x INTEGER NOT NULL,
    pac_y INTEGER NOT NULL,
    pac_dir INTEGER NOT NULL CHECK (pac_dir BETWEEN 0 AND 3),
    score INTEGER NOT NULL CHECK (score >= 0),
    lives INTEGER NOT NULL CHECK (lives BETWEEN 0 AND 255),
    phase INTEGER NOT NULL,
    PRIMARY KEY (replay_id, tick),
    FOREIGN KEY (replay_id) REFERENCES replay(id) ON DELETE CASCADE
) WITHOUT ROWID,
STRICT;

CREATE TABLE ghost_frame (
    replay_id INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    ghost INTEGER NOT NULL CHECK (ghost BETWEEN 0 AND 3),
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    direction INTEGER NOT NULL CHECK (direction BETWEEN 0 AND 3),
    state INTEGER NOT NULL,
    PRIMARY KEY (replay_id, tick, ghost),
    FOREIGN KEY (replay_id, tick) REFERENCES frame(replay_id, tick) ON DELETE CASCADE
) WITHOUT ROWID,
STRICT;

CREATE TABLE collectible_change (
    replay_id INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    tile INTEGER NOT NULL CHECK (tile >= 0),
    collectible INTEGER NOT NULL,
    PRIMARY KEY (replay_id, tick, tile),
    FOREIGN KEY (replay_id, tick) REFERENCES frame(replay_id, tick) ON DELETE CASCADE
) WITHOUT ROWID,
STRICT;
