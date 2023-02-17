CREATE TABLE IF NOT EXISTS guilds (
    guild_id BIGINT PRIMARY KEY,
    prefixes TEXT [],
    disabled_commands TEXT []
);

CREATE TABLE IF NOT EXISTS blacklist (
    user_id BIGINT PRIMARY KEY,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS errors (
    code BIGINT PRIMARY KEY,
    author BIGINT,
    guild_id BIGINT,
    error TEXT,
    message TEXT,
    created TIMESTAMP,
    fixed BOOL,
    followers BIGINT []
);