"""Campaign checkpoints in Git — a reviewed snapshot of the results in the repo.

The live campaign is shared through the Drive folder (journal.py); Git keeps
the controlled history: at a phase gate (automatically, when the TRR is
signed) or on demand ("Save checkpoint to Git…"), the console exports the
campaign and commits a snapshot under

    <repo>/DVT/checkpoints/<campaign>/<YYYYMMDD-HHMM>_<label>/
        <campaign>.campaign.json     every run, value, verdict, NCR, waiver, event
        <campaign>.xlsx              the workbook
        <campaign>.report.md         the Markdown report
        temperature_by_component.csv (when present)
        CHECKPOINT.md                who, when, why, progress per machine

and pushes when a remote is configured. Only those paths are committed — other
staged or modified files in the working tree are left alone.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CHECKPOINT_DIRNAME = "checkpoints"
KEEP = (".campaign.json", ".xlsx", ".report.md")          # snapshot files (the PDF / charts stay in the export folder)
KEEP_NAMES = ("temperature_by_component.csv",)


@dataclass
class CheckpointResult:
    ok: bool = False
    folder: Path | None = None
    commit: str | None = None
    pushed: bool = False
    message: str = ""
    error: str | None = None
    files: list[str] = field(default_factory=list)


def _git(args: list[str], cwd: Path, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)   # git talks UTF-8, not the console code page


def git_available() -> bool:
    return shutil.which("git") is not None


def repo_root(start: Path) -> Path | None:
    if not git_available():
        return None
    r = _git(["rev-parse", "--show-toplevel"], Path(start))
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def safe_label(label: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", (label or "").strip()).strip("-")
    return s[:48] or "checkpoint"


def folder_name(label: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return f"{when.strftime('%Y%m%d-%H%M')}_{safe_label(label)}"


def commit_message(label: str, progress: dict, campaign: str, operator: str = "") -> str:
    done, total = progress.get("done", 0), progress.get("total", 0)
    pct = round(100 * done / total) if total else 0
    return (f"DVT checkpoint: {label} — {done}/{total} runs ({pct} %), {progress.get('PASS', 0)} PASS / {progress.get('FAIL', 0)} FAIL"
            f" / {progress.get('BLOCKED', 0)} BLOCKED / {progress.get('WAIVED', 0)} WAIVED [{campaign}]" + (f" by {operator}" if operator else ""))


def checkpoint_markdown(label: str, operator: str, campaign: str, catalog_version: str, progress: dict, head: str | None, when: datetime) -> str:
    per = progress.get("perUnit") or {}
    rows = "\n".join(f"| {u} | {v['done']}/{v['total']} | {round(100 * v['done'] / v['total']) if v['total'] else 0} % | {v.get('phase', '—')} |" for u, v in per.items())
    return f"""# DVT checkpoint — {label}

| | |
|---|---|
| Campaign | {campaign} |
| When (UTC) | {when.strftime('%Y-%m-%d %H:%M')} |
| By | {operator or '—'} |
| Catalog | v{catalog_version} |
| Code (HEAD before this checkpoint) | {head or '—'} |
| Runs committed | {progress.get('done', 0)} / {progress.get('total', 0)} |
| Verdicts | {progress.get('PASS', 0)} PASS · {progress.get('FAIL', 0)} FAIL · {progress.get('BLOCKED', 0)} BLOCKED · {progress.get('WAIVED', 0)} WAIVED |
| Rejected runs | {progress.get('rejected', 0)} |
| Open NCRs | {progress.get('openNcrs', 0)} |

## Progress per machine

| Unit | Runs | % | Phase |
|---|---|---|---|
{rows}

Files in this folder are the exports of the moment: the campaign JSON (every
run, value, verdict, NCR, waiver and event), the workbook and the report.
"""


def make_checkpoint(exporter, engine, label: str, operator: str, campaign: str, catalog_version: str,
                    repo: Path | None = None, push: bool = True, when: datetime | None = None) -> CheckpointResult:
    """Export the campaign, copy the snapshot into the repo, commit (and push). Never raises."""
    res = CheckpointResult(); when = when or datetime.now(timezone.utc)
    try:
        repo = repo or repo_root(Path(__file__).resolve().parent)
        if repo is None:
            res.error = "not inside a Git repository (or git is not installed)"; return res
        files = exporter.export_all()
        progress = engine.progress()
        rel = Path("DVT") / CHECKPOINT_DIRNAME / safe_label(campaign) / folder_name(label, when)
        folder = repo / rel; folder.mkdir(parents=True, exist_ok=True); res.folder = folder
        for f in files:
            if f.name.endswith(KEEP) or f.name in KEEP_NAMES:
                shutil.copy2(f, folder / f.name); res.files.append(f.name)
        head = _git(["rev-parse", "--short", "HEAD"], repo).stdout.strip() or None
        (folder / "CHECKPOINT.md").write_text(checkpoint_markdown(label, operator, campaign, catalog_version, progress, head, when), encoding="utf-8")
        res.files.append("CHECKPOINT.md")
        res.message = commit_message(label, progress, campaign, operator)
        rel_s = rel.as_posix()
        r = _git(["add", "-A", "--", rel_s], repo)
        if r.returncode != 0:
            res.error = f"git add: {r.stderr.strip()}"; return res
        ident = []
        if not _git(["config", "user.name"], repo).stdout.strip():
            ident = ["-c", f"user.name={operator or 'sCure DVT console'}", "-c", f"user.email={safe_label(operator or 'dvt')}@scure-dvt"]
        r = _git([*ident, "commit", "-m", res.message, "--", rel_s], repo)
        if r.returncode != 0:
            res.error = f"git commit: {(r.stderr or r.stdout).strip()}"; return res
        res.commit = _git(["rev-parse", "--short", "HEAD"], repo).stdout.strip() or None
        res.ok = True
        if push:
            if _git(["remote"], repo).stdout.strip():
                r = _git(["push"], repo, timeout=120)
                res.pushed = r.returncode == 0
                if not res.pushed:
                    res.error = f"committed {res.commit}, push failed: {(r.stderr or r.stdout).strip()[:300]}"
            else:
                res.error = f"committed {res.commit}; no remote configured, nothing pushed"
        return res
    except Exception as e:  # noqa: BLE001 - a checkpoint must never take the console down
        res.error = f"{type(e).__name__}: {e}"; return res


def last_checkpoints(repo: Path, campaign: str, n: int = 5) -> list[dict]:
    """The latest checkpoint folders of a campaign (newest first)."""
    d = repo / "DVT" / CHECKPOINT_DIRNAME / safe_label(campaign)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir(), reverse=True)[:n]:
        if p.is_dir():
            out.append({"name": p.name, "path": str(p), "label": p.name.split("_", 1)[1] if "_" in p.name else p.name, "files": sorted(x.name for x in p.iterdir())})
    return out
