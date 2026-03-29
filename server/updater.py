#!/usr/bin/env python3
"""
sCure Update Manager
Handles finding, verifying, and installing update packages from USB.

Called by app.py when user clicks "Update Software".
"""

import os
import json
import subprocess
import tarfile
import tempfile
import glob
import shutil
from pathlib import Path

PUBLIC_KEY = "/opt/scure/keys/scure-update.pub"
INSTALL_DIR = "/opt/scure"
USB_MOUNT_POINTS = ["/media/usb", "/media/pi", "/mnt/usb"]
USB_DEVICES = ["/dev/sda1", "/dev/sdb1"]


def find_usb_mount():
    """Find mounted USB drive or try to mount one."""
    # Check already-mounted paths
    for path in USB_MOUNT_POINTS:
        if os.path.ismount(path):
            return path

    # Try to mount
    mount_point = "/media/usb"
    os.makedirs(mount_point, exist_ok=True)
    for dev in USB_DEVICES:
        if os.path.exists(dev):
            try:
                subprocess.run(["mount", dev, mount_point],
                               capture_output=True, timeout=10)
                if os.path.ismount(mount_point):
                    return mount_point
            except Exception:
                continue

    return None


def find_update_package(usb_path):
    """Find .scu update files on USB."""
    packages = glob.glob(os.path.join(usb_path, "*.scu"))
    packages += glob.glob(os.path.join(usb_path, "scure-update", "*.scu"))

    if not packages:
        return None

    # Return newest
    packages.sort(key=os.path.getmtime, reverse=True)
    return packages[0]


def verify_signature(payload_path, sig_path):
    """Verify the update package signature using the public key."""
    if not os.path.exists(PUBLIC_KEY):
        return False, "Public key not found"

    try:
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", PUBLIC_KEY,
             "-signature", sig_path, payload_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, "Signature valid"
        return False, f"Invalid signature: {result.stderr}"
    except Exception as e:
        return False, str(e)


def extract_and_verify(scu_path):
    """Extract .scu package, verify signature, return extracted path."""
    work_dir = tempfile.mkdtemp(prefix="scure-update-")

    try:
        # Extract outer .scu (contains .tar.gz + .sig)
        with tarfile.open(scu_path, 'r') as tar:
            tar.extractall(work_dir)

        # Find the payload and signature
        tar_files = glob.glob(os.path.join(work_dir, "*.tar.gz"))
        sig_files = glob.glob(os.path.join(work_dir, "*.sig"))

        if not tar_files or not sig_files:
            return None, "Invalid package structure"

        payload = tar_files[0]
        signature = sig_files[0]

        # Verify signature
        valid, msg = verify_signature(payload, signature)
        if not valid:
            shutil.rmtree(work_dir)
            return None, msg

        # Extract the actual update
        with tarfile.open(payload, 'r:gz') as tar:
            tar.extractall(work_dir)

        # Find the update directory (contains manifest.json)
        for item in os.listdir(work_dir):
            manifest = os.path.join(work_dir, item, "manifest.json")
            if os.path.isfile(manifest):
                return os.path.join(work_dir, item), "OK"

        return None, "No manifest found in package"

    except Exception as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        return None, str(e)


def read_manifest(update_dir):
    """Read the manifest from an extracted update."""
    manifest_path = os.path.join(update_dir, "manifest.json")
    with open(manifest_path) as f:
        return json.load(f)


def install_update(update_dir, progress_callback=None):
    """Run the install process."""
    steps = [
        ("Pre-install backup", ["bash", f"{update_dir}/install.sh", "--pre"]),
        ("Installing update", ["bash", f"{update_dir}/install.sh", "--post"]),
    ]

    total = len(steps)
    for i, (desc, cmd) in enumerate(steps):
        if progress_callback:
            progress_callback(desc, int((i / total) * 100))

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            # Rollback
            subprocess.run(
                ["bash", f"{update_dir}/install.sh", "--rollback"],
                capture_output=True, timeout=120
            )
            return False, f"Failed at '{desc}': {result.stderr}"

    if progress_callback:
        progress_callback("Complete", 100)

    return True, "Update installed successfully"


def run_update():
    """
    Full update flow:
    1. Find USB
    2. Find .scu package
    3. Verify signature
    4. Read manifest
    5. Install
    6. Cleanup

    Returns dict with status updates.
    """
    result = {
        'steps': [],
        'ok': False,
        'version': None,
        'message': '',
    }

    def log(step, status):
        result['steps'].append({'step': step, 'status': status})

    # 1. Find USB
    log('Finding USB drive', 'running')
    usb = find_usb_mount()
    if not usb:
        log('Finding USB drive', 'error')
        result['message'] = 'No USB drive found. Please insert a USB stick.'
        return result
    log('Finding USB drive', 'ok')

    # 2. Find package
    log('Looking for update package', 'running')
    scu = find_update_package(usb)
    if not scu:
        log('Looking for update package', 'error')
        result['message'] = 'No .scu update file found on USB.'
        return result
    log('Looking for update package', 'ok')

    # 3. Verify
    log('Verifying signature', 'running')
    update_dir, msg = extract_and_verify(scu)
    if not update_dir:
        log('Verifying signature', 'error')
        result['message'] = f'Verification failed: {msg}'
        return result
    log('Verifying signature', 'ok')

    # 4. Read manifest
    manifest = read_manifest(update_dir)
    result['version'] = manifest.get('version', 'unknown')
    log(f"Version: {result['version']}", 'ok')

    # 5. Install
    log('Installing update', 'running')
    ok, install_msg = install_update(update_dir)
    if not ok:
        log('Installing update', 'error')
        result['message'] = install_msg
        return result
    log('Installing update', 'ok')

    # 6. Cleanup
    try:
        shutil.rmtree(os.path.dirname(update_dir), ignore_errors=True)
        subprocess.run(["umount", usb], capture_output=True, timeout=10)
    except Exception:
        pass

    result['ok'] = True
    result['message'] = f'Updated to version {result["version"]}'
    return result


if __name__ == '__main__':
    # Test run
    print("Running update process...")
    result = run_update()
    print(json.dumps(result, indent=2))
