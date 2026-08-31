"""Google Drive synchronisation (SRS-DVT-110…112).

Two backends, chosen by configuration:

  * `api`    — Google Drive API v3 with the engineer's own Google account
               (OAuth "installed app"). Needs `credentials.json` from Google
               Cloud Console (Drive API enabled, OAuth client type Desktop).
               The first sync opens the browser once; the token is cached in
               `token.json` next to it. Files are uploaded into a folder
               "<campaign>" (created if missing) — the latest version of each
               export overwrites the previous one, so the Drive folder always
               mirrors the campaign.
  * `folder` — copy into a folder that Google Drive for Desktop / OneDrive
               already synchronises (e.g. G:\\My Drive\\sCure DVT).

Sync never blocks the operator: `Syncer.sync()` is called after every saved
result from a background thread; failures are recorded in the store's
sync_queue and retried on the next call.
"""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .store import Store

SCOPES = ["https://www.googleapis.com/auth/drive.file"]      # only files this app created
MIME = {".json": "application/json", ".csv": "text/csv", ".md": "text/markdown",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf", ".txt": "text/plain"}


@dataclass
class SyncConfig:
    mode: str = "api"                    # api | folder | off
    campaign: str = "sCure-DVT"
    credentials_file: Path = Path("credentials.json")
    token_file: Path = Path("token.json")
    folder_path: Path | None = None      # for mode=folder
    drive_folder_id: str | None = None   # optional: upload into an existing Drive folder

    @classmethod
    def load(cls, path: Path) -> "SyncConfig":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(mode=d.get("mode", "api"), campaign=d.get("campaign", "sCure-DVT"),
                   credentials_file=Path(d.get("credentials_file", "credentials.json")),
                   token_file=Path(d.get("token_file", "token.json")),
                   folder_path=Path(d["folder_path"]) if d.get("folder_path") else None,
                   drive_folder_id=d.get("drive_folder_id"))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"mode": self.mode, "campaign": self.campaign,
                                    "credentials_file": str(self.credentials_file), "token_file": str(self.token_file),
                                    "folder_path": str(self.folder_path) if self.folder_path else None,
                                    "drive_folder_id": self.drive_folder_id}, indent=2), encoding="utf-8")


@dataclass
class SyncStatus:
    mode: str
    ok: bool
    last_sync: str | None = None
    last_error: str | None = None
    pending: int = 0
    account: str | None = None
    target: str | None = None
    uploaded: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
#  backends
# --------------------------------------------------------------------------
class FolderBackend:
    def __init__(self, folder: Path):
        self.folder = folder

    def describe(self) -> str:
        return f"folder {self.folder}"

    def push(self, files: list[Path], root: Path) -> list[str]:
        out = []
        for f in files:
            rel = f.relative_to(root)
            dst = self.folder / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            out.append(str(rel))
        return out


class DriveApiBackend:
    def __init__(self, cfg: SyncConfig):
        self.cfg = cfg
        self._svc = None
        self._folder_ids: dict[str, str] = {}
        self.account: str | None = None

    def describe(self) -> str:
        return f"Google Drive ({self.account or 'not signed in'}) / {self.cfg.campaign}"

    def _service(self):
        if self._svc is not None:
            return self._svc
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        creds = None
        if self.cfg.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.cfg.token_file), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.cfg.credentials_file.exists():
                    raise RuntimeError(f"Google OAuth client file not found: {self.cfg.credentials_file} "
                                       "(Google Cloud Console → APIs → Credentials → OAuth client ID, Desktop app)")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.cfg.credentials_file), SCOPES)
                creds = flow.run_local_server(port=0)        # opens the browser once
            self.cfg.token_file.write_text(creds.to_json(), encoding="utf-8")
        self._svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        try:
            about = self._svc.about().get(fields="user(emailAddress)").execute()
            self.account = about.get("user", {}).get("emailAddress")
        except Exception:  # noqa: BLE001 - informational only
            pass
        return self._svc

    def _folder(self, name: str, parent: str | None) -> str:
        key = f"{parent}/{name}"
        if key in self._folder_ids:
            return self._folder_ids[key]
        svc = self._service()
        q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        q += f" and '{parent}' in parents" if parent else " and 'root' in parents"
        res = svc.files().list(q=q, fields="files(id)", spaces="drive").execute().get("files", [])
        if res:
            fid = res[0]["id"]
        else:
            meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
            if parent:
                meta["parents"] = [parent]
            fid = svc.files().create(body=meta, fields="id").execute()["id"]
        self._folder_ids[key] = fid
        return fid

    def push(self, files: list[Path], root: Path) -> list[str]:
        from googleapiclient.http import MediaFileUpload
        svc = self._service()
        base = self.cfg.drive_folder_id or self._folder(self.cfg.campaign, None)
        out = []
        for f in files:
            rel = f.relative_to(root)
            parent = base
            for part in rel.parts[:-1]:
                parent = self._folder(part, parent)
            q = f"name = '{f.name}' and '{parent}' in parents and trashed = false"
            existing = svc.files().list(q=q, fields="files(id)", spaces="drive").execute().get("files", [])
            media = MediaFileUpload(str(f), mimetype=MIME.get(f.suffix.lower(), "application/octet-stream"), resumable=False)
            if existing:
                svc.files().update(fileId=existing[0]["id"], media_body=media).execute()
            else:
                svc.files().create(body={"name": f.name, "parents": [parent]}, media_body=media, fields="id").execute()
            out.append(str(rel))
        return out


# --------------------------------------------------------------------------
#  syncer
# --------------------------------------------------------------------------
class Syncer:
    def __init__(self, cfg: SyncConfig, store: Store, export_root: Path, backend=None):
        self.cfg, self.store, self.root = cfg, store, export_root
        self.backend = backend or self._make_backend()
        self.status = SyncStatus(mode=cfg.mode, ok=cfg.mode == "off", target=self.backend.describe() if self.backend else None)
        self._lock = threading.Lock()

    def _make_backend(self):
        if self.cfg.mode == "folder":
            if not self.cfg.folder_path:
                raise RuntimeError("folder sync selected but no folder_path configured")
            return FolderBackend(self.cfg.folder_path)
        if self.cfg.mode == "api":
            return DriveApiBackend(self.cfg)
        return None

    def sync(self, files: list[Path]) -> SyncStatus:
        """Push the given exported files; drain the store's sync queue on success."""
        with self._lock:
            pending = self.store.pending_sync()
            self.status.pending = len(pending)
            if self.backend is None:
                return self.status
            try:
                uploaded = self.backend.push(files, self.root)
                self.store.mark_synced([p["id"] for p in pending])
                self.status = SyncStatus(self.cfg.mode, True, datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                                         None, 0, getattr(self.backend, "account", None), self.backend.describe(), uploaded)
            except Exception as e:  # noqa: BLE001 - never lose a run over a sync error
                self.store.mark_sync_failed([p["id"] for p in pending], f"{type(e).__name__}: {e}")
                self.status.ok = False
                self.status.last_error = f"{type(e).__name__}: {e}"
                self.status.pending = len(pending)
            return self.status
