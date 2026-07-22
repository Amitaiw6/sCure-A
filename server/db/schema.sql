-- =====================================================================
-- sCure Box — PostgreSQL schema
-- Canonical data model for print data, released materials, cure runs and
-- the cure report. Implements the project ER model (Origin / sCure).
--
-- Apply:  psql "$DATABASE_URL" -f server/db/schema.sql
-- Idempotent: safe to re-run (CREATE ... IF NOT EXISTS).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- Released materials & their chemistry
-- ---------------------------------------------------------------------

-- Raw resin lot (the released chemistry).
CREATE TABLE IF NOT EXISTS resins (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    supplier     TEXT,
    lot_number   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A released material (a named, versioned formulation derived from a resin).
CREATE TABLE IF NOT EXISTS materials (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ext_id       TEXT UNIQUE,                       -- app-provided material/program id
    resin_id     UUID REFERENCES resins(id) ON DELETE SET NULL,
    name         TEXT NOT NULL,
    version      TEXT,
    is_preset    BOOLEAN NOT NULL DEFAULT FALSE,   -- system-provided vs. user program
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Curing recipe. A resin has a default profile; a material may override it.
-- `parameters` holds the ordered cure steps and derived fields
-- (steps[], total_duration, timer/uv modes, cooling mode, …).
CREATE TABLE IF NOT EXISTS cure_profiles (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cure_unit_id   UUID,                                       -- optional: unit the profile targets
    resin_id       UUID REFERENCES resins(id)    ON DELETE SET NULL,   -- defines default
    material_id    UUID REFERENCES materials(id) ON DELETE CASCADE,    -- overrides
    parameters     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cure_profiles_material ON cure_profiles(material_id);
CREATE INDEX IF NOT EXISTS ix_cure_profiles_resin    ON cure_profiles(resin_id);

-- ---------------------------------------------------------------------
-- Printing side
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS printers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_number TEXT UNIQUE,
    model         TEXT,
    status        TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_id   UUID REFERENCES materials(id) ON DELETE SET NULL,   -- uses
    print_spec_id UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prints (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ext_id      TEXT UNIQUE,                                       -- app-provided print/history id
    job_id      UUID REFERENCES jobs(id)     ON DELETE SET NULL,   -- executes
    printer_id  UUID REFERENCES printers(id) ON DELETE SET NULL,   -- runs on
    name        TEXT,                                              -- display label, e.g. "Print #008"
    start_time  TIMESTAMPTZ,
    end_time    TIMESTAMPTZ,
    status      TEXT
);
CREATE INDEX IF NOT EXISTS ix_prints_printer ON prints(printer_id);
CREATE INDEX IF NOT EXISTS ix_prints_start   ON prints(start_time DESC);

-- Print consumables (per-print binding of the build head and tray membrane).
CREATE TABLE IF NOT EXISTS build_heads (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_number TEXT UNIQUE,
    hw_revision   TEXT,
    status        TEXT
);

CREATE TABLE IF NOT EXISTS tray_membranes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_number TEXT UNIQUE,
    membrane_type TEXT,
    max_slices    INTEGER,
    status        TEXT
);

CREATE TABLE IF NOT EXISTS print_hardware (
    print_id         UUID PRIMARY KEY REFERENCES prints(id)         ON DELETE CASCADE,   -- binds
    build_head_id    UUID REFERENCES build_heads(id)    ON DELETE SET NULL,              -- uses
    tray_membrane_id UUID REFERENCES tray_membranes(id) ON DELETE SET NULL,              -- uses
    bound_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Curing side
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cure_boxes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_number TEXT UNIQUE,
    model         TEXT,
    status        TEXT
);

-- A curing session on a cure box (groups one or more cure runs).
CREATE TABLE IF NOT EXISTS cure_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cure_box_id UUID REFERENCES cure_boxes(id) ON DELETE SET NULL,   -- hosts
    started_at  TIMESTAMPTZ,
    ended_at    TIMESTAMPTZ,
    status      TEXT
);

-- A single cure run: one print cured on a box under a profile in a session.
CREATE TABLE IF NOT EXISTS cure_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ext_id            TEXT UNIQUE,                                             -- app-provided cure-log id
    print_id          UUID REFERENCES prints(id)         ON DELETE SET NULL,   -- has (PRINTS → CURE_RUNS)
    build_head_id     UUID REFERENCES build_heads(id)    ON DELETE SET NULL,   -- cured in
    cure_box_id       UUID REFERENCES cure_boxes(id)     ON DELETE SET NULL,   -- executes
    cure_session_id   UUID REFERENCES cure_sessions(id)  ON DELETE SET NULL,   -- groups
    curing_profile_id UUID REFERENCES cure_profiles(id)  ON DELETE SET NULL,   -- applied
    steps             INTEGER,           -- total steps in the applied profile
    steps_completed   INTEGER,
    target_temp       NUMERIC,
    phases            JSONB,             -- e.g. ["Drying","Heating","Cure","Cooling"]
    started_at        TIMESTAMPTZ,
    ended_at          TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'running'   -- running | completed | aborted | error
);
CREATE INDEX IF NOT EXISTS ix_cure_runs_print   ON cure_runs(print_id);
CREATE INDEX IF NOT EXISTS ix_cure_runs_session ON cure_runs(cure_session_id);
CREATE INDEX IF NOT EXISTS ix_cure_runs_started ON cure_runs(started_at DESC);

-- Per-run telemetry time-series (drives the cure report).
CREATE TABLE IF NOT EXISTS cure_run_telemetry (
    id           BIGSERIAL PRIMARY KEY,
    cure_run_id  UUID NOT NULL REFERENCES cure_runs(id) ON DELETE CASCADE,
    t            INTEGER NOT NULL,           -- seconds since run start
    chamber_temp NUMERIC,
    uv_on        BOOLEAN,
    uv_type      TEXT,                       -- '405nm' | '450nm' | null
    led_right    NUMERIC,
    led_left     NUMERIC,
    led_door     NUMERIC,
    led_back     NUMERIC,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_telemetry_run ON cure_run_telemetry(cure_run_id, t);

-- The generated cure report for a run (persisted, not only downloaded).
CREATE TABLE IF NOT EXISTS cure_reports (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cure_run_id  UUID NOT NULL REFERENCES cure_runs(id) ON DELETE CASCADE,
    format       TEXT NOT NULL DEFAULT 'html',   -- html | pdf | json
    content      TEXT,                           -- rendered report (HTML)
    summary      JSONB,                          -- material, duration, steps, target, serial …
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reports_run ON cure_reports(cure_run_id);

-- ---------------------------------------------------------------------
-- Convenience views — return the shapes the app UI already consumes,
-- so the frontend reads these while the normalized tables stay the source of truth.
-- ---------------------------------------------------------------------

-- Released materials / user programs (§6.5, §6.7) in the app's Material shape.
CREATE OR REPLACE VIEW v_materials AS
SELECT
    COALESCE(m.ext_id, m.id::text)                       AS id,
    m.name                                               AS name,
    m.is_preset                                          AS "isPreset",
    m.created_at                                         AS "createdAt",
    COALESCE(cp.parameters -> 'steps', '[]'::jsonb)      AS steps,
    COALESCE((cp.parameters ->> 'totalDuration')::int, 0) AS "totalDuration"
FROM materials m
LEFT JOIN cure_profiles cp ON cp.material_id = m.id
ORDER BY m.is_preset DESC, m.created_at;

-- Print History rows (§6.4) — one row per print, with its cure summary.
CREATE OR REPLACE VIEW v_print_history AS
SELECT
    COALESCE(p.ext_id, p.id::text)                          AS id,
    COALESCE(p.name, 'Print')                               AS "printName",
    m.name                                                  AS "materialName",
    pr.serial_number                                        AS "printerName",
    COALESCE(p.start_time, cr.started_at)                   AS date,
    COALESCE(
        EXTRACT(EPOCH FROM (p.end_time - p.start_time))::int,
        EXTRACT(EPOCH FROM (cr.ended_at - cr.started_at))::int
    )                                                       AS duration,
    COALESCE(cr.status, p.status)                           AS status,
    cr.steps                                                AS steps,
    (cp.parameters ->> 'csvFile')                           AS "csvFile"
FROM prints p
LEFT JOIN jobs j          ON j.id = p.job_id
LEFT JOIN materials m      ON m.id = j.material_id
LEFT JOIN printers pr      ON pr.id = p.printer_id
LEFT JOIN cure_runs cr     ON cr.print_id = p.id
LEFT JOIN cure_profiles cp ON cp.id = cr.curing_profile_id
ORDER BY date DESC;

-- Cure History rows (§8) — one row per cure run.
CREATE OR REPLACE VIEW v_cure_history AS
SELECT
    COALESCE(cr.ext_id, cr.id::text)     AS id,
    m.name                               AS "materialName",
    cr.steps                             AS steps,
    cr.steps_completed                   AS "stepsCompleted",
    cr.started_at                        AS "startedAt",
    cr.ended_at                          AS "endedAt",
    EXTRACT(EPOCH FROM (cr.ended_at - cr.started_at))::int AS duration,
    cr.status                            AS status,
    cr.phases                            AS phases,
    cr.target_temp                       AS "targetTemp",
    cb.serial_number                     AS "serialNumber",
    COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
                   't', te.t, 'chamberTemp', te.chamber_temp,
                   'uvOn', te.uv_on, 'uvType', te.uv_type,
                   'ledTemps', jsonb_build_object('right', te.led_right, 'left', te.led_left,
                                                  'door', te.led_door, 'back', te.led_back))
                 ORDER BY te.t)
        FROM cure_run_telemetry te WHERE te.cure_run_id = cr.id
    ), '[]'::jsonb)                       AS telemetry
FROM cure_runs cr
LEFT JOIN prints p          ON p.id = cr.print_id
LEFT JOIN jobs j            ON j.id = p.job_id
LEFT JOIN materials m       ON m.id = j.material_id
LEFT JOIN cure_boxes cb     ON cb.id = cr.cure_box_id
ORDER BY cr.started_at DESC;
