"""Approved-image catalog client with local cache and offline mode
(ARCHITECTURE.md §4.5).

    cat = ImageCatalog(server_url, trust, cache_dir, product="SCURE-A")
    res = cat.resolve(detected_hw)        # -> Resolution
    path = cat.ensure_downloaded(res, progress=cb)   # verified file path

Rules enforced here, independent of the UI:
  * only a manifest that verifies against the trusted image-signing keys
  * only channel == production AND productionApproved == true (factory role)
  * hash + size re-checked on the cached file before EVERY use
  * offline: newest cached approved manifest, flagged offline=True
  * withdrawn builds refused once the tool has heard of them
"""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from stratasys_appliance import crypto, manifests

WITHDRAWN_FILE = "withdrawn.json"


@dataclass
class Resolution:
    envelope: dict
    payload: dict
    online: bool
    local_version: str | None            # newest cached approved version before this resolve
    server_versions: dict = field(default_factory=dict)   # per-channel newest, for the UI
    status: str = ""

    @property
    def version(self) -> str:
        return self.payload["imageVersion"]

    @property
    def build_id(self) -> str:
        return self.payload["buildId"]


class CatalogError(Exception):
    pass


class ImageCatalog:
    def __init__(self, server_url: str | None, trust: crypto.TrustStore, cache_dir: str | Path,
                 product: str = "SCURE-A", channel: str = "production", timeout: float = 10.0,
                 opener: Callable = urllib.request.urlopen):
        self.server_url = (server_url or "").rstrip("/") or None
        self.trust = trust
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.product = product
        self.channel = channel
        self.timeout = timeout
        self._open = opener

    # ---------------- cache ----------------
    def _dir(self, build_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in build_id)
        return self.cache / safe

    def cached_manifests(self) -> list[dict]:
        out = []
        for mf in self.cache.glob("*/manifest.json"):
            try:
                env = json.loads(mf.read_text())
                p = manifests.verify_manifest(env, self.trust)
            except (OSError, ValueError, manifests.ManifestError):
                continue
            if p["product"] == self.product:
                out.append(env)
        return out

    def withdrawn(self) -> set[str]:
        f = self.cache / WITHDRAWN_FILE
        try:
            return set(json.loads(f.read_text()))
        except (OSError, ValueError):
            return set()

    def _remember_withdrawn(self, ids) -> None:
        (self.cache / WITHDRAWN_FILE).write_text(json.dumps(sorted(set(ids) | self.withdrawn())))

    def newest_cached(self) -> dict | None:
        envs = [e for e in self.cached_manifests() if e["payload"]["buildId"] not in self.withdrawn()]
        best = manifests.newest_approved([e["payload"] for e in envs], self.channel)
        return next((e for e in envs if e["payload"]["buildId"] == best["buildId"]), None) if best else None

    # ---------------- server ----------------
    def _get_json(self, path: str) -> dict:
        try:
            with self._open(f"{self.server_url}{path}", timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:          # reachable server, negative answer (e.g. 404 no image)
            try:
                return json.loads(e.read().decode())
            except ValueError:
                return {"ok": False, "error": f"HTTP {e.code}"}

    def resolve(self, hw: manifests.DetectedHardware | None) -> Resolution:
        local = self.newest_cached()
        local_version = local["payload"]["imageVersion"] if local else None
        env, online, versions = None, False, {}
        if self.server_url:
            try:
                data = self._get_json(f"/images/latest?product={self.product}&channel={self.channel}")
                if data.get("ok"):
                    env, versions, online = data["manifest"], data.get("versions", {}), True
                    try:
                        w = self._get_json("/images/withdrawn")
                        if w.get("ok"):
                            self._remember_withdrawn(w["withdrawn"])
                    except (urllib.error.URLError, OSError, ValueError):
                        pass
                else:
                    online = True     # server reachable, but nothing approved for this product
            except (urllib.error.URLError, OSError, ValueError, TimeoutError):
                online = False
        if env is None:
            if local is None:
                raise CatalogError("no approved image available: server unreachable and cache empty"
                                   if not online else f"server has no {self.channel} image for {self.product}")
            env = local
        payload = manifests.verify_manifest(env, self.trust)
        manifests.check_installable(payload, hw, self.withdrawn(), self.channel)
        status = (f"Latest Production Version: {payload['imageVersion']}" if online else
                  f"OFFLINE MODE — Unable to verify whether a newer Production Image is available. "
                  f"Using cached approved image: {payload['imageVersion']}")
        return Resolution(env, payload, online, local_version, versions, status)

    def ensure_downloaded(self, res: Resolution, progress: Callable[[int, int], None] | None = None) -> Path:
        d = self._dir(res.build_id)
        d.mkdir(parents=True, exist_ok=True)
        img = d / "image.img.zst"
        (d / "manifest.json").write_text(json.dumps(res.envelope, indent=2))
        if img.exists():
            try:
                manifests.check_file(res.payload, img)
                return img
            except manifests.ManifestError:
                img.unlink()             # corrupted cache: never trusted, re-download
        if not res.online and not img.exists():
            raise CatalogError(f"cached image file for {res.version} is missing/corrupt and the station is offline")
        tmp = d / "image.img.zst.part"
        url = res.payload["url"]
        if url.startswith("/"):
            url = f"{self.server_url}{url}"
        with self._open(url, timeout=self.timeout) as r, tmp.open("wb") as f:
            total = int(res.payload["sizeBytes"])
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        manifests.check_file(res.payload, tmp)      # raises HASH/SIZE on tampering
        shutil.move(tmp, img)
        return img

    def verify_before_flash(self, res: Resolution, path: Path) -> None:
        """Re-verify signature (manifest) + hash (file) right before writing
        to the target — the cache is never trusted from memory."""
        manifests.verify_manifest(res.envelope, self.trust)
        manifests.check_file(res.payload, path)
