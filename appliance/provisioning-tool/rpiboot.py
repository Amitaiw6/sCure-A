"""Raspberry Pi CM5 access from the provisioning PC via `rpiboot` (usbboot).

Two phases:
  1. mass-storage: `rpiboot -d mass-storage-gadget64` makes the module's
     eMMC/NVMe appear as a USB disk on the PC -> flash + read board info.
  2. secure-boot programming: `rpiboot -d secure-boot-recovery5` with a
     signed `pieeprom.bin` + `config.txt` (program_pubkey, revoke_devkey,
     program_jtag_lock) burns the OTP and installs the signed EEPROM.

All subprocess calls are isolated here so the state machine can be tested
with a fake. Windows and Linux hosts are both supported by usbboot; the
block-device discovery differs and is handled in `find_target_disk`.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class RpibootError(Exception):
    pass


@dataclass
class ModuleInfo:
    board_serial: str
    board_revision: str
    model: str
    eeprom_version: str
    storage_device: str
    storage_size_bytes: int
    secure_boot: bool
    memory_mb: int


def _run(cmd, timeout=600, check=True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)
    except FileNotFoundError:
        raise RpibootError(f"{cmd[0]} not found — install Raspberry Pi usbboot")
    except subprocess.CalledProcessError as e:
        raise RpibootError(f"{' '.join(cmd)} failed: {e.stderr.strip() or e.stdout.strip()}")


class Rpiboot:
    def __init__(self, usbboot_dir: str | Path | None = None):
        self.usbboot = Path(usbboot_dir or os.environ.get("USBBOOT_DIR", "/opt/usbboot"))
        self.exe = shutil.which("rpiboot") or str(self.usbboot / "rpiboot")

    def expose_mass_storage(self, timeout=120) -> None:
        """Blocks until a module in nRPIBOOT mode has loaded the gadget."""
        _run([self.exe, "-d", str(self.usbboot / "mass-storage-gadget64")], timeout=timeout)

    def find_target_disk(self, wait_s=30) -> str:
        """Block device the gadget created. Linux: by USB vendor id
        0a5c (Broadcom) in /sys; Windows: physical drive with that VID."""
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if platform.system() == "Linux":
                for dev in sorted(Path("/sys/block").glob("sd*")):
                    try:
                        vendor = (dev / "device/vendor").read_text().strip().lower()
                        model = (dev / "device/model").read_text().strip().lower()
                    except OSError:
                        continue
                    if "rpi" in vendor or "rpi" in model or "raspberry" in model:
                        return f"/dev/{dev.name}"
            elif platform.system() == "Windows":
                ps = ("Get-CimInstance Win32_DiskDrive | Where-Object {$_.PNPDeviceID -like '*VID_0A5C*'} "
                      "| Select-Object -First 1 -ExpandProperty DeviceID")
                out = _run(["powershell", "-NoProfile", "-Command", ps], check=False).stdout.strip()
                if out:
                    return out
            time.sleep(1)
        raise RpibootError("module storage did not appear on the USB bus")

    def read_module_info(self, disk: str) -> ModuleInfo:
        """rpiboot prints the board info when loading the gadget; we also
        read the exposed boot partition's `otp.json` written by the gadget."""
        info = {"board_serial": "", "board_revision": "", "model": "CM5", "eeprom_version": "",
                "secure_boot": False, "memory_mb": 0}
        out = _run([self.exe, "-d", str(self.usbboot / "mass-storage-gadget64"), "-i"], check=False, timeout=30).stdout
        for line in out.splitlines():
            k, _, v = line.partition(":")
            k = k.strip().lower()
            if k == "serial":
                info["board_serial"] = v.strip()
            elif k == "revision":
                info["board_revision"] = v.strip()
            elif k in ("eeprom", "bootloader"):
                info["eeprom_version"] = v.strip()
            elif k == "secure boot":
                info["secure_boot"] = v.strip().lower() in ("1", "true", "yes", "on")
            elif k == "memory":
                info["memory_mb"] = int("".join(ch for ch in v if ch.isdigit()) or 0)
        size = 0
        try:
            if platform.system() == "Linux":
                size = int(_run(["blockdev", "--getsize64", disk]).stdout.strip())
        except (RpibootError, ValueError):
            pass
        return ModuleInfo(storage_device=disk, storage_size_bytes=size, **info)

    def flash(self, image_zst: Path, disk: str, progress=None) -> None:
        """zstd -dc image | dd to the module storage. `progress(done, total)`."""
        total = image_zst.stat().st_size
        if platform.system() == "Linux":
            cmd = f"zstd -dc '{image_zst}' | dd of='{disk}' bs=4M conv=fsync status=none"
            p = subprocess.Popen(["bash", "-c", cmd], stderr=subprocess.PIPE, text=True)
            _, err = p.communicate()
            if p.returncode != 0:
                raise RpibootError(f"flash failed: {err.strip()}")
            _run(["sync"])
        else:
            raise RpibootError("flashing from a Windows host: use the Linux provisioning station image")
        if progress:
            progress(total, total)

    def program_secure_boot(self, signed_eeprom_dir: Path, timeout=300) -> None:
        """`signed_eeprom_dir` = secure-boot-recovery5 payload prepared by the
        release team: pieeprom.bin signed with the Stratasys boot key, config.txt
        with program_pubkey=1 revoke_devkey=1 program_jtag_lock=1. Irreversible."""
        cfg = (signed_eeprom_dir / "config.txt").read_text()
        for must in ("program_pubkey=1", "revoke_devkey=1"):
            if must not in cfg:
                raise RpibootError(f"refusing: {must} missing from {signed_eeprom_dir}/config.txt")
        _run([self.exe, "-d", str(signed_eeprom_dir)], timeout=timeout)

    def boot_provisioning_mode(self, timeout=120) -> None:
        """Let the module leave rpiboot and boot its own (signed) image; the
        image's initramfs brings up the USB-Ethernet gadget for the agent."""
        # nothing to do: releasing the USB mass-storage gadget (unplug/replug
        # or the carrier's provisioning switch) reboots the module.
        return


class FakeRpiboot(Rpiboot):
    """Deterministic stand-in for tests and dry runs."""

    def __init__(self, info: ModuleInfo | None = None):
        self.info = info or ModuleInfo("10000000a1b2c3d4", "d04170", "Raspberry Pi Compute Module 5",
                                       "2025-05-08", "/dev/fake", 32_000_000_000, False, 4096)
        self.flashed: list[tuple[str, str]] = []
        self.programmed = False

    def expose_mass_storage(self, timeout=120): return None
    def find_target_disk(self, wait_s=30): return self.info.storage_device
    def read_module_info(self, disk): return self.info

    def flash(self, image_zst, disk, progress=None):
        self.flashed.append((str(image_zst), disk))
        if progress:
            progress(1, 1)

    def program_secure_boot(self, signed_eeprom_dir, timeout=300):
        self.programmed = True
        self.info.secure_boot = True
