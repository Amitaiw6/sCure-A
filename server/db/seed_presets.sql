-- Auto-generated preset seed (from public/materials/presets/presets.json).
-- Idempotent: ON CONFLICT (ext_id) DO NOTHING. Applied after schema.sql by db.init_schema().

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('preset-ST45', 'ST45', TRUE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"steps":[{"step":1,"process":"Drying","temperature":45,"intensity":null,"time":10},{"step":2,"process":"Heating","temperature":60,"intensity":null,"time":5},{"step":3,"process":"Cure","temperature":60,"intensity":null,"time":15,"uvIntensity":30,"timerMode":"on-target","uvStartMode":"at-target"},{"step":4,"process":"Cooling","temperature":25,"coolingMode":"medium"},{"step":5,"process":"Drying","temperature":40,"intensity":null,"time":5}],"totalDuration":35,"isPreset":true}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('preset-Carbon Fiber', 'Carbon Fiber', TRUE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"steps":[{"step":1,"process":"Drying","temperature":50,"intensity":null,"time":15},{"step":2,"process":"Heating","temperature":70,"intensity":null,"time":8},{"step":3,"process":"Cure","temperature":70,"intensity":null,"time":20,"uvIntensity":50,"timerMode":"on-target","uvStartMode":"at-start"},{"step":4,"process":"Bleacher","temperature":70,"intensity":null,"time":10,"uvIntensity":40,"timerMode":"on-target","uvStartMode":"at-target"},{"step":5,"process":"Cooling","temperature":30,"coolingMode":"slow"},{"step":6,"process":"Drying","temperature":35,"intensity":null,"time":5}],"totalDuration":58,"isPreset":true}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('preset-Fiberglass', 'Fiberglass', TRUE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"steps":[{"step":1,"process":"Drying","temperature":45,"intensity":null,"time":8},{"step":2,"process":"Heating","temperature":55,"intensity":null,"time":5},{"step":3,"process":"Cure","temperature":55,"intensity":null,"time":15,"uvIntensity":20,"timerMode":"on-target","uvStartMode":"at-target"},{"step":4,"process":"Cooling","temperature":25,"coolingMode":"medium"},{"step":5,"process":"Drying","temperature":30,"intensity":null,"time":5}],"totalDuration":33,"isPreset":true}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('preset-ABS-Like', 'ABS-Like', TRUE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"steps":[{"step":1,"process":"Drying","temperature":40,"intensity":null,"time":10},{"step":2,"process":"Heating","temperature":60,"intensity":null,"time":5},{"step":3,"process":"Cure","temperature":60,"intensity":null,"time":15,"uvIntensity":40,"timerMode":"on-target","uvStartMode":"at-target"},{"step":4,"process":"Cooling","temperature":25,"coolingMode":"slow"},{"step":5,"process":"Nitrogen","temperature":null,"intensity":null},{"step":6,"process":"Heating","temperature":50,"intensity":null,"time":10},{"step":7,"process":"Cooling","temperature":25,"coolingMode":"medium"}],"totalDuration":40,"isPreset":true}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('preset-Dental Model', 'Dental Model', TRUE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"steps":[{"step":1,"process":"Drying","temperature":35,"intensity":null,"time":5},{"step":2,"process":"Cure","temperature":40,"intensity":null,"time":20,"uvIntensity":60,"timerMode":"on-target","uvStartMode":"at-start"},{"step":3,"process":"Bleacher","temperature":40,"intensity":null,"time":10,"uvIntensity":50,"timerMode":"on-target","uvStartMode":"at-target"},{"step":4,"process":"Cooling","temperature":25,"coolingMode":"slow"},{"step":5,"process":"Drying","temperature":30,"intensity":null,"time":5}],"totalDuration":40,"isPreset":true}'::jsonb FROM ins;

WITH ins AS (
  INSERT INTO materials (ext_id, name, is_preset) VALUES ('preset-Flexible', 'Flexible', TRUE)
  ON CONFLICT (ext_id) DO NOTHING RETURNING id)
INSERT INTO cure_profiles (material_id, parameters)
SELECT id, '{"steps":[{"step":1,"process":"Drying","temperature":35,"intensity":null,"time":8},{"step":2,"process":"Heating","temperature":45,"intensity":null,"time":5},{"step":3,"process":"Cure","temperature":45,"intensity":null,"time":25,"uvIntensity":15,"timerMode":"on-target","uvStartMode":"at-target"},{"step":4,"process":"Cooling","temperature":25,"coolingMode":"slow"},{"step":5,"process":"Nitrogen","temperature":null,"intensity":null},{"step":6,"process":"Bleacher","temperature":40,"intensity":null,"time":10,"uvIntensity":20,"timerMode":"on-target","uvStartMode":"at-target"},{"step":7,"process":"Cooling","temperature":25,"coolingMode":"medium"},{"step":8,"process":"Drying","temperature":30,"intensity":null,"time":5}],"totalDuration":53,"isPreset":true}'::jsonb FROM ins;
