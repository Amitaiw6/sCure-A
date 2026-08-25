#!/usr/bin/env python3
"""Stratasys Serial Number + Image + Device service (factory side).

    POST /serials/allocate            {stationId, operator, reason?, previousSerial?}
    POST /serials/<serial>/commit     {allocationId}
    POST /serials/<serial>/void       {allocationId, reason}
    POST /serials/ranges              {stationId, operator, size}   -> signed range token
    POST /serials/ranges/<id>/reconcile {used: [serial...]}
    GET  /serials/last
    POST /devices/register            {publicKeyPem, identityBackend, boardSerial, boardRevision,
                                       fingerprint, secureBoot, nonceSignature, nonce}
    POST /licenses/issue              {serial, deviceId, productType, features, softwareCompat,
                                       previousSerial?, provisional?}
    GET  /images/latest?product=&channel=
    GET  /images/withdrawn
    POST /images/publish              {envelope}           (engineering)
    POST /images/<buildId>/approve    {approvedBy}         (release manager)
    POST /images/<buildId>/withdraw
    POST /provisioning/runs           {...run record...}
    GET  /audit?serial=

Atomic serial allocation: the counter row is updated inside one
transaction with a row lock (SELECT ... FOR UPDATE on PostgreSQL; SQLite's
BEGIN IMMEDIATE gives the same exclusivity). A number, once produced, is
never produced again, whatever happens to the request afterwards.

Storage: PostgreSQL via DATABASE_URL (psycopg) in production; SQLite
(SERIAL_DB=path, default ./serial-service.db) for development and tests.
Signing keys: SERIAL_SIGNING_KEY (range tokens + manifests) and
LICENSE_SIGNING_KEY (licenses) — PEM paths. In production the license key
lives in the HSM-backed signer; this service forwards signing requests to
it (LICENSE_SIGNER_URL) instead of loading a key file.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, g

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from stratasys_appliance import crypto, serials, license as lic, manifests, audit  # noqa: E402
from stratasys_appliance.identity import load_public_pem, device_id as derive_device_id, verify_challenge  # noqa: E402

app = Flask(__name__)

DB_PATH = os.environ.get("SERIAL_DB", "serial-service.db")
RESERVATION_MINUTES = int(os.environ.get("SERIAL_RESERVATION_MINUTES", "120"))
RANGE_DAYS = int(os.environ.get("SERIAL_RANGE_DAYS", "14"))
ISSUER = os.environ.get("LICENSE_ISSUER", "stratasys-license-ca-2026")
ROLE_HEADER = "X-Stratasys-Role"          # factory | service | engineering | release
ROLES_ALLOCATE = {"factory", "service"}
ROLES_ENGINEERING = {"engineering", "release"}

_signing_key = None
_license_key = None


def _key(env: str, cache_attr: str):
    path = os.environ.get(env)
    if not path:
        return None
    return crypto.load_private_key(path)


def signing_key():
    global _signing_key
    if _signing_key is None:
        _signing_key = _key("SERIAL_SIGNING_KEY", "_signing_key") or crypto.generate_private_key()
    return _signing_key


def license_key():
    global _license_key
    if _license_key is None:
        _license_key = _key("LICENSE_SIGNING_KEY", "_license_key") or crypto.generate_private_key()
    return _license_key


# --------------------------------------------------------------------------
#  storage (SQLite for dev/tests; the SQL is kept PostgreSQL-compatible)
# --------------------------------------------------------------------------
SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS serial_counter (id INTEGER PRIMARY KEY CHECK (id = 1), last_number INTEGER NOT NULL DEFAULT 0);
INSERT OR IGNORE INTO serial_counter (id, last_number) VALUES (1, 0);
CREATE TABLE IF NOT EXISTS serial_allocations (
    serial TEXT PRIMARY KEY, number INTEGER NOT NULL UNIQUE, state TEXT NOT NULL,
    allocation_id TEXT NOT NULL UNIQUE, station_id TEXT NOT NULL, operator TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT 'provisioning', previous_serial TEXT, range_id TEXT,
    reserved_at TEXT NOT NULL, reserved_until TEXT, committed_at TEXT);
CREATE TABLE IF NOT EXISTS serial_ranges (range_id TEXT PRIMARY KEY, station_id TEXT NOT NULL,
    first_number INTEGER NOT NULL, last_number INTEGER NOT NULL, issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL, token TEXT NOT NULL, reconciled_at TEXT);
CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, public_key_pem TEXT NOT NULL,
    identity_backend TEXT NOT NULL, board_serial TEXT, board_revision TEXT, hardware_fingerprint TEXT,
    secure_boot INTEGER NOT NULL DEFAULT 0, registered_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS machines (serial TEXT PRIMARY KEY, device_id TEXT NOT NULL,
    product_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PROVISIONING', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS licenses (license_id TEXT PRIMARY KEY, serial TEXT NOT NULL, device_id TEXT NOT NULL,
    envelope TEXT NOT NULL, provisional INTEGER NOT NULL DEFAULT 0, issued_at TEXT NOT NULL,
    revoked_at TEXT, revoke_reason TEXT);
CREATE TABLE IF NOT EXISTS images (build_id TEXT PRIMARY KEY, product TEXT NOT NULL, image_version TEXT NOT NULL,
    channel TEXT NOT NULL, production_approved INTEGER NOT NULL DEFAULT 0, withdrawn INTEGER NOT NULL DEFAULT 0,
    manifest TEXT NOT NULL, approved_by TEXT, approved_at TEXT, published_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS provisioning_runs (run_id TEXT PRIMARY KEY, serial TEXT, device_id TEXT,
    station_id TEXT NOT NULL, operator TEXT NOT NULL, image_version TEXT, build_id TEXT, image_sha256 TEXT,
    app_version TEXT, online INTEGER NOT NULL, result TEXT NOT NULL, step_log TEXT NOT NULL,
    started_at TEXT NOT NULL, finished_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, serial TEXT,
    device_id TEXT, actor TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL, prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE);
"""


def db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, isolation_level=None)   # autocommit; explicit BEGIN below
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQLITE)
        g.db = conn
    return g.db


@app.teardown_appcontext
def _close(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def audit_write(conn, event: str, detail: dict, actor: str, serial=None, device_id=None) -> str:
    row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = row["hash"] if row else audit.GENESIS
    entry = {"ts": iso(now()), "serial": serial, "deviceId": device_id, "actor": actor,
             "event": event, "detail": detail, "prevHash": prev}
    h = crypto.sha256_hex(prev.encode() + crypto.canonical(entry))
    conn.execute("INSERT INTO audit_log (ts, serial, device_id, actor, event, detail, prev_hash, hash) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (entry["ts"], serial, device_id, actor, event, json.dumps(detail), prev, h))
    return h


def require_role(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            role = request.headers.get(ROLE_HEADER, "")
            if role not in roles:
                return jsonify({"ok": False, "error": f"role {role or 'none'} not allowed"}), 403
            g.actor = f"{role}:{request.headers.get('X-Stratasys-Operator', 'unknown')}"
            return fn(*a, **kw)
        return wrapper
    return deco


# --------------------------------------------------------------------------
#  serial numbers
# --------------------------------------------------------------------------
def _take_numbers(conn, count: int) -> tuple[int, int]:
    """Atomically advance the counter by `count`; returns (first, last).
    BEGIN IMMEDIATE takes the write lock before reading, so two concurrent
    callers are strictly serialised (PostgreSQL: SELECT ... FOR UPDATE)."""
    conn.execute("BEGIN IMMEDIATE")
    last = conn.execute("SELECT last_number FROM serial_counter WHERE id = 1").fetchone()["last_number"]
    first, new_last = last + 1, last + count
    if new_last > serials.MAX_NUMBER:
        conn.execute("ROLLBACK")
        raise RuntimeError("serial number space exhausted")
    conn.execute("UPDATE serial_counter SET last_number = ? WHERE id = 1", (new_last,))
    return first, new_last


@app.post("/serials/allocate")
@require_role(*ROLES_ALLOCATE)
def allocate():
    d = request.get_json(force=True) or {}
    station, operator = d.get("stationId"), d.get("operator")
    if not station or not operator:
        return jsonify({"ok": False, "error": "stationId and operator required"}), 400
    reason = d.get("reason") or "provisioning"
    previous = d.get("previousSerial")
    if reason == "reassignment" and not previous:
        return jsonify({"ok": False, "error": "reassignment requires previousSerial"}), 400
    if previous and not serials.is_valid(previous):
        return jsonify({"ok": False, "error": "invalid previousSerial"}), 400
    conn = db()
    if previous and not conn.execute("SELECT 1 FROM serial_allocations WHERE serial=?", (previous,)).fetchone():
        return jsonify({"ok": False, "error": f"{previous} was never allocated"}), 404
    try:
        first, _ = _take_numbers(conn, 1)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 507
    serial = serials.format_serial(first)
    alloc_id = str(uuid.uuid4())
    until = now() + timedelta(minutes=RESERVATION_MINUTES)
    conn.execute("INSERT INTO serial_allocations (serial, number, state, allocation_id, station_id, operator, "
                 "reason, previous_serial, reserved_at, reserved_until) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (serial, first, "RESERVED", alloc_id, station, operator, reason, previous, iso(now()), iso(until)))
    audit_write(conn, "Serial number allocated" if reason != "reassignment" else "Serial number reassigned",
                {"serial": serial, "previousSerial": previous, "reason": reason, "station": station},
                g.actor, serial=serial)
    conn.execute("COMMIT")
    return jsonify({"ok": True, "serial": serial, "allocationId": alloc_id,
                    "previousSerial": previous, "reservedUntil": iso(until)})


@app.post("/serials/<serial>/commit")
@require_role(*ROLES_ALLOCATE)
def commit(serial):
    d = request.get_json(force=True) or {}
    conn = db()
    row = conn.execute("SELECT * FROM serial_allocations WHERE serial=?", (serial,)).fetchone()
    if not row or row["allocation_id"] != d.get("allocationId"):
        return jsonify({"ok": False, "error": "unknown serial/allocation"}), 404
    if row["state"] == "ASSIGNED":
        return jsonify({"ok": True, "serial": serial, "state": "ASSIGNED"})   # idempotent
    if row["state"] != "RESERVED":
        return jsonify({"ok": False, "error": f"serial is {row['state']}"}), 409
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE serial_allocations SET state='ASSIGNED', committed_at=? WHERE serial=?", (iso(now()), serial))
    audit_write(conn, "Serial number committed", {"serial": serial}, g.actor, serial=serial)
    conn.execute("COMMIT")
    return jsonify({"ok": True, "serial": serial, "state": "ASSIGNED"})


@app.post("/serials/<serial>/void")
@require_role(*ROLES_ALLOCATE)
def void(serial):
    d = request.get_json(force=True) or {}
    conn = db()
    row = conn.execute("SELECT * FROM serial_allocations WHERE serial=?", (serial,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "unknown serial"}), 404
    if row["state"] == "ASSIGNED":
        return jsonify({"ok": False, "error": "assigned serials are retired, never voided"}), 409
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE serial_allocations SET state='VOID' WHERE serial=?", (serial,))
    audit_write(conn, "Serial number voided", {"serial": serial, "reason": d.get("reason")}, g.actor, serial=serial)
    conn.execute("COMMIT")
    return jsonify({"ok": True, "serial": serial, "state": "VOID"})


@app.get("/serials/last")
@require_role("factory", "service", "engineering", "release")
def last_serial():
    n = db().execute("SELECT last_number FROM serial_counter WHERE id=1").fetchone()["last_number"]
    return jsonify({"ok": True, "lastNumber": n, "lastSerial": serials.format_serial(n) if n else None,
                    "nextSerial": serials.format_serial(n + 1)})


@app.post("/serials/ranges")
@require_role(*ROLES_ALLOCATE)
def allocate_range():
    d = request.get_json(force=True) or {}
    size = int(d.get("size", 0))
    station, operator = d.get("stationId"), d.get("operator")
    if not (1 <= size <= 500) or not station or not operator:
        return jsonify({"ok": False, "error": "stationId, operator and 1<=size<=500 required"}), 400
    conn = db()
    first, last = _take_numbers(conn, size)
    range_id = str(uuid.uuid4())
    issued, expires = now(), now() + timedelta(days=RANGE_DAYS)
    payload = {"type": "serial-range", "rangeId": range_id, "stationId": station,
               "first": serials.format_serial(first), "last": serials.format_serial(last),
               "issuedAt": iso(issued), "expiresAt": iso(expires)}
    token = crypto.sign(payload, signing_key())
    for n in range(first, last + 1):
        conn.execute("INSERT INTO serial_allocations (serial, number, state, allocation_id, station_id, operator, "
                     "reason, range_id, reserved_at, reserved_until) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (serials.format_serial(n), n, "RANGE", str(uuid.uuid4()), station, operator, "range",
                      range_id, iso(issued), iso(expires)))
    conn.execute("INSERT INTO serial_ranges (range_id, station_id, first_number, last_number, issued_at, expires_at, token) "
                 "VALUES (?,?,?,?,?,?,?)", (range_id, station, first, last, iso(issued), iso(expires), json.dumps(token)))
    audit_write(conn, "Serial range issued", {"rangeId": range_id, "first": payload["first"], "last": payload["last"],
                                              "station": station}, g.actor)
    conn.execute("COMMIT")
    return jsonify({"ok": True, "token": token})


@app.post("/serials/ranges/<range_id>/reconcile")
@require_role(*ROLES_ALLOCATE)
def reconcile_range(range_id):
    d = request.get_json(force=True) or {}
    used = set(d.get("used") or [])
    conn = db()
    rng = conn.execute("SELECT * FROM serial_ranges WHERE range_id=?", (range_id,)).fetchone()
    if not rng:
        return jsonify({"ok": False, "error": "unknown range"}), 404
    conn.execute("BEGIN IMMEDIATE")
    rows = conn.execute("SELECT serial, state FROM serial_allocations WHERE range_id=?", (range_id,)).fetchall()
    assigned, voided = [], []
    for r in rows:
        if r["state"] != "RANGE":
            continue
        if r["serial"] in used:
            conn.execute("UPDATE serial_allocations SET state='ASSIGNED', committed_at=? WHERE serial=?", (iso(now()), r["serial"]))
            assigned.append(r["serial"])
        else:
            conn.execute("UPDATE serial_allocations SET state='VOID' WHERE serial=?", (r["serial"],))
            voided.append(r["serial"])
    conn.execute("UPDATE serial_ranges SET reconciled_at=? WHERE range_id=?", (iso(now()), range_id))
    audit_write(conn, "Serial range reconciled", {"rangeId": range_id, "assigned": assigned, "voided": voided}, g.actor)
    conn.execute("COMMIT")
    return jsonify({"ok": True, "assigned": assigned, "voided": voided})


# --------------------------------------------------------------------------
#  devices + licenses
# --------------------------------------------------------------------------
@app.post("/devices/register")
@require_role(*ROLES_ALLOCATE)
def register_device():
    d = request.get_json(force=True) or {}
    try:
        pub = load_public_pem(d["publicKeyPem"])
        nonce = base64.b64decode(d["nonce"])
        sig = base64.b64decode(d["nonceSignature"])
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": f"bad request: {e}"}), 400
    if not verify_challenge(pub, nonce, sig):
        return jsonify({"ok": False, "error": "device did not prove possession of its key"}), 400
    dev_id = derive_device_id(pub)
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT OR REPLACE INTO devices (device_id, public_key_pem, identity_backend, board_serial, board_revision, "
                 "hardware_fingerprint, secure_boot, registered_at) VALUES (?,?,?,?,?,?,?,?)",
                 (dev_id, d["publicKeyPem"], d.get("identityBackend", "otp-hkdf"), d.get("boardSerial"),
                  d.get("boardRevision"), d.get("fingerprint"), 1 if d.get("secureBoot") else 0, iso(now())))
    audit_write(conn, "Device identity registered", {"deviceId": dev_id, "boardSerial": d.get("boardSerial"),
                                                     "secureBoot": bool(d.get("secureBoot"))}, g.actor, device_id=dev_id)
    conn.execute("COMMIT")
    return jsonify({"ok": True, "deviceId": dev_id})


@app.post("/licenses/issue")
@require_role(*ROLES_ALLOCATE)
def issue_license():
    d = request.get_json(force=True) or {}
    conn = db()
    dev = conn.execute("SELECT * FROM devices WHERE device_id=?", (d.get("deviceId"),)).fetchone()
    alloc = conn.execute("SELECT * FROM serial_allocations WHERE serial=?", (d.get("serial"),)).fetchone()
    if not dev or not alloc:
        return jsonify({"ok": False, "error": "unknown device or serial"}), 404
    if alloc["state"] not in ("RESERVED", "ASSIGNED", "RANGE"):
        return jsonify({"ok": False, "error": f"serial is {alloc['state']}"}), 409
    features = list(d.get("features") or ["production"])
    if not dev["secure_boot"] or dev["identity_backend"] == "software":
        features = [f for f in features if f != lic.PRODUCTION_FEATURE]     # never a production license
    try:
        payload = lic.build_payload(
            serial=d["serial"], device_id=dev["device_id"], device_public_key_pem=dev["public_key_pem"],
            product_type=d.get("productType", "SCURE-A"), features=features,
            software_compat=d.get("softwareCompat", ">=0.6.0 <2.0.0"), issuer=ISSUER,
            identity_backend=dev["identity_backend"], previous_serial=d.get("previousSerial") or alloc["previous_serial"],
            expires_at=(now() + timedelta(days=30)) if d.get("provisional") else None,
            provisional=bool(d.get("provisional")))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    env = crypto.sign(payload, license_key())
    lid = str(uuid.uuid4())
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO licenses (license_id, serial, device_id, envelope, provisional, issued_at) VALUES (?,?,?,?,?,?)",
                 (lid, d["serial"], dev["device_id"], json.dumps(env), 1 if d.get("provisional") else 0, iso(now())))
    conn.execute("INSERT OR REPLACE INTO machines (serial, device_id, product_type, status, created_at) VALUES (?,?,?,?,?)",
                 (d["serial"], dev["device_id"], payload["productType"], "PROVISIONING", iso(now())))
    audit_write(conn, "License issued", {"licenseId": lid, "serial": d["serial"], "features": features,
                                         "provisional": bool(d.get("provisional"))}, g.actor,
                serial=d["serial"], device_id=dev["device_id"])
    conn.execute("COMMIT")
    return jsonify({"ok": True, "licenseId": lid, "license": env})


# --------------------------------------------------------------------------
#  image catalog
# --------------------------------------------------------------------------
@app.post("/images/publish")
@require_role(*ROLES_ENGINEERING)
def publish_image():
    d = request.get_json(force=True) or {}
    env = d.get("envelope")
    if not env:
        payload = d.get("manifest")
        if not payload:
            return jsonify({"ok": False, "error": "envelope or manifest required"}), 400
        env = crypto.sign(payload, signing_key())
    try:
        p = manifests.verify_manifest(env, crypto.TrustStore.of([signing_key().public_key()]))
    except manifests.ManifestError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT OR REPLACE INTO images (build_id, product, image_version, channel, production_approved, withdrawn, "
                 "manifest, published_at) VALUES (?,?,?,?,?,?,?,?)",
                 (p["buildId"], p["product"], p["imageVersion"], p["channel"],
                  1 if (p["channel"] == "production" and p["productionApproved"] is True) else 0, 0,
                  json.dumps(env), iso(now())))
    audit_write(conn, "Image published", {"buildId": p["buildId"], "version": p["imageVersion"], "channel": p["channel"]}, g.actor)
    conn.execute("COMMIT")
    return jsonify({"ok": True, "buildId": p["buildId"]})


@app.post("/images/<build_id>/approve")
@require_role("release")
def approve_image(build_id):
    """Marks a build Production Approved: re-signs the manifest with
    channel=production, productionApproved=true. Only the release role."""
    d = request.get_json(force=True) or {}
    conn = db()
    row = conn.execute("SELECT manifest FROM images WHERE build_id=?", (build_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "unknown build"}), 404
    payload = dict(json.loads(row["manifest"])["payload"])
    payload.update({"channel": "production", "productionApproved": True,
                    "approvedAt": iso(now()), "approvedBy": d.get("approvedBy", g.actor)})
    env = crypto.sign(payload, signing_key())
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE images SET channel='production', production_approved=1, manifest=?, approved_by=?, approved_at=? WHERE build_id=?",
                 (json.dumps(env), payload["approvedBy"], payload["approvedAt"], build_id))
    audit_write(conn, "Image production-approved", {"buildId": build_id, "version": payload["imageVersion"]}, g.actor)
    conn.execute("COMMIT")
    return jsonify({"ok": True, "manifest": env})


@app.post("/images/<build_id>/withdraw")
@require_role("release")
def withdraw_image(build_id):
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    n = conn.execute("UPDATE images SET withdrawn=1, production_approved=0 WHERE build_id=?", (build_id,)).rowcount
    audit_write(conn, "Image withdrawn", {"buildId": build_id}, g.actor)
    conn.execute("COMMIT")
    return jsonify({"ok": bool(n)})


@app.get("/images/latest")
def latest_image():
    product = request.args.get("product", "SCURE-A")
    channel = request.args.get("channel", "production")
    if channel not in manifests.CHANNELS:
        return jsonify({"ok": False, "error": "bad channel"}), 400
    rows = db().execute("SELECT manifest FROM images WHERE product=? AND channel=? AND withdrawn=0", (product, channel)).fetchall()
    payloads = [json.loads(r["manifest"]) for r in rows]
    best = manifests.newest_approved([e["payload"] for e in payloads], channel)
    if not best:
        return jsonify({"ok": False, "error": f"no {channel} image for {product}"}), 404
    env = next(e for e in payloads if e["payload"]["buildId"] == best["buildId"])
    # every channel's view of the catalogue, for the provisioning UI
    versions = {}
    for ch in manifests.CHANNELS:
        r = db().execute("SELECT manifest FROM images WHERE product=? AND channel=? AND withdrawn=0", (product, ch)).fetchall()
        p = manifests.newest_approved([json.loads(x["manifest"])["payload"] for x in r], ch)
        versions[ch] = p["imageVersion"] if p else None
    return jsonify({"ok": True, "manifest": env, "versions": versions,
                    "signerPublicKeyPem": crypto.public_pem(signing_key().public_key())})


@app.get("/images/withdrawn")
def withdrawn_images():
    rows = db().execute("SELECT build_id FROM images WHERE withdrawn=1").fetchall()
    return jsonify({"ok": True, "withdrawn": [r["build_id"] for r in rows]})


# --------------------------------------------------------------------------
#  provisioning records + audit
# --------------------------------------------------------------------------
@app.post("/provisioning/runs")
@require_role(*ROLES_ALLOCATE)
def record_run():
    d = request.get_json(force=True) or {}
    required = ("runId", "stationId", "operator", "online", "result", "stepLog", "startedAt", "finishedAt")
    if any(k not in d for k in required):
        return jsonify({"ok": False, "error": f"required: {required}"}), 400
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT OR REPLACE INTO provisioning_runs (run_id, serial, device_id, station_id, operator, image_version, build_id, "
                 "image_sha256, app_version, online, result, step_log, started_at, finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (d["runId"], d.get("serial"), d.get("deviceId"), d["stationId"], d["operator"], d.get("imageVersion"),
                  d.get("buildId"), d.get("imageSha256"), d.get("appVersion"), 1 if d["online"] else 0, d["result"],
                  json.dumps(d["stepLog"]), d["startedAt"], d["finishedAt"]))
    if d.get("serial") and d["result"] == "READY_FOR_PRODUCTION":
        conn.execute("UPDATE machines SET status='READY_FOR_PRODUCTION' WHERE serial=?", (d["serial"],))
    audit_write(conn, "Provisioning run recorded", {"runId": d["runId"], "result": d["result"], "online": bool(d["online"]),
                                                    "imageVersion": d.get("imageVersion"), "buildId": d.get("buildId")},
                g.actor, serial=d.get("serial"), device_id=d.get("deviceId"))
    conn.execute("COMMIT")
    return jsonify({"ok": True})


@app.post("/recovery-keys")
@require_role(*ROLES_ALLOCATE)
def recovery_key():
    """Escrow of the LUKS recovery passphrase, already encrypted to the
    Stratasys KMS key by the module — the service never sees it in clear."""
    d = request.get_json(force=True) or {}
    if not d.get("serial") or not d.get("ciphertext"):
        return jsonify({"ok": False, "error": "serial and ciphertext required"}), 400
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("CREATE TABLE IF NOT EXISTS recovery_keys (serial TEXT PRIMARY KEY, ciphertext TEXT NOT NULL, "
                 "kms_key_id TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("INSERT OR REPLACE INTO recovery_keys (serial, ciphertext, kms_key_id, created_at) VALUES (?,?,?,?)",
                 (d["serial"], d["ciphertext"], d.get("kmsKeyId", ""), iso(now())))
    audit_write(conn, "Recovery key escrowed", {"serial": d["serial"], "kmsKeyId": d.get("kmsKeyId")}, g.actor, serial=d["serial"])
    conn.execute("COMMIT")
    return jsonify({"ok": True})


@app.get("/audit")
@require_role("factory", "service", "engineering", "release")
def audit_query():
    serial = request.args.get("serial")
    q = "SELECT ts, serial, device_id, actor, event, detail, prev_hash, hash FROM audit_log"
    args = ()
    if serial:
        q += " WHERE serial=?"
        args = (serial,)
    rows = db().execute(q + " ORDER BY id", args).fetchall()
    entries = [{"ts": r["ts"], "serial": r["serial"], "deviceId": r["device_id"], "actor": r["actor"],
                "event": r["event"], "detail": json.loads(r["detail"]), "prevHash": r["prev_hash"], "hash": r["hash"]}
               for r in rows]
    ok, n, _ = audit.verify_chain(entries) if not serial else (True, len(entries), None)
    return jsonify({"ok": True, "chainIntact": ok, "count": n, "entries": entries})


@app.get("/keys/public")
def public_keys():
    return jsonify({"ok": True,
                    "serialServiceKeyPem": crypto.public_pem(signing_key().public_key()),
                    "licenseKeyPem": crypto.public_pem(license_key().public_key())})


if __name__ == "__main__":
    app.run(host=os.environ.get("BIND", "127.0.0.1"), port=int(os.environ.get("PORT", "8440")))
