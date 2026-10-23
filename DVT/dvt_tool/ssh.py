"""SSH access to the machine under test — the DUT address doubles as the SSH host.

    host_of(url)                       "http://192.168.2.155:3001" -> "192.168.2.155"
    ssh_command(url, user, key)        the exact command line the operator would type
    test_ssh(url, user, key)           (ok, text) — BatchMode `hostname` over the key, no prompts
    open_terminal(url, user, key)      opens a Windows Terminal / console window with that ssh session

Defaults come from the campaign store (meta `ssh_user`, `ssh_key`) and fall back
to the test machine's known account (testingpi, key ~/.ssh/scure_pi).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

DEFAULT_USER = "testingpi"
DEFAULT_KEY = "~/.ssh/scure_pi"


def host_of(url: str | None) -> str | None:
    """Bare host / IP of a DUT address; None for the simulator or an empty address."""
    if not url or url.startswith("sim://"):
        return None
    u = url if "://" in url else f"http://{url}"
    return urlsplit(u).hostname


def ssh_command(url: str | None, user: str = DEFAULT_USER, key: str = DEFAULT_KEY) -> str | None:
    host = host_of(url)
    if not host:
        return None
    key = os.path.expanduser(key.strip()) if key and key.strip() else ""
    return f'ssh {"-i " + _q(key) + " " if key else ""}{user.strip() or DEFAULT_USER}@{host}'


def _q(p: str) -> str:
    return f'"{p}"' if " " in p else p


def test_ssh(url: str | None, user: str = DEFAULT_USER, key: str = DEFAULT_KEY, timeout: float = 6.0) -> tuple[bool, str]:
    host = host_of(url)
    if not host:
        return False, "no SSH host — the DUT is the simulator"
    if not shutil.which("ssh"):
        return False, "ssh client not found on this PC"
    args = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={int(timeout)}", "-o", "StrictHostKeyChecking=accept-new"]
    if key and key.strip():
        args += ["-i", os.path.expanduser(key.strip())]
    args += [f"{user.strip() or DEFAULT_USER}@{host}", "hostname; hostname -I; uptime -p"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 4)
    except subprocess.TimeoutExpired:
        return False, f"{host}: timed out"
    out = (r.stdout or "").strip(); err = "\n".join(l for l in (r.stderr or "").splitlines() if not l.startswith("**") and "Permanently added" not in l).strip()
    return (r.returncode == 0), (out if r.returncode == 0 else (err or out or f"ssh exit {r.returncode}"))


def open_terminal(url: str | None, user: str = DEFAULT_USER, key: str = DEFAULT_KEY) -> str | None:
    """Open an interactive SSH session in a new window. Returns the command used, or None."""
    cmd = ssh_command(url, user, key)
    if not cmd:
        return None
    if sys.platform.startswith("win"):
        wt = shutil.which("wt")
        if wt:
            subprocess.Popen([wt, "cmd", "/k", cmd])
        else:
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", cmd])
    else:
        term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("xterm")
        if not term:
            return None
        subprocess.Popen([term, "-e", cmd])
    return cmd
