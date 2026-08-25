# Stratasys Secure Linux Appliance — Threat Model (Phase 2)

Version 0.1 · 2026-08-25. Companion to [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Assets

| Asset | Where | Confidentiality | Integrity |
|---|---|---|---|
| Application binaries, proprietary algorithms | verity root (`/usr`) | medium (obfuscated, not secret) | **critical** |
| Calibration, machine config, credentials, license | `/data` (LUKS2) | **critical** | critical |
| Device private key | derived in the signed initramfs from the CM5 OTP key (never on disk); optionally an SPI TPM 2.0 | **critical** | critical |
| Serial number / identity binding | `/data/identity` + license | low | **critical** |
| Audit log | `/data/audit` (hash-chained) | low | **critical** |
| Stratasys signing keys (boot.img, EEPROM, license, update CA, image manifest, SSH CA) | **never on the machine** (HSM) | **critical** | critical |
| Manufacturing DB | Stratasys network | high | high |

## 2. Attacker classes

| Class | Capabilities | Typical motive |
|---|---|---|
| **N** — Normal user | Touchscreen / keyboard on the running kiosk | Curiosity, "get to the desktop" |
| **A** — Administrator-level user | Has physical access, can power-cycle, attach USB/keyboard, can put the carrier into `nRPIBOOT` mode | Copy software, change serial, second machine |
| **D** — Disk thief | Removes the SSD, reads it elsewhere | Extract files, clone |
| **S** — Skilled attacker | Above + Linux/firmware skills, `rpiboot`, logic analyser, has time | Clone product, defeat licensing |
| **P** — Full physical access, lab equipment | Above + chip-off eMMC, SoC-level attacks, cold-boot | Reverse engineer, mass clone |
| **M** — Malicious/compromised update source | Can present files to the update path | Persistence, sabotage |

## 3. Scenarios

Risk = likelihood × impact before mitigation (H/M/L). "Residual" is what the attacker can still achieve after all mitigations.

### A — Leave kiosk mode / open a terminal (class N, A)
- **Attack path**: keyboard shortcuts (Alt-F4, Ctrl-Alt-Fn, Ctrl-Alt-Del, Super), Chromium hotkeys (Ctrl-T, F12, Ctrl-Shift-I), crash the browser to land on a desktop, plug a keyboard with media keys, open a `file://` or external URL from the app.
- **Risk**: H likelihood, M impact (a shell as `kiosk` has no privileges, but is a foothold).
- **Mitigation**: no desktop/DM exist; `cage` shows one client and binds no VT-switch keys; `logind NAutoVTs=0`; all gettys masked; `ctrl-alt-del.target` masked; `kernel.sysrq=0`; Chromium managed policy (DevTools off, URL allow-list = app only, downloads off, printing off, incognito off); crash → systemd restarts cage in 2 s (the screen goes black-with-logo, never to a shell); `kiosk` user `nologin`, no sudo installed.
- **Hardware**: none.
- **Residual**: none for class N. Class A can attach a serial adapter to the carrier's UART — the console is disabled in the signed `cmdline.txt` and `config.txt` (`enable_uart=0`), so it prints nothing and accepts nothing.

### B — Remove the SSD and read it on another computer (class D)
- **Attack path**: mount partitions on a Linux laptop.
- **Risk**: H × H.
- **Mitigation**: `/data` is LUKS2 (argon2id, AES-XTS-256); the unlock key is derived inside the signed initramfs from the CM5's OTP device key — it does not exist on the storage. The root partition is readable (Debian + app binaries) but is dm-verity protected, so it cannot be modified and re-inserted. Recovery passphrase is escrowed at Stratasys only.
- **Hardware**: CM5 with secure boot programmed (the OTP key read-out lock depends on it).
- **Residual**: the attacker reads the app binaries (public Debian + Stratasys code; proprietary algorithms are compiled/stripped but reversible with effort). **They obtain no configuration, calibration, license, credentials, audit log or device key.**

### C — Copy the entire disk image (class A, D)
- **Attack path**: `dd` the SSD, write it to another SSD.
- **Risk**: H × H.
- **Mitigation**: as B; a copy written back into the *same* module boots (byte-identical, same OTP key) — acceptable; in *another* module the LUKS key derivation yields a different key, and even with the recovery passphrase the license check fails (device ID ≠ that module's identity key).
- **Residual**: an exact clone works only in the original module — not an attack. Combined with an OTP-key extraction (see L) it becomes one.

### D — Copy the Stratasys application to another computer (class A)
- **Attack path**: extract the app from the root partition (readable), run it on a normal Linux PC.
- **Risk**: H × M.
- **Mitigation**: the app starts only after `stratasys-security` reports `license=valid`, which requires (1) an Ed25519-valid license naming (2) a device ID derived from (3) the module's silicon-derived identity key that signs a live challenge. None of those can be produced without Stratasys' private key. Proprietary modules are compiled (Cython/Rust), stripped, and refuse to import without the security service token.
- **Residual**: a skilled attacker can patch the license check out of the copied binaries (they control that PC). This is the fundamental limit of software on a general-purpose PC (requirement §14): the copied app can be made to *run*, but it will not be a *licensed* machine, will not receive updates (signed, version-floor, device-authenticated), and any proprietary server-side services refuse it. Legal/contractual protection applies here.

### E — Change the machine serial number (class N, A)
- **Attack path**: edit `/data/identity/serial`, edit the DB, edit the license.
- **Risk**: M × M.
- **Mitigation**: normal user has no filesystem access; the serial is *inside the signed license payload* — the file is just a cache; `stratasys-security` compares them and treats a mismatch as `LICENSE_INVALID`. The app exposes the serial read-only through the security socket. Manufacturing DB is on the Stratasys network, role-based, audited.
- **Residual**: none without the license signing key.

### F — Second machine with the same license (class A, S)
- **Attack path**: copy `/data/license.json` and identity files to another provisioned or unprovisioned PC.
- **Risk**: H × H.
- **Mitigation**: the license names one device ID = hash of one module's identity public key; a second module cannot sign the challenge; the Manufacturing DB detects duplicate serials reporting from two device IDs and can revoke.
- **Hardware**: CM5 secure boot (OTP key read-out lock) or SPI TPM 2.0.
- **Residual**: a class-P attacker extracting the OTP key from the SoC (silicon-level attack, or a VideoCore firmware vulnerability).

### G — Modify an application binary (class A, S)
- **Attack path**: edit a file on the root partition (offline) or at runtime.
- **Risk**: M × H.
- **Mitigation**: root is dm-verity; the root hash is inside the signed `boot.img`; a changed block fails to read (I/O error) → service fails → kiosk shows the Integrity Error screen; runtime `/usr` is read-only and there is no package manager; defence-in-depth manifest re-hash by the security service at every start.
- **Residual**: an attacker who can also replace `boot.img` needs the boot-signing key → see K.

### H — Boot from USB / SD (class A)
- **Attack path**: plug a USB stick or SD card with another OS; use `nRPIBOOT` + `rpiboot` to boot a foreign image over USB.
- **Risk**: H × H.
- **Mitigation**: the signed EEPROM config sets `BOOT_ORDER` to internal storage only; in secure-boot mode the boot ROM/EEPROM only executes a `boot.img` signed with the key whose hash is in OTP — including `rpiboot` payloads. A foreign image is refused before the kernel runs.
- **Hardware**: CM5 with OTP programmed (irreversible).
- **Residual**: none below silicon level — there is no CMOS reset on a Pi. Denial of service (erasing the storage via `rpiboot` mass-storage mode) remains possible; the attacker gains a verity root and an encrypted `/data` (see B).

### I — Access firmware settings (class A)
- **Attack path**: edit `config.txt`, EEPROM config, or use `rpiboot` recovery payloads.
- **Risk**: H × M.
- **Mitigation**: `config.txt`/`cmdline.txt` live inside the signed `boot.img`; the EEPROM config is part of the signed EEPROM image (`SIGNED_BOOT=1`, self-update disabled); recovery payloads must be signed. There is no interactive firmware UI on a Pi.
- **Residual**: none without the boot-signing key. The appliance additionally refuses Production Mode when it detects secure boot is *not* enabled (lab module), so a mis-provisioned unit is visible.

### J — Read security keys from the filesystem (class A, S)
- **Attack path**: find the license signing key, device key, or LUKS key on disk.
- **Risk**: H × H if such keys existed.
- **Mitigation**: none of them exist on disk. The boot/license/update/image **private** keys are never on the machine; the device private key is derived from the OTP key in the initramfs and held only in the security service's memory (the OTP read-out is locked before user space starts); the LUKS key is derived the same way and never stored; service SSH uses short-lived certificates; the only on-disk secrets are in LUKS `/data` with `0400` permissions, owned by `security`.
- **Residual**: root at runtime can read `/data` secrets (config, calibration, cached license) and, with a debugger, the identity key from the security service's memory — there is no interactive root; the only root-capable path is a certificate-authenticated engineer during a Service window, and that is audited.

### K — Replace the operating system (class A, S)
- **Attack path**: install another OS on the SSD or replace the UKI.
- **Risk**: M × H.
- **Mitigation**: the EEPROM refuses an unsigned `boot.img`; a foreign OS cannot run at all on a programmed module. If the attacker moves the storage to a *non-secure-boot* Pi, it boots the verity root but cannot derive the `/data` key — no license, no calibration, no config.
- **Residual**: the attacker turned a Stratasys module into a blank module (or an unlicensed one). Availability loss, no confidentiality loss.

### L — Clone the SSD into another computer (class S, P)
- **Attack path**: as C + the second computer.
- **Risk**: M × H.
- **Mitigation**: OTP-derived LUKS key + silicon-bound license (B, F). The key never crosses an external bus — it is read inside the SoC by the signed initramfs.
- **Residual**: a class-P attacker exploiting a VideoCore/EEPROM firmware vulnerability, or a silicon-level OTP extraction. If an SPI TPM is used for identity, the discrete-TPM bus-sniffing class of attacks applies to *that* key exchange (mitigated by TPM parameter encryption); for this reason the OTP-derived path is preferred for the LUKS key even when a TPM is present. Even then, a clone yields `/data` but **not** a working identity — the clone runs unlicensed (F).

### M — Malicious or corrupted software update (class M, A)
- **Attack path**: a tampered USB `.scu`, a MITM on the HTTPS update source, an old vulnerable but validly signed version, a corrupted download.
- **Risk**: M × H.
- **Mitigation**: RAUC bundles are CMS-signed with a certificate chained to the Stratasys update CA (root inside the verity root); TLS with pinned Stratasys CA; the manifest carries `minVersion` (anti-rollback floor in `/data/security`); writes only to the inactive slot; tryboot boot-once with automatic fallback; the slot is marked good only after the security service confirms license + integrity + app health; every attempt audited with signer identity.
- **Residual**: compromise of the update CA itself (HSM + rotation + revocation via next bundle); a physical attacker can re-flash via `rpiboot` — but only a Stratasys-signed image boots, so the result is a blank or unlicensed unit, not a compromised one.

## 4. Protection matrix

| | N user | A admin-level | D disk theft | S skilled | P physical lab |
|---|---|---|---|---|---|
| Leave kiosk | Blocked | Blocked | — | Blocked (via other vectors) | — |
| Read `/data` secrets | Blocked | Blocked | **Blocked** | Blocked (TPM) | Possible with dTPM bus attack |
| Read app binaries | Blocked | Possible (verity root readable offline) | Possible | Possible | Possible |
| Modify app | Blocked | Blocked | Blocked | Blocked (Secure Boot) | Blocked unless firmware defeated → then unlicensed |
| Change serial | Blocked | Blocked | Blocked | Blocked | Blocked |
| Second licensed machine | Blocked | Blocked | Blocked | Blocked | Only by extracting the TPM key |
| Unauthorised boot | Blocked | Blocked (OTP secure boot) | — | Blocked | Blocked below silicon level |
| Unauthorised service access | Blocked | Blocked | — | Blocked (certificates) | — |

## 5. Explicit limitations (requirement §14)

1. **Software on a general-purpose PC cannot be made impossible to extract.** The root filesystem is readable when the disk is removed. What we make *infeasible* is: obtaining a licensed, updatable, working second machine; reading any machine-specific secret; and modifying the shipped software without detection.
2. **Secure boot on the CM5 is irreversible.** Programming the OTP is a one-way operation: a lost boot-signing key would make it impossible to ship new boot images to programmed units. Key custody (HSM, dual control, escrowed backup) is therefore a *production* requirement, not an IT nicety.
3. **The OTP-key protection rests on the VideoCore firmware and secure boot.** A vulnerability in the closed-source bootloader/firmware could expose the key. Raspberry Pi publishes EEPROM updates; the update pipeline must be able to ship signed EEPROM images.
3b. **x86 variant only**: firmware controls (USB boot, admin password) are not enforced by Linux and are undone by a CMOS reset; discrete-TPM bus sniffing is a published attack class. See ARCHITECTURE.md §12.
4. **Runtime root** (a Stratasys engineer in Service Mode) can read `/data`. That is by design and audited; the private device key still never leaves the TPM.
5. **Obfuscation of algorithms** (compiled/stripped modules) delays, it does not prevent, reverse engineering.

## 6. Security requirements derived (traceability)

| ID | Requirement | Mitigates |
|---|---|---|
| SR-1 | No getty, no DM, cage single-client, Chromium managed policy | A |
| SR-2 | `/data` LUKS2, key derived from the OTP device key in the signed initramfs, recovery key escrowed | B, C, J, L |
| SR-3 | Root dm-verity, roothash in signed `boot.img` | G, K |
| SR-4 | Pi secure boot: OTP key hash programmed, dev key revoked, signed EEPROM config, JTAG lock | H, I, K |
| SR-5 | Silicon-derived (or TPM) device key, device ID = hash(pubkey), live challenge | D, F, L |
| SR-6 | Ed25519 license with serial + device ID; verified at boot and periodically | D, E, F |
| SR-7 | Signed updates, inactive-slot write, boot counting, version floor | M |
| SR-8 | Hash-chained audit log written only by the security service | E, all |
| SR-9 | No static credentials; SSH certificates; time-boxed sshd | J, service abuse |
| SR-10 | Appliance refuses Production Mode when secure boot not active / identity unavailable / integrity failed / license invalid | H, I, G, D |
