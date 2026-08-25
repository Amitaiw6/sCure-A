-- Stratasys Manufacturing Database — PostgreSQL schema (ARCHITECTURE.md §4.6)
-- The dev/test server (app.py with SQLite) creates an equivalent schema
-- automatically; this file is the production reference.

CREATE TABLE IF NOT EXISTS serial_counter (
    id            SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_number   INTEGER  NOT NULL DEFAULT 0          -- SC000000 = nothing assigned yet
);
INSERT INTO serial_counter (id, last_number) VALUES (1, 0) ON CONFLICT DO NOTHING;

-- Every number the counter ever produced, in every state. Numbers are burned
-- on allocation: RESERVED -> ASSIGNED (committed) | VOID (expired/failed).
CREATE TABLE IF NOT EXISTS serial_allocations (
    serial           CHAR(8)     PRIMARY KEY,           -- SC000126
    number           INTEGER     NOT NULL UNIQUE,
    state            TEXT        NOT NULL CHECK (state IN ('RESERVED','ASSIGNED','VOID','RANGE')),
    allocation_id    UUID        NOT NULL UNIQUE,
    station_id       TEXT        NOT NULL,
    operator         TEXT        NOT NULL,
    reason           TEXT        NOT NULL DEFAULT 'provisioning',   -- provisioning | reassignment | range
    previous_serial  CHAR(8)     REFERENCES serial_allocations(serial),
    range_id         UUID,
    reserved_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reserved_until   TIMESTAMPTZ,
    committed_at     TIMESTAMPTZ
);

-- Signed pre-allocated ranges for offline stations (§4.4).
CREATE TABLE IF NOT EXISTS serial_ranges (
    range_id      UUID        PRIMARY KEY,
    station_id    TEXT        NOT NULL,
    first_number  INTEGER     NOT NULL,
    last_number   INTEGER     NOT NULL,
    issued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    token         JSONB       NOT NULL,            -- the signed envelope handed to the station
    reconciled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS devices (
    device_id            TEXT        PRIMARY KEY,     -- DEV-...
    public_key_pem       TEXT        NOT NULL,
    identity_backend     TEXT        NOT NULL,        -- otp-hkdf | tpm2 | software
    board_serial         TEXT,
    board_revision       TEXT,
    hardware_fingerprint TEXT,
    secure_boot          BOOLEAN     NOT NULL DEFAULT false,
    registered_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS machines (
    serial            CHAR(8)     PRIMARY KEY REFERENCES serial_allocations(serial),
    device_id         TEXT        NOT NULL REFERENCES devices(device_id),
    product_type      TEXT        NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'PROVISIONING',   -- PROVISIONING | READY_FOR_PRODUCTION | FAILED | RETIRED
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS licenses (
    license_id     UUID        PRIMARY KEY,
    serial         CHAR(8)     NOT NULL REFERENCES serial_allocations(serial),
    device_id      TEXT        NOT NULL REFERENCES devices(device_id),
    envelope       JSONB       NOT NULL,             -- signed license as issued
    provisional    BOOLEAN     NOT NULL DEFAULT false,
    issued_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at     TIMESTAMPTZ,
    revoke_reason  TEXT
);

-- Image catalog (§4.5). approval is the only thing the factory tool obeys.
CREATE TABLE IF NOT EXISTS images (
    build_id             TEXT        PRIMARY KEY,
    product              TEXT        NOT NULL,
    image_version        TEXT        NOT NULL,
    channel              TEXT        NOT NULL CHECK (channel IN ('development','qa','production')),
    production_approved  BOOLEAN     NOT NULL DEFAULT false,
    withdrawn            BOOLEAN     NOT NULL DEFAULT false,
    manifest             JSONB       NOT NULL,       -- signed envelope
    approved_by          TEXT,
    approved_at          TIMESTAMPTZ,
    published_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provisioning_runs (
    run_id              UUID        PRIMARY KEY,
    serial              CHAR(8)     REFERENCES serial_allocations(serial),
    device_id           TEXT        REFERENCES devices(device_id),
    station_id          TEXT        NOT NULL,
    operator            TEXT        NOT NULL,
    image_version       TEXT,
    build_id            TEXT,
    image_sha256        TEXT,
    app_version         TEXT,
    online              BOOLEAN     NOT NULL,          -- station had server access during the run
    result              TEXT        NOT NULL,          -- READY_FOR_PRODUCTION | FAILED | ABORTED
    step_log            JSONB       NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    finished_at         TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS update_history (
    id            BIGSERIAL   PRIMARY KEY,
    serial        CHAR(8)     NOT NULL REFERENCES serial_allocations(serial),
    from_version  TEXT,
    to_version    TEXT,
    source        TEXT,
    result        TEXT        NOT NULL,   -- SUCCESS | ROLLED_BACK | REJECTED
    reported_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- LUKS recovery passphrases, encrypted to the Stratasys service KMS key —
-- never in clear.
CREATE TABLE IF NOT EXISTS recovery_keys (
    serial         CHAR(8)     PRIMARY KEY REFERENCES serial_allocations(serial),
    ciphertext     BYTEA       NOT NULL,
    kms_key_id     TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only, hash-chained (same chain format as the device audit log).
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    serial      CHAR(8),
    device_id   TEXT,
    actor       TEXT        NOT NULL,
    event       TEXT        NOT NULL,
    detail      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    prev_hash   CHAR(64)    NOT NULL,
    hash        CHAR(64)    NOT NULL UNIQUE
);
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
