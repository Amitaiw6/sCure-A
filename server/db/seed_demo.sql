-- =====================================================================
-- sCure Box — DEMO data (dummy work programs + a little print/cure history).
-- Optional. Idempotent (safe to re-run).
--
-- Apply manually:   psql "$DATABASE_URL" -f server/db/seed_demo.sql
-- Or on start-up:   set env SCURE_SEED_DEMO=1  (db.init_schema applies it)
-- =====================================================================

-- ---- Demo material programs (user "work programs") -------------------
-- Same pattern as seed_presets.sql but is_preset = FALSE.

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('demo-rigid-pa', 'Demo Rigid PA', FALSE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"isPreset":false,"totalDuration":28,"steps":[
  {"step":1,"process":"Heating","temperature":55,"intensity":null,"time":8},
  {"step":2,"process":"Cure","temperature":60,"intensity":null,"time":20,"uvIntensity":40,"timerMode":"on-target","uvStartMode":"at-target"},
  {"step":3,"process":"Cooling","temperature":25,"coolingMode":"slow"}]}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('demo-flex-tpu', 'Demo Flexible TPU', FALSE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"isPreset":false,"totalDuration":27,"steps":[
  {"step":1,"process":"Drying","temperature":45,"intensity":null,"time":10},
  {"step":2,"process":"Heating","temperature":50,"intensity":null,"time":5},
  {"step":3,"process":"Cure","temperature":50,"intensity":null,"time":12,"uvIntensity":25,"timerMode":"on-target","uvStartMode":"at-target"},
  {"step":4,"process":"Cooling","temperature":25,"coolingMode":"medium"}]}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('demo-tough-1500', 'Demo Tough 1500', FALSE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"isPreset":false,"totalDuration":43,"steps":[
  {"step":1,"process":"Heating","temperature":70,"intensity":null,"time":8},
  {"step":2,"process":"Cure","temperature":70,"intensity":null,"time":25,"uvIntensity":50,"timerMode":"on-target","uvStartMode":"at-start"},
  {"step":3,"process":"Bleacher","temperature":70,"intensity":null,"time":10,"uvIntensity":40,"timerMode":"on-target","uvStartMode":"at-target"},
  {"step":4,"process":"Cooling","temperature":30,"coolingMode":"slow"}]}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('demo-dental', 'Demo Dental Model', FALSE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"isPreset":false,"totalDuration":20,"steps":[
  {"step":1,"process":"Heating","temperature":40,"intensity":null,"time":5},
  {"step":2,"process":"Nitrogen","temperature":null,"intensity":null,"time":0},
  {"step":3,"process":"Cure","temperature":40,"intensity":null,"time":15,"uvIntensity":30,"timerMode":"on-target","uvStartMode":"at-target"},
  {"step":4,"process":"Cooling","temperature":25,"coolingMode":"fast"}]}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('demo-castable', 'Demo Castable Wax', FALSE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"isPreset":false,"totalDuration":22,"steps":[
  {"step":1,"process":"Drying","temperature":40,"intensity":null,"time":8},
  {"step":2,"process":"Heating","temperature":45,"intensity":null,"time":4},
  {"step":3,"process":"Cure","temperature":45,"intensity":null,"time":10,"uvIntensity":20,"timerMode":"on-target","uvStartMode":"at-target"},
  {"step":4,"process":"Cooling","temperature":25,"coolingMode":"medium"}]}'::jsonb FROM ins;

-- ---- Demo print + cure history --------------------------------------
DO $$
DECLARE jid uuid; pid uuid;
BEGIN
  IF EXISTS (SELECT 1 FROM prints WHERE ext_id LIKE 'demo-print-%') THEN
    RAISE NOTICE 'Demo print history already present — skipping.';
    RETURN;
  END IF;

  INSERT INTO printers (serial_number, model, status) VALUES
    ('OR200001', 'Origin One', 'online'),
    ('OR200002', 'Origin One', 'online')
  ON CONFLICT (serial_number) DO NOTHING;

  INSERT INTO cure_boxes (serial_number, model, status) VALUES
    ('SC-DEMO-01', 'sCure Box', 'online')
  ON CONFLICT (serial_number) DO NOTHING;

  -- #105 Demo Dental Model — error (newest)
  INSERT INTO jobs (material_id) VALUES ((SELECT id FROM materials WHERE name='Demo Dental Model' LIMIT 1)) RETURNING id INTO jid;
  INSERT INTO prints (ext_id, printer_id, job_id, name, start_time, end_time, status)
    VALUES ('demo-print-5', (SELECT id FROM printers WHERE serial_number='OR200001'), jid, 'Print #105',
            TIMESTAMPTZ '2026-06-24 09:15:00+00', TIMESTAMPTZ '2026-06-24 09:25:00+00', 'error') RETURNING id INTO pid;
  INSERT INTO cure_runs (ext_id, print_id, steps, steps_completed, target_temp, phases, started_at, ended_at, status)
    VALUES ('demo-print-5', pid, 4, 1, 40, '["Heating","Nitrogen","Cure","Cooling"]'::jsonb,
            TIMESTAMPTZ '2026-06-24 09:15:00+00', TIMESTAMPTZ '2026-06-24 09:25:00+00', 'error');

  -- #104 ST45 (preset) — completed
  INSERT INTO jobs (material_id) VALUES ((SELECT id FROM materials WHERE name='ST45' LIMIT 1)) RETURNING id INTO jid;
  INSERT INTO prints (ext_id, printer_id, job_id, name, start_time, end_time, status)
    VALUES ('demo-print-4', (SELECT id FROM printers WHERE serial_number='OR200002'), jid, 'Print #104',
            TIMESTAMPTZ '2026-06-23 14:00:00+00', TIMESTAMPTZ '2026-06-23 14:35:00+00', 'completed') RETURNING id INTO pid;
  INSERT INTO cure_runs (ext_id, print_id, cure_box_id, steps, steps_completed, target_temp, phases, started_at, ended_at, status)
    VALUES ('demo-print-4', pid, (SELECT id FROM cure_boxes WHERE serial_number='SC-DEMO-01'), 5, 5, 60,
            '["Drying","Heating","Cure","Cooling","Drying"]'::jsonb,
            TIMESTAMPTZ '2026-06-23 14:00:00+00', TIMESTAMPTZ '2026-06-23 14:35:00+00', 'completed');

  -- #103 Demo Tough 1500 — aborted
  INSERT INTO jobs (material_id) VALUES ((SELECT id FROM materials WHERE name='Demo Tough 1500' LIMIT 1)) RETURNING id INTO jid;
  INSERT INTO prints (ext_id, printer_id, job_id, name, start_time, end_time, status)
    VALUES ('demo-print-3', (SELECT id FROM printers WHERE serial_number='OR200002'), jid, 'Print #103',
            TIMESTAMPTZ '2026-06-22 11:05:00+00', TIMESTAMPTZ '2026-06-22 11:20:00+00', 'aborted') RETURNING id INTO pid;
  INSERT INTO cure_runs (ext_id, print_id, steps, steps_completed, target_temp, phases, started_at, ended_at, status)
    VALUES ('demo-print-3', pid, 4, 2, 70, '["Heating","Cure","Bleaching","Cooling"]'::jsonb,
            TIMESTAMPTZ '2026-06-22 11:05:00+00', TIMESTAMPTZ '2026-06-22 11:20:00+00', 'aborted');

  -- #102 Demo Flexible TPU — completed
  INSERT INTO jobs (material_id) VALUES ((SELECT id FROM materials WHERE name='Demo Flexible TPU' LIMIT 1)) RETURNING id INTO jid;
  INSERT INTO prints (ext_id, printer_id, job_id, name, start_time, end_time, status)
    VALUES ('demo-print-2', (SELECT id FROM printers WHERE serial_number='OR200001'), jid, 'Print #102',
            TIMESTAMPTZ '2026-06-21 16:40:00+00', TIMESTAMPTZ '2026-06-21 17:07:00+00', 'completed') RETURNING id INTO pid;
  INSERT INTO cure_runs (ext_id, print_id, cure_box_id, steps, steps_completed, target_temp, phases, started_at, ended_at, status)
    VALUES ('demo-print-2', pid, (SELECT id FROM cure_boxes WHERE serial_number='SC-DEMO-01'), 4, 4, 50,
            '["Drying","Heating","Cure","Cooling"]'::jsonb,
            TIMESTAMPTZ '2026-06-21 16:40:00+00', TIMESTAMPTZ '2026-06-21 17:07:00+00', 'completed');

  -- #101 Demo Rigid PA — completed (oldest, gets telemetry + a report)
  INSERT INTO jobs (material_id) VALUES ((SELECT id FROM materials WHERE name='Demo Rigid PA' LIMIT 1)) RETURNING id INTO jid;
  INSERT INTO prints (ext_id, printer_id, job_id, name, start_time, end_time, status)
    VALUES ('demo-print-1', (SELECT id FROM printers WHERE serial_number='OR200001'), jid, 'Print #101',
            TIMESTAMPTZ '2026-06-20 10:00:00+00', TIMESTAMPTZ '2026-06-20 10:28:00+00', 'completed') RETURNING id INTO pid;
  INSERT INTO cure_runs (ext_id, print_id, cure_box_id, steps, steps_completed, target_temp, phases, started_at, ended_at, status)
    VALUES ('demo-print-1', pid, (SELECT id FROM cure_boxes WHERE serial_number='SC-DEMO-01'), 3, 3, 60,
            '["Heating","Cure","Cooling"]'::jsonb,
            TIMESTAMPTZ '2026-06-20 10:00:00+00', TIMESTAMPTZ '2026-06-20 10:28:00+00', 'completed');

  -- telemetry for demo-print-1 (so Cure History shows a downloadable report)
  INSERT INTO cure_run_telemetry (cure_run_id, t, chamber_temp, uv_on, uv_type)
  SELECT cr.id, g.t * 30,
         LEAST(60, 25 + g.t * 3.5),
         (g.t >= 8),
         CASE WHEN g.t >= 8 THEN '405nm' ELSE NULL END
  FROM cure_runs cr, generate_series(0, 24) AS g(t)
  WHERE cr.ext_id = 'demo-print-1';

  INSERT INTO cure_reports (cure_run_id, format, content, summary)
  SELECT cr.id, 'html',
         '<html><body><h1>Demo Cure Report — Demo Rigid PA</h1><p>Completed in 28 min, 3 steps.</p></body></html>',
         '{"materialName":"Demo Rigid PA","status":"completed","duration":1680,"steps":3,"targetTemp":60}'::jsonb
  FROM cure_runs cr WHERE cr.ext_id = 'demo-print-1';

  RAISE NOTICE 'Demo data seeded: 5 programs, 5 prints, telemetry + report on Print #101.';
END $$;
