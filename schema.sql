CREATE TABLE IF NOT EXISTS users (
    discord_id BIGINT,
    riot_id VARCHAR(255) NOT NULL,
    puuid VARCHAR(255) NOT NULL,
    reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (discord_id, riot_id)
);

CREATE TABLE IF NOT EXISTS rank_history (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT,
    riot_id VARCHAR(255),
    tier VARCHAR(50),
    rank VARCHAR(10),
    lp INTEGER,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    games INTEGER DEFAULT 0,
    fetch_date DATE NOT NULL,
    reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (discord_id, riot_id) REFERENCES users(discord_id, riot_id),
    UNIQUE (discord_id, riot_id, fetch_date)
);

CREATE TABLE IF NOT EXISTS schedules (
    id SERIAL PRIMARY KEY,
    schedule_time TIME NOT NULL,
    channel_id BIGINT NOT NULL,
    period_days INTEGER DEFAULT 7,
    created_by BIGINT,
    reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
