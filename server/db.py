#!/usr/bin/env python3
"""
sCure Box — PostgreSQL data layer.

All print data, released materials and cure reports are managed here. If no
DATABASE_URL is configured (or psycopg2 is missing), `available()` returns
False and the caller (app.py) transparently falls back to the JSON files, so
development still works without a database.

Env:
    DATABASE_URL   e.g. postgresql://scure:scure@localhost:5432/scure
"""

import os
import json
import datetime as _dt

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import ThreadedConnectionPool
    _HAVE_DRIVER = True
except ImportError:  # driver not installed
    _HAVE_DRIVER = False

_POOL = None
_POOL_FAILED = False


def _pool():
    global _POOL, _POOL_FAILED
    if _POOL or _POOL_FAILED:
        return _POOL
    if not (_HAVE_DRIVER and DATABASE_URL):
        _POOL_FAILED = True
        return None
    try:
        _POOL = ThreadedConnectionPool(1, 8, dsn=DATABASE_URL)
    except Exception as e:  # cannot connect
        print(f"[DB] Connection pool init failed: {e}")
        _POOL_FAILED = True
    return _POOL


def available():
    """True when a Postgres database is configured and reachable."""
    return _pool() is not None


class _conn:
    """Context manager yielding a pooled connection (commit/rollback + return)."""
    def __enter__(self):
        self.c = _pool().getconn()
        return self.c

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.c.commit()
        else:
            self.c.rollback()
        _pool().putconn(self.c)
        return False


def _dictcur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _rows(conn, sql, args=None):
    with _dictcur(conn) as cur:
        cur.execute(sql, args or ())
        return [dict(r) for r in cur.fetchall()]


def init_schema():
    """Apply server/db/schema.sql then seed presets (both idempotent)."""
    if not available():
        return False
    base = os.path.dirname(__file__)
    with _conn() as conn, conn.cursor() as cur:
        with open(os.path.join(base, 'db', 'schema.sql'), 'r', encoding='utf-8') as f:
            cur.execute(f.read())
        seed = os.path.join(base, 'db', 'seed_presets.sql')
        if os.path.exists(seed):
            with open(seed, 'r', encoding='utf-8') as f:
                cur.execute(f.read())
        # Optional demo data (dummy programs + print/cure history). Off by default.
        demo = os.path.join(base, 'db', 'seed_demo.sql')
        if os.environ.get('SCURE_SEED_DEMO') and os.path.exists(demo):
            with open(demo, 'r', encoding='utf-8') as f:
                cur.execute(f.read())
    return True


def _end_time(date, duration):
    """date (ISO str) + duration (seconds) → end timestamp, best-effort."""
    if not date or duration is None:
        return None
    try:
        d = _dt.datetime.fromisoformat(str(date).replace('Z', '+00:00'))
        return (d + _dt.timedelta(seconds=int(duration))).isoformat()
    except Exception:
        return None


# ============================================================
# Released materials / user programs  (materials + cure_profiles)
# ============================================================

def get_materials(presets_only=None):
    with _conn() as conn:
        rows = _rows(conn, "SELECT * FROM v_materials")
    if presets_only is True:
        rows = [r for r in rows if r['isPreset']]
    if presets_only is False:
        rows = [r for r in rows if not r['isPreset']]
    return rows


def replace_user_materials(materials):
    """Full replace of the user's programs (is_preset = false). Presets untouched."""
    with _conn() as conn, conn.cursor() as cur:
        keep = []
        for m in materials or []:
            ext = str(m.get('id'))
            keep.append(ext)
            params = {
                'steps': m.get('steps', []),
                'totalDuration': m.get('totalDuration', 0),
                'isPreset': False,
                'csvFile': m.get('csvFile'),
            }
            cur.execute(
                """INSERT INTO materials (ext_id, name, is_preset)
                   VALUES (%s, %s, FALSE)
                   ON CONFLICT (ext_id) DO UPDATE SET name = EXCLUDED.name
                   RETURNING id""",
                (ext, m.get('name', 'Untitled')),
            )
            mid = cur.fetchone()[0]
            cur.execute("DELETE FROM cure_profiles WHERE material_id = %s", (mid,))
            cur.execute(
                "INSERT INTO cure_profiles (material_id, parameters) VALUES (%s, %s)",
                (mid, psycopg2.extras.Json(params)),
            )
        # remove user programs no longer present
        if keep:
            cur.execute(
                "DELETE FROM materials WHERE is_preset = FALSE AND ext_id IS NOT NULL AND NOT (ext_id = ANY(%s))",
                (keep,),
            )
        else:
            cur.execute("DELETE FROM materials WHERE is_preset = FALSE AND ext_id IS NOT NULL")
    return True


def _find_or_create_material(cur, name):
    cur.execute("SELECT id FROM materials WHERE name = %s ORDER BY is_preset DESC LIMIT 1", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO materials (name) VALUES (%s) RETURNING id", (name,))
    return cur.fetchone()[0]


def _upsert_printer(cur, serial):
    if not serial:
        return None
    cur.execute(
        """INSERT INTO printers (serial_number) VALUES (%s)
           ON CONFLICT (serial_number) DO UPDATE SET serial_number = EXCLUDED.serial_number
           RETURNING id""",
        (serial,),
    )
    return cur.fetchone()[0]


# ============================================================
# Print history  (prints + jobs + printers + cure_runs)
# ============================================================

def get_print_history():
    with _conn() as conn:
        return _rows(conn, "SELECT * FROM v_print_history")


def replace_print_history(logs):
    """Full replace of print history from the app's denormalized records."""
    with _conn() as conn, conn.cursor() as cur:
        keep = []
        for log in logs or []:
            ext = str(log.get('id'))
            keep.append(ext)
            printer_id = _upsert_printer(cur, log.get('printerName'))
            material_id = _find_or_create_material(cur, log.get('materialName')) if log.get('materialName') else None
            start = log.get('date')
            end = _end_time(start, log.get('duration'))
            # print row
            cur.execute(
                """INSERT INTO prints (ext_id, printer_id, name, start_time, end_time, status)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (ext_id) DO UPDATE
                     SET printer_id = EXCLUDED.printer_id, name = EXCLUDED.name,
                         start_time = EXCLUDED.start_time, end_time = EXCLUDED.end_time,
                         status = EXCLUDED.status
                   RETURNING id, job_id""",
                (ext, printer_id, log.get('printName'), start, end, log.get('status')),
            )
            pid, job_id = cur.fetchone()
            if job_id is None and material_id is not None:
                cur.execute("INSERT INTO jobs (material_id) VALUES (%s) RETURNING id", (material_id,))
                job_id = cur.fetchone()[0]
                cur.execute("UPDATE prints SET job_id = %s WHERE id = %s", (job_id, pid))
            # cure run summary for this print (steps / status shown in history)
            cur.execute(
                """INSERT INTO cure_runs (ext_id, print_id, steps, started_at, ended_at, status)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (ext_id) DO UPDATE
                     SET print_id = EXCLUDED.print_id, steps = EXCLUDED.steps,
                         started_at = EXCLUDED.started_at, ended_at = EXCLUDED.ended_at,
                         status = EXCLUDED.status""",
                (ext, pid, log.get('steps'), start, end, log.get('status')),
            )
        # delete removed entries
        if keep:
            cur.execute("DELETE FROM cure_runs WHERE ext_id IS NOT NULL AND NOT (ext_id = ANY(%s))", (keep,))
            cur.execute("DELETE FROM prints WHERE ext_id IS NOT NULL AND NOT (ext_id = ANY(%s))", (keep,))
        else:
            cur.execute("DELETE FROM cure_runs WHERE ext_id IS NOT NULL")
            cur.execute("DELETE FROM prints WHERE ext_id IS NOT NULL")
    return True


# ============================================================
# Cure runs, telemetry & the cure report
# ============================================================

def get_cure_history():
    with _conn() as conn:
        return _rows(conn, "SELECT * FROM v_cure_history")


def _cure_run_id(cur, ext_id):
    cur.execute("SELECT id FROM cure_runs WHERE ext_id = %s", (str(ext_id),))
    row = cur.fetchone()
    return row[0] if row else None


def start_cure_run(ext_id, material_name, steps, phases, target_temp, serial_number=None):
    with _conn() as conn, conn.cursor() as cur:
        box_id = None
        if serial_number:
            cur.execute(
                """INSERT INTO cure_boxes (serial_number) VALUES (%s)
                   ON CONFLICT (serial_number) DO UPDATE SET serial_number = EXCLUDED.serial_number
                   RETURNING id""",
                (serial_number,),
            )
            box_id = cur.fetchone()[0]
        material_id = _find_or_create_material(cur, material_name) if material_name else None
        cur.execute(
            """INSERT INTO cure_runs (ext_id, cure_box_id, steps, steps_completed, target_temp, phases, started_at, status)
               VALUES (%s, %s, %s, 0, %s, %s, now(), 'running')
               ON CONFLICT (ext_id) DO UPDATE
                 SET cure_box_id = EXCLUDED.cure_box_id, steps = EXCLUDED.steps,
                     target_temp = EXCLUDED.target_temp, phases = EXCLUDED.phases,
                     started_at = EXCLUDED.started_at, status = 'running'
               RETURNING id""",
            (str(ext_id), box_id, steps, target_temp, psycopg2.extras.Json(phases or []),),
        )
        _ = material_id  # material linkage is via the print; kept for future use
        return cur.fetchone()[0]


def finish_cure_run(ext_id, status, steps_completed=None):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE cure_runs
               SET status = %s, ended_at = now(),
                   steps_completed = COALESCE(%s, steps_completed)
               WHERE ext_id = %s""",
            (status, steps_completed, str(ext_id)),
        )
        return cur.rowcount > 0


def record_telemetry(ext_id, sample):
    with _conn() as conn, conn.cursor() as cur:
        run_id = _cure_run_id(cur, ext_id)
        if not run_id:
            return False
        led = sample.get('ledTemps') or {}
        cur.execute(
            """INSERT INTO cure_run_telemetry
                 (cure_run_id, t, chamber_temp, uv_on, uv_type, led_right, led_left, led_door, led_back)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (run_id, sample.get('t'), sample.get('chamberTemp'), sample.get('uvOn'),
             sample.get('uvType'), led.get('right'), led.get('left'), led.get('door'), led.get('back')),
        )
        return True


def save_report(ext_id, content, summary=None, fmt='html'):
    """Persist a generated cure report for a run (by app cure-log id)."""
    with _conn() as conn, conn.cursor() as cur:
        run_id = _cure_run_id(cur, ext_id)
        if not run_id:
            # create a minimal run so the report has a home
            cur.execute(
                "INSERT INTO cure_runs (ext_id, status) VALUES (%s, 'completed') RETURNING id",
                (str(ext_id),),
            )
            run_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO cure_reports (cure_run_id, format, content, summary) VALUES (%s, %s, %s, %s) RETURNING id",
            (run_id, fmt, content, psycopg2.extras.Json(summary) if summary is not None else None),
        )
        return str(cur.fetchone()[0])


def get_report(ext_id):
    with _conn() as conn:
        rows = _rows(
            conn,
            """SELECT r.id::text AS id, r.format, r.content, r.summary, r.generated_at
               FROM cure_reports r JOIN cure_runs cr ON cr.id = r.cure_run_id
               WHERE cr.ext_id = %s ORDER BY r.generated_at DESC LIMIT 1""",
            (str(ext_id),),
        )
    return rows[0] if rows else None
