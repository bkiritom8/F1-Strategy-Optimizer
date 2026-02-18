-- F1 Strategy Optimizer — Database Schema
-- Apply with: psql -f schema.sql

-- Drivers
CREATE TABLE IF NOT EXISTS drivers (
    driver_id       VARCHAR(50)  PRIMARY KEY,
    code            VARCHAR(3),
    given_name      VARCHAR(100),
    family_name     VARCHAR(100),
    date_of_birth   DATE,
    nationality     VARCHAR(50),
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- Constructors
CREATE TABLE IF NOT EXISTS constructors (
    constructor_id  VARCHAR(50)  PRIMARY KEY,
    name            VARCHAR(100),
    nationality     VARCHAR(50),
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- Seasons
CREATE TABLE IF NOT EXISTS seasons (
    season      INTEGER      PRIMARY KEY,
    url         VARCHAR(500),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Races
CREATE TABLE IF NOT EXISTS races (
    id            SERIAL       PRIMARY KEY,
    season        INTEGER      REFERENCES seasons(season),
    round         INTEGER,
    circuit_id    VARCHAR(50),
    circuit_name  VARCHAR(200),
    country       VARCHAR(100),
    locality      VARCHAR(100),
    lat           DOUBLE PRECISION,
    lng           DOUBLE PRECISION,
    race_name     VARCHAR(200),
    race_date     DATE,
    race_time     TIME,
    url           VARCHAR(500),
    created_at    TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (season, round)
);

-- Race Results
CREATE TABLE IF NOT EXISTS race_results (
    id                  SERIAL          PRIMARY KEY,
    season              INTEGER,
    round               INTEGER,
    driver_id           VARCHAR(50)     REFERENCES drivers(driver_id),
    constructor_id      VARCHAR(50)     REFERENCES constructors(constructor_id),
    grid                INTEGER,
    position            INTEGER,
    position_text       VARCHAR(10),
    points              DOUBLE PRECISION,
    laps                INTEGER,
    status              VARCHAR(100),
    time_millis         INTEGER,
    fastest_lap         INTEGER,
    fastest_lap_time    VARCHAR(20),
    fastest_lap_speed   DOUBLE PRECISION,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (season, round, driver_id)
);

-- Lap Times
CREATE TABLE IF NOT EXISTS lap_times (
    id           SERIAL       PRIMARY KEY,
    season       INTEGER,
    round        INTEGER,
    driver_id    VARCHAR(50)  REFERENCES drivers(driver_id),
    lap          INTEGER,
    position     INTEGER,
    time_millis  INTEGER,
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (season, round, driver_id, lap)
);

-- Pit Stops
CREATE TABLE IF NOT EXISTS pit_stops (
    id               SERIAL       PRIMARY KEY,
    season           INTEGER,
    round            INTEGER,
    driver_id        VARCHAR(50)  REFERENCES drivers(driver_id),
    stop             INTEGER,
    lap              INTEGER,
    time             TIME,
    duration_millis  INTEGER,
    created_at       TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (season, round, driver_id, stop)
);

-- Qualifying
CREATE TABLE IF NOT EXISTS qualifying (
    id              SERIAL       PRIMARY KEY,
    season          INTEGER,
    round           INTEGER,
    driver_id       VARCHAR(50)  REFERENCES drivers(driver_id),
    constructor_id  VARCHAR(50)  REFERENCES constructors(constructor_id),
    number          INTEGER,
    position        INTEGER,
    q1              VARCHAR(20),
    q2              VARCHAR(20),
    q3              VARCHAR(20),
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (season, round, driver_id)
);

-- Driver Standings
CREATE TABLE IF NOT EXISTS driver_standings (
    id              SERIAL          PRIMARY KEY,
    season          INTEGER,
    round           INTEGER,
    driver_id       VARCHAR(50)     REFERENCES drivers(driver_id),
    constructor_id  VARCHAR(50)     REFERENCES constructors(constructor_id),
    points          DOUBLE PRECISION,
    position        INTEGER,
    wins            INTEGER,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (season, round, driver_id)
);

-- Constructor Standings
CREATE TABLE IF NOT EXISTS constructor_standings (
    id              SERIAL          PRIMARY KEY,
    season          INTEGER,
    round           INTEGER,
    constructor_id  VARCHAR(50)     REFERENCES constructors(constructor_id),
    points          DOUBLE PRECISION,
    position        INTEGER,
    wins            INTEGER,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (season, round, constructor_id)
);

-- Weather
CREATE TABLE IF NOT EXISTS weather (
    id              SERIAL          PRIMARY KEY,
    season          INTEGER,
    round           INTEGER,
    circuit_id      VARCHAR(50),
    session_type    VARCHAR(20),
    air_temp        DOUBLE PRECISION,
    track_temp      DOUBLE PRECISION,
    humidity        DOUBLE PRECISION,
    pressure        DOUBLE PRECISION,
    wind_speed      DOUBLE PRECISION,
    wind_direction  DOUBLE PRECISION,
    rainfall        BOOLEAN,
    timestamp       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (season, round, circuit_id, session_type, timestamp)
);

-- Lap Features  (FastF1 — 2018+)
CREATE TABLE IF NOT EXISTS lap_features (
    id                  SERIAL          PRIMARY KEY,
    season              INTEGER         NOT NULL,
    round               INTEGER         NOT NULL,
    circuit_id          VARCHAR(50),
    driver_id           VARCHAR(50)     REFERENCES drivers(driver_id),
    lap_number          INTEGER         NOT NULL,
    lap_time_seconds    DOUBLE PRECISION,
    sector1_time        DOUBLE PRECISION,
    sector2_time        DOUBLE PRECISION,
    sector3_time        DOUBLE PRECISION,
    compound            VARCHAR(20),
    tyre_life           INTEGER,
    stint_number        INTEGER,
    fuel_load_estimate  DOUBLE PRECISION,
    track_temp          DOUBLE PRECISION,
    air_temp            DOUBLE PRECISION,
    is_safety_car       BOOLEAN         DEFAULT FALSE,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (season, round, driver_id, lap_number)
);

-- Telemetry Features  (aggregated per lap — FastF1 — 2018+)
CREATE TABLE IF NOT EXISTS telemetry_features (
    id            SERIAL          PRIMARY KEY,
    season        INTEGER         NOT NULL,
    round         INTEGER         NOT NULL,
    circuit_id    VARCHAR(50),
    driver_id     VARCHAR(50)     REFERENCES drivers(driver_id),
    lap_number    INTEGER         NOT NULL,
    mean_throttle DOUBLE PRECISION,
    std_throttle  DOUBLE PRECISION,
    mean_brake    DOUBLE PRECISION,
    std_brake     DOUBLE PRECISION,
    mean_speed    DOUBLE PRECISION,
    max_speed     DOUBLE PRECISION,
    created_at    TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (season, round, driver_id, lap_number)
);

-- Driver Profiles  (computed from telemetry_features + lap_features)
CREATE TABLE IF NOT EXISTS driver_profiles (
    driver_id          VARCHAR(50)     PRIMARY KEY REFERENCES drivers(driver_id),
    aggression_score   DOUBLE PRECISION,   -- mean max throttle across laps
    consistency_score  DOUBLE PRECISION,   -- 1 / std(lap_time_seconds)
    total_laps         INTEGER,
    updated_at         TIMESTAMPTZ     DEFAULT NOW()
);
