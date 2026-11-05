# sCureBox-CS 1.0.152 — Deploy-Ops tickets (OPS-)

## Repo, deploy, kiosk, QA — overview

Everything in this file was read from the sCureBox-CS repo at version 1.0.152. These tickets cover everything outside `src/`, except `docs/srs`. Source code under `src/` belongs to the other areas (Domain, Hardware, Application-Process, Application-Platform, Dvt-Hdt, Api, Native UI). Where an OPS ticket depends on a contract in `src/` (command-line modes, environment variables, endpoints), it names that contract and the owning area.

### Repo tree (top 2 levels, build outputs and large binaries left out)

```
SCureBox.sln                 solution: 5 src projects + 5 test projects, solution folders "src" and "tests"
Directory.Build.props        shared MSBuild properties (net10.0, warnings as errors, ...)
global.json                  SDK pin 10.0.100, rollForward latestFeature
VERSION                      single line "1.0.152": the product version
README.md                    layer overview + local run commands
CHANGE_SUMMARY.md            human change summary 0.4.9 -> 1.0.64 (refers to a CHANGE_SUMMARY.he.md that is NOT in the repo)
.gitignore / .gitattributes
branding/                    logo.png, logo@2x.png, logo.svg, splash-preview.png
config/                      components.json, errors.json, origin.json, presets.json, system.json, versions.json
deploy/
  config-txt-fragment.txt    boot config.txt fragment (I2C, GPIO rest levels, SPI off ...)
  display-10inch.txt         Touch Display 2 (10.1") config.txt profile
  networkmanager-scurebox.conf
  io-safe-boot.sh            early-boot IO rest state
  netbird-enroll.sh          NetBird install + enrollment
  install.sh                 on-device installer
  publish.ps1                build the linux-arm64 release tarball
  deploy-to-pi.ps1           scp + remote install.sh (legacy helper)
  install-scurebox.ps1       developer one-stop installer (deploy | flash)
  install-desktop-shortcut.ps1
  make-installer.ps1         portable field-installer bundle (.zip)
  make-demo-installer.ps1    Windows PC demo setup .exe (IExpress)
  package-origin-app.ps1 / package-origin-app.sh   Origin application package (.tgz)
  prepare-cm5.ps1            publish + build image + flash in one command
  scurebox-ui.service, scurebox.service, scurebox-io-safe.service, scurebox-watchdog.service,
  scurebox-dvt-bench.service, scurebox-netbird-enroll.service
  db/                        schema.sql, seed_presets.sql (PostgreSQL)
  keys/                      scure-update.pub (RSA public key for signed USB updates)
  kiosk/                     scurebox-kiosk.service, scurebox-kiosk.sh, chromium-policy.json, labwc/rc.xml, loading.html, logo.png
  plymouth/scurebox/         scurebox.plymouth, scurebox.script, logo.png
  origin-app/                run.sh, run-watchdog.sh, run-dvt-runner.sh
  installer/                 Install-sCureBox.ps1, Install-sCureBox-GUI.ps1, Install-sCureBox.cmd, "sCureBox Installer.cmd", README.txt
  image/                     build-image.py, patch-display.py, test_patch_display.py, flash-cm5.ps1, unxz.py, README.md
                             (input/, out/, cache/ are git-ignored work folders)
  out/                       git-ignored build outputs
docs/                        01-api-contract.md, 02-hardware-map.md, 03-ui-and-qa.md, 04-ui-spec.md, 05-native-ui.md,
                             06-srs.md, HSI_sCure.xlsx, sCure_SRS.html, srs/ (not in this area)
pwa/                         index.html, app.js, styles.css, sw.js, manifest.webmanifest, icons/, tests/test_pwa.py, README.md
qa/                          qa-tests.js, run-qa.mjs, qa-tool.html, run-all.ps1, last-qa-report.json, README.md
reference/                   original Python sources the port came from (read-only): app.py, io_controller.py, io_bridge.py,
                             updater.py, db.py, temperature_control.py, cooling_mode.py, led_calibration.py,
                             hdt_calibration.py, picolog_tc08.py
src/                         SCureBox.Api, SCureBox.Application, SCureBox.Domain, SCureBox.Hardware, SCureBox.Ui (other areas)
tests/                       SCureBox.{Api,Application,Domain,Hardware,Ui}.Tests
ui/dist/                     vendored React build (Step A web UI) served as wwwroot
```

The working tree also has untracked files at the root: `1.0.1_origin.img.xz` (a 1.28 GB OS image) and `NUL` (a 95-byte file left by a Windows redirect). `.gitignore` ignores both (`*.img.xz`, `NUL`). A rebuild must not create them.

### Runtime topology on the device

**A. Raspberry Pi OS image** (built by `build-image.py` or installed with `install.sh`). systemd, every service runs as `root` unless stated otherwise:

| Unit | Process | Port / IPC | Notes |
|---|---|---|---|
| `scurebox-io-safe.service` | oneshot `/bin/bash /opt/scurebox/deploy/io-safe-boot.sh` | — | `WantedBy=sysinit.target`. Drives the SSR/relay lines to rest before the firmware starts. |
| `scurebox-ui.service` (default, `--ui native`) | `/opt/scurebox/scurebox-ui`: firmware + API + native Avalonia UI on DRM/KMS, tty1 | HTTP `*:3001` (IPv4+IPv6) | `Type=notify`, `WatchdogSec=60`, `RuntimeDirectory=scurebox` (`/run/scurebox`). |
| `scurebox.service` (`--ui browser`) | `/opt/scurebox/scurebox`: firmware + API + React UI from wwwroot | HTTP `*:3001` | Mutually exclusive with `scurebox-ui.service`. |
| `scurebox-kiosk.service` (`--ui browser` only) | labwc + Chromium as the desktop user (uid 1000) on tty1 | opens `http://localhost:3001` | Created from a template by `install.sh`. |
| `scurebox-watchdog.service` | `/opt/scurebox/scurebox --watchdog --timeout 20` | reads `/run/scurebox-heartbeat` | Not bound to the firmware unit. `Nice=-5`. |
| `scurebox-dvt-bench.service` | `/opt/scurebox/scurebox --dvt-bench --port 3002 --firmware http://127.0.0.1:3001` | HTTP `:3002` (`/bench/status`) | Not bound to the firmware unit. |
| `scurebox-netbird-enroll.service` | oneshot `netbird-enroll.sh`, retried every 60 s | — | Enabled only while a setup key is waiting. |
| `netbird.service` | vendor NetBird client (WireGuard mesh) | wt0 | Installed by `netbird-enroll.sh`. |

Paths: application `/opt/scurebox` (rsync of the release; `/opt/scurebox/data` is a symlink to `/var/lib/scurebox`); machine config `/etc/scurebox/components.json` (seeded once, never overwritten); data `/var/lib/scurebox` (+ `logs/`); `/var/log/scure`; heartbeat `/run/scurebox-heartbeat`; NetBird key `/etc/scurebox/netbird-setup-key` (0600, deleted after enrollment); kiosk `/etc/scurebox/labwc/`, `/etc/chromium/policies/managed/scurebox.json`; Plymouth theme `/usr/share/plymouth/themes/scurebox/`; NetworkManager `/etc/NetworkManager/conf.d/90-scurebox-wired.conf`; TC-08 driver `/opt/picoscope/lib` (from Pico's .deb); first-boot log `/var/log/scurebox-firstrun.log`. Default login user: uid 1000, `scure` by default (see OPS-12). Hostname `scurebox` (mDNS `scurebox.local`).

**B. Origin image** (factory GPT A/B image; read-only erofs root; Origin supervisor at `http://127.0.0.1:8080`). sCureBox is installed as an *application package* (OPS-15):

| Manifest service | Script | User |
|---|---|---|
| `scurebox-main` | `/bin/sh main/run.sh` → `dotnet ./scurebox-ui.dll` in window mode under labwc | `root` |
| `scurebox-watchdog` | `/bin/sh main/run-watchdog.sh` → `dotnet ./scurebox.dll --watchdog --timeout 20` | `root` |
| `scurebox-dvt-runner` | `/bin/sh main/run-dvt-runner.sh` → `node dvt-runner/runner/dvt-runner.cjs <cfg>` (or idle) | supervisor default (no `user` key) |

Paths: version folder `/opt/app/versions/<version>/` (read-only); persistent state `/opt/data/scurebox/` (`data/`, `components.json`, `native/`, `ui.env`, `dvt-runner.json`); heartbeat `/dev/shm/scurebox-heartbeat`. Install: `POST :8080/api/application/install {"path": "/tmp/<pkg>.tgz"}`.

**C. Windows PC demo**: `%LOCALAPPDATA%\Programs\sCureBox Demo\scurebox-ui.exe` with a `demo.mode` marker → simulator, window 1600x1000, `http://127.0.0.1:3011`, data in `%LOCALAPPDATA%\sCureBox Demo\data`.

**Ports used anywhere:** 3001 firmware API/UI; 3002 DVT bench; 3011 PC demo; 3111 / 3112 QA servers (`run-all.ps1`); 8080 Origin supervisor; 8080 also the PWA's local test server (`python -m http.server`).

---

### OPS-01 — Repository skeleton, solution and build conventions
**Summary**
- **What it is for:** The basic layout of the code repository: the solution file, shared build settings, logos and reference documents.
- **Problem it solves:** Without one shared setup, projects build differently, warnings slip through, and scripts made on Windows break on the Pi because of wrong line endings.
- **How we solve it:** Create one solution with shared settings (.NET 10, warnings count as errors), fixed ignore rules so keys and OS images are never committed, and Linux line endings for scripts.

**Project / folder:** repo root (`SCureBox.sln`, `Directory.Build.props`, `global.json`, `.gitignore`, `.gitattributes`, `README.md`, `branding/`, `reference/`, `docs/` except `docs/srs`)
**Goal:** Create the repository layout, the solution and the shared build settings so that every project builds the same way (net10.0, nullable, warnings as errors) and every script and asset has the right line endings. This ticket gives a clean `dotnet build SCureBox.sln` with no warnings once the other areas add their sources.
**Depends on:** none (first ticket). The other areas fill `src/` and `tests/`.
**Files to create:**
- `SCureBox.sln`: VS format 12.00, header "Visual Studio Version 17". Solution folders `src` (SCureBox.Api, SCureBox.Application, SCureBox.Domain, SCureBox.Hardware, SCureBox.Ui) and `tests` (SCureBox.Api.Tests, SCureBox.Application.Tests, SCureBox.Domain.Tests, SCureBox.Hardware.Tests, SCureBox.Ui.Tests). Configurations Debug/Release, Any CPU.
- `Directory.Build.props`: shared properties (below).
- `global.json`: `{"sdk":{"version":"10.0.100","rollForward":"latestFeature"}}`.
- `.gitignore`, `.gitattributes` (below).
- `README.md`: the layer table (UI src/SCureBox.Ui = Step B native Avalonia; ui/dist = Step A React build served at http://localhost:3001, still shipped through `install.sh --ui browser`; Application; Domain; Hardware; Host = SCureBox.Api) and the local run commands.
- `branding/logo.svg` (white stroked "S" mark: four lines, stroke width 5.5, square caps, viewBox `-3 -7 106 141`), `logo.png`, `logo@2x.png`, `splash-preview.png`.
- `reference/*.py`: the original Python sources, kept read-only as the porting reference. No build uses them.
- `docs/01-api-contract.md` … `docs/06-srs.md`, `docs/HSI_sCure.xlsx`, `docs/sCure_SRS.html`: specification documents, carried over unchanged. Other areas own their content.
**Public contract:**
- `Directory.Build.props`: `TargetFramework=net10.0`, `Nullable=enable`, `ImplicitUsings=enable`, `LangVersion=latest`, `TreatWarningsAsErrors=true`, `WarningsNotAsErrors=CS1591;xUnit1004`, `InvariantGlobalization=true`, `SatelliteResourceLanguages=en`, `Version=1.0.0` (fixed; the product version comes from `VERSION`, see OPS-02), `Company=sCure`, `Product=sCureBox firmware`, `NoWarn=$(NoWarn);CA1416`.
- Assembly names: `scurebox` (SCureBox.Api) and `scurebox-ui` (SCureBox.Ui). The deploy scripts depend on these names.
- Local run: `SCURE_SIMULATE=1 dotnet run --project src/SCureBox.Ui` gives the native UI in a 1920x1200 window plus the API on :3001. `dotnet run --project src/SCureBox.Api` gives the API plus the React UI only.
**Behaviour & rules:**
1. `.gitignore` must contain exactly these entries: `bin/`, `obj/`, `*.user`, `.vs/`, `TestResults/`, `deploy/out/`, `deploy/image/cache/`, `deploy/image/out/`, `data/`, `src/SCureBox.Api/GITINFO`, `*.log`, `*netbird-setup-key*` with the exception `!deploy/netbird-enroll.sh`, `deploy/image/input/`, `*.img`, `*.img.xz`, `NUL`. Each group carries a short comment saying why it is ignored. NetBird keys and OS images must never be committed.
2. `.gitattributes`: `* text=auto`. Use `eol=lf` for `*.sh *.py *.service *.script *.plymouth *.html *.xml *.c`, and mark `*.png` as binary. Shell scripts and units built on Windows must reach the Pi with LF line endings.
3. The SDK is resolved from `%LOCALAPPDATA%\Microsoft\dotnet\dotnet.exe` when it exists (a user-local SDK), otherwise from `dotnet` on PATH. Every PowerShell build script uses this rule and sets `DOTNET_CLI_TELEMETRY_OPTOUT=1`.
4. Warnings are errors in every project, including tests.
**Configuration:** none.
**Acceptance criteria:**
- `dotnet build SCureBox.sln -nologo -v q` succeeds with 0 warnings once the area projects exist.
- `git check-ignore` matches `deploy/out/x`, `foo.img.xz`, `deploy/my-netbird-setup-key.txt` and `NUL`. It does not match `deploy/netbird-enroll.sh`.
- A `.sh` file committed from Windows is checked out with LF line endings.
**Tests:** a build of the solution; `git check-ignore -v` for the paths above.
**Reference (source):** `SCureBox.sln`, `Directory.Build.props`, `global.json`, `.gitignore`, `.gitattributes`, `README.md`, `branding/`, `reference/`

---

### OPS-02 — Versioning convention (VERSION, versions.json, GITINFO)
**Summary**
- **What it is for:** The rule for how the product version is numbered, recorded and shown on the machine.
- **Problem it solves:** Without it, nobody knows which version runs on a unit or what changed between releases.
- **How we solve it:** One VERSION file plus a release-notes list. Every change raises the version and adds notes. Builds also stamp the git commit, and the unit shows it in Settings and through the API.

**Project / folder:** `VERSION`, `config/versions.json`, `CHANGE_SUMMARY.md`; consumed by `src/SCureBox.Api` and `src/SCureBox.Ui`
**Goal:** One product version string with a release-notes registry. Every change bumps the version and adds an entry. Build scripts stamp the git commit next to the executables, and the running unit reports the version through `/api/system/version` and the Settings > Versions modal.
**Depends on:** OPS-01. Api (`/api/system/version`, `scurebox --version`), Native UI (Versions dialog).
**Files to create:**
- `VERSION`: one line, semver `MAJOR.MINOR.PATCH` (here `1.0.152`), trailing newline allowed.
- `config/versions.json`: the release-notes registry.
- `CHANGE_SUMMARY.md`: a free-form, human-written summary of the changes (no tooling reads it).
**Public contract:**
- `config/versions.json` = `{"_comment": "<rule text>", "history": [ {"version": "1.0.152", "date": "YYYY-MM-DD", "notes": ["...", "..."]}, ... ]}`, newest first. The repo has 265 entries, from 1.0.152 back to 0.1.0 (2026-08-06). The `_comment` text is: "sCure version registry - newest first. On every release: bump the VERSION file at the repo root AND add an entry here (version, date, notes). The Settings > Versions modal shows this list."
- `GITINFO` (generated, never committed): two lines, the short commit hash (`git rev-parse --short HEAD`) and the commit date (`git log -1 --format=%cs`, YYYY-MM-DD). The build scripts write it to `src/SCureBox.Api/GITINFO` and copy it to the payload root.
- The `SCureBox.Api.csproj` content items copy `../../VERSION` to the output root as `VERSION` and `../../config/**` to `config/` (CopyToOutput and CopyToPublish = PreserveNewest).
- Version resolution at runtime (Api / Application-Platform): read the first line of `<AppContext.BaseDirectory>/VERSION`. If it is missing or empty, fall back to `AssemblyInformationalVersion` (the part before `+`), then to the assembly version (3 parts), then to `"unknown"`. `/api/system/version` returns `{appVersion, gitCommit, gitDate, lastBoot, os, kernel, python:null, runtime, emmcSerial}`. `gitCommit` and `gitDate` come from `GITINFO`, or null when it is missing.
- `scurebox --version` prints the same app version and exits.
**Behaviour & rules:**
1. Every code change bumps `VERSION` (normally the PATCH number) and inserts a new object at index 0 of `history` with the same version, today's date and one or more notes. Notes are full sentences: what changed and why (often "user, <date>"), followed by a "Tests: ..." note that names the tests that prove it.
2. Commit messages follow `type(scope): summary - v1.0.N` (for example `fix: ... - v1.0.86`, `feat(ui): ... - v1.0.81`). Older commits used `v1.0.N: summary`. A commit that covers several versions writes `v1.0.87..1.0.106`.
3. `Directory.Build.props` `Version` stays `1.0.0`. It is not synchronised with `VERSION`.
4. The release artifact names carry the version read from `VERSION`: `scurebox-<v>-linux-arm64.tar.gz`, `scurebox-<v>-origin-app.tgz`, `scurebox-<v>-cm5.img`, `sCureBox-Installer-<v>.zip`, `sCureBox-Demo-Setup-<v>.exe`. Downstream tools take the version from the tarball name: the second `-`-separated token.
5. `ui/dist/config/versions.json` is a separate file with the same shape: the web UI's own registry (sCure-A 0.9.4). It is not the firmware registry. See OPS-11.
**Configuration:** none.
**Acceptance criteria:**
- `VERSION` and `history[0].version` are equal.
- `scurebox --version` prints the VERSION content.
- After `publish.ps1`, the payload root holds `VERSION` and `GITINFO`, and `/api/system/version` shows `gitCommit` and `gitDate`.
- With `GITINFO` removed, `gitCommit` and `gitDate` are null and the endpoint still answers.
**Tests:** `tests/SCureBox.Application.Tests/Platform/SystemServiceTests.cs` (writes a temporary `VERSION` "0.9.1" and expects appVersion 0.9.1); `tests/SCureBox.Api.Tests/StaticUiTests.cs` (`/config/versions.json` is served); QA row `sys_version` (appVersion is x.y.z and every key is present).
**Reference (source):** `VERSION`, `config/versions.json`, `CHANGE_SUMMARY.md`, `src/SCureBox.Api/SCureBox.Api.csproj`, `src/SCureBox.Api/Infrastructure/CommandLine.cs` (ReadAppVersion), `src/SCureBox.Application/Platform/SystemService.cs` (Version/ReadAppVersion), `src/SCureBox.Ui/ViewModels/Dialogs/VersionsDialogViewModel.cs`, `deploy/publish.ps1`

---

### OPS-03 — Release build: publish.ps1 and the linux-arm64 payload
**Summary**
- **What it is for:** The release build script that packs the sCure Box software for the Raspberry Pi into one file.
- **Problem it solves:** Every install path needs the same complete, clean package; once an OS image left inside made a release too big to install.
- **How we solve it:** A script runs the tests, builds both programs for the Pi, adds config, install scripts and keys, leaves out images and secrets, fixes line endings and creates one tarball.

**Project / folder:** `deploy/publish.ps1`, `deploy/deploy-to-pi.ps1`, `deploy/keys/`, `deploy/db/`
**Goal:** Build the self-contained linux-arm64 release, which is both executables plus everything `install.sh` needs, as one tarball. The tarball is the input of every installer path: SSH deploy, image build, and the field installer.
**Depends on:** OPS-01, OPS-02. Api and Native UI (the projects being published), Hardware (`src/SCureBox.Hardware/native`).
**Files to create:** `deploy/publish.ps1`; `deploy/deploy-to-pi.ps1`; `deploy/keys/scure-update.pub`; `deploy/db/schema.sql`; `deploy/db/seed_presets.sql`.
**Public contract:**
- `publish.ps1 [-Runtime linux-arm64] [-SkipTests]` writes `deploy/out/scurebox-<version>-<Runtime>.tar.gz`, which holds one top-level folder `scurebox-<version>-<Runtime>/`.
- Payload layout:
  - `scurebox`, `scurebox-ui` plus their DLLs and the .NET runtime (self-contained, not single-file, `DebugType=none`, `UseAppHost=true`)
  - `wwwroot/` (ui/dist)
  - `config/`
  - `VERSION`, `GITINFO`
  - `deploy/`: a copy of the repo deploy folder without `out`, `image/cache`, `image/out`, `image/input`, `*netbird-setup-key*`, `*.img`, `*.img.xz`, `*.img.zip`
  - `native/`: a copy of `src/SCureBox.Hardware/native`, which includes `build-pio-helpers.sh`, `pio_*.c` and `linux-arm64/`
  - `keys/scure-update.pub`
- `deploy-to-pi.ps1 -Host <ip> [-User testingpi] [-Key ~/.ssh/scure_pi] [-Tarball] [-SudoPassword <securestring>] [-NoKiosk] [-Reboot]` copies the newest tarball to `/tmp`, extracts it and runs `sudo ./deploy/install.sh`. When a password is given it is echoed to `sudo -S`; otherwise it uses `sudo -n`.
- `keys/scure-update.pub`: a PEM "PUBLIC KEY" (an RSA 4096-bit SubjectPublicKeyInfo, 814 bytes). It verifies signed `.scu` USB update packages. The matching private key is NOT in the repo. It is passed to `scurebox --make-update-package <folder> <privateKeyPem> <out.scu>` when a package is built. A rebuild generates its own key pair, commits only the public half, and keeps the private half outside the repo.
- `deploy/db/schema.sql`: idempotent PostgreSQL schema (`CREATE ... IF NOT EXISTS`, `pgcrypto`). Tables: resins, materials, cure_profiles, printers, jobs, prints, build_heads, tray_membranes, print_hardware, cure_boxes, cure_sessions, cure_runs (+ JSONB `sensor_issues`, `fan_issues`, `run_alerts` added with `ALTER ... ADD COLUMN IF NOT EXISTS`), cure_run_telemetry (+ `fan_rpm` JSONB), cure_reports. Views: v_materials, v_print_history, v_cure_history.
- `deploy/db/seed_presets.sql`: one `WITH ins AS (INSERT INTO materials (ext_id,name,is_preset) ... ON CONFLICT (ext_id) DO NOTHING RETURNING id) INSERT INTO cure_profiles ...` block per preset (`preset-ST45`, `preset-Carbon Fiber`, ...), with the steps JSON. The Application-Platform persistence layer looks for these files in `<app>/db`, then `<app>/deploy/db`, then the repo's `deploy/db`, and applies them when `DATABASE_URL` is set.
**Behaviour & rules:**
1. Unless `-SkipTests` is given, run `dotnet test SCureBox.sln -nologo -v q` first and stop if it fails.
2. Write GITINFO (OPS-02). A git failure is not fatal.
3. Publish `src/SCureBox.Api/SCureBox.Api.csproj`, then `src/SCureBox.Ui/SCureBox.Ui.csproj`, into the same stage folder with `-c Release -r <rt> --self-contained true -p:PublishSingleFile=false -p:DebugType=none -p:UseAppHost=true`.
4. Copy deploy/ with robocopy, excluding the folders and files above. Robocopy exit codes below 8 are success. A 1.3 GB OS image once ended up in a release and the boot partition could not hold it, so image files are always excluded.
5. Rewrite every `*.sh` in the stage with LF line endings, UTF-8 without BOM.
6. Create the tar with Windows' own `%SystemRoot%\System32\tar.exe` (bsdtar), run from `deploy/out`. A Git-for-Windows tar mangles Windows output paths.
7. Print the tarball size in MB.
**Configuration:** none. The NetBird key and passwords are never part of the payload.
**Acceptance criteria:**
- The tarball has exactly one top-level folder.
- `scurebox`, `scurebox-ui`, `wwwroot/index.html`, `config/components.json`, `deploy/install.sh`, `native/build-pio-helpers.sh`, `keys/scure-update.pub`, `VERSION` are present.
- No `*.img*` or `*netbird-setup-key*` file is in the tarball.
- Every `.sh` in it has no CR characters.
- A failing test stops the publish unless `-SkipTests` is given.
**Tests:** manual. `tar -tzf` the output and check the list above, then `install.sh` on a unit (OPS-04).
**Reference (source):** `deploy/publish.ps1`, `deploy/deploy-to-pi.ps1`, `deploy/keys/scure-update.pub`, `deploy/db/schema.sql`, `deploy/db/seed_presets.sql`, `src/SCureBox.Api/Infrastructure/CommandLine.cs`, `src/SCureBox.Application/Platform/UpdateService.cs`, `src/SCureBox.Application/Persistence/PostgresDatabaseInitializer.cs`

---

### OPS-04 — On-device installer install.sh
**Summary**
- **What it is for:** The install script that runs on the machine and sets up the sCure Box software and system.
- **Problem it solves:** Setting up a unit by hand (files, boot settings, screen, services, remote access, drivers) is slow and error-prone, and must work the same way every time.
- **How we solve it:** One script, safe to run again, that copies the app, keeps existing machine settings, sets boot and display options, installs services, remote access and drivers, and does not fail just because there is no internet.

**Project / folder:** `deploy/install.sh`, `deploy/networkmanager-scurebox.conf`
**Goal:** A single idempotent root script, run from an extracted release. It installs the application to `/opt/scurebox`, sets up the boot configuration, display, splash, systemd services, remote access, network tolerance and the DVT drivers, and restarts everything. The image first boot, the SSH deploy and the field installer all use it.
**Depends on:** OPS-03, OPS-05, OPS-06, OPS-07, OPS-08, OPS-09, OPS-10.
**Files to create:** `deploy/install.sh`; `deploy/networkmanager-scurebox.conf`.
**Public contract:**
- `sudo ./deploy/install.sh [--ui native|browser] [--no-kiosk] [--reboot|--no-reboot] [--payload DIR] [--netbird-key KEY] [--no-netbird]`. Defaults: `--ui native`, kiosk on, no reboot, NetBird on, payload = the parent of the script's directory. An unknown option prints "unknown option X" and exits 2. If not run as root, it prints "run as root (sudo)" and exits 1. If the payload has no `./scurebox`, it exits 1.
- Log lines are prefixed `[install] `. Callers look for these substrings to tell that the boot config changed: "scurebox fragment", "Touch Display 2 profile", "Plymouth theme".
- `networkmanager-scurebox.conf` is installed to `/etc/NetworkManager/conf.d/90-scurebox-wired.conf`. Content: section `[connection-scurebox-wired]`, `match-device=interface-name:eth0`, `ipv4.dhcp-timeout=2147483647`.
**Behaviour & rules (in order):**
1. `chmod +x` the payload's `scurebox`, `deploy/*.sh`, `deploy/kiosk/*.sh`, `native/*.sh`. Errors are ignored, because a tarball from Windows loses the mode bits.
2. Disable and stop the legacy `scure.service` and `scure-io-safe.service` when they are enabled (the old Python firmware used the same port 3001). Then stop `scurebox.service`.
3. `mkdir -p /opt/scurebox /etc/scurebox /var/lib/scurebox /var/lib/scurebox/logs`. Run `rsync -a --delete --exclude data payload/ → /opt/scurebox/`. If rsync fails, use `rm -rf` and `cp -a`. Then chmod again. Seed `/etc/scurebox/components.json` from `config/components.json` only when it does not exist. Run `ln -sfn /var/lib/scurebox /opt/scurebox/data`.
4. Run `raspi-config nonint do_i2c 0` (non-fatal). Boot config is `/boot/firmware/config.txt`, or `/boot/config.txt`. Append `config-txt-fragment.txt` when the file has no `>>> scurebox` marker. Append `display-10inch.txt` when the file has no `vc4-kms-dsi-ili79600-10-1inch`.
5. A/B images. For each of `/dev/disk/by-partlabel/boot_a` and `boot_b` that exists: use its current mount point and remount it rw, or mount it as vfat on a temporary directory. When its `config.txt` (case-insensitive name) has no line starting `dtoverlay=vc4-kms-dsi-ili79600-10-1inch`, append `[all]` plus the display profile, `sync`, and log "A/B: 10.1" Touch Display 2 profile added to <slot>". Unmount a temporary mount afterwards.
6. PIO helpers. When `gcc` exists: if `/usr/local/src/utils/piolib` is missing, run `git clone --depth 1 https://github.com/raspberrypi/utils /usr/local/src/utils`. Then run `PIOLIB=/usr/local/src/utils/piolib bash /opt/scurebox/native/build-pio-helpers.sh /opt/scurebox/native`. A failure is logged ("servo falls back to software PWM") and is not fatal. OPEN QUESTION: `build-pio-helpers.sh` reads `PIOLIB_SRC`, not `PIOLIB`, and treats `$1` only as `install`. In practice it clones piolib again into `/tmp/rpi-utils` and builds into its own directory (`/opt/scurebox/native`). Decide whether to fix the variable name.
7. systemd UI mode. If `--ui native` is chosen but `/opt/scurebox/scurebox-ui` is missing, fall back to browser mode and log it. Always install `scurebox-io-safe.service` and run `mkdir -p /var/log/scure`.
   - native: install `scurebox-ui.service`; `disable --now` and delete `scurebox-kiosk.service` and `scurebox.service`; daemon-reload; enable io-safe and ui; restart io-safe (errors ignored) and ui; set kiosk off.
   - browser: install `scurebox.service`; disable and delete `scurebox-ui.service`; enable and restart io-safe and scurebox.
8. Plymouth. When `plymouth-set-default-theme` exists: copy `deploy/plymouth/scurebox/*` to `/usr/share/plymouth/themes/scurebox/`, then run `plymouth-set-default-theme -R scurebox` (fallback: without `-R`). cmdline is `/boot/firmware/cmdline.txt`, or `/boot/cmdline.txt`. Join it into one line. Remove these tokens: ` console=tty1`, ` quiet`, ` splash`, ` plymouth.ignore-serial-consoles`, ` logo.nologo`, ` vt.global_cursor_default=0`, ` loglevel=N`, ` consoleblank=N`. Then append ` console=tty3 quiet splash plymouth.ignore-serial-consoles logo.nologo vt.global_cursor_default=0 loglevel=0 consoleblank=0`. Running it twice gives the same line.
9. Native display ownership (native mode): `disable --now lightdm.service`, `mask getty@tty1.service`, `systemctl set-default multi-user.target`, `raspi-config nonint do_blanking 1`.
10. Browser kiosk (kiosk on and a uid-1000 user exists). Install `kiosk/labwc/rc.xml` to `/etc/scurebox/labwc/rc.xml` and create an empty `/etc/scurebox/labwc/autostart`. Install `chromium-policy.json` as `/etc/chromium/policies/managed/scurebox.json`. Render `scurebox-kiosk.service` with sed: `__KIOSK_USER__` = the user name, `__KIOSK_UID__` = `1000`, `__KIOSK_HOME__` = the home directory. Add the user to the groups video, input, render, tty (where they exist). Disable lightdm, run `set-default graphical.target`, enable and restart the kiosk, and turn blanking off.
11. NetBird (unless `--no-netbird`). Install `scurebox-netbird-enroll.service`. With `--netbird-key`, write it to `/etc/scurebox/netbird-setup-key` under umask 077. If that file or `/boot/firmware/netbird-setup-key` (or `/boot/netbird-setup-key`) is non-empty: enable the enroll service and run `netbird-enroll.sh` (with `set +e`). On exit 0, disable the service. Otherwise log "...retries every minute" and run `systemctl start --no-block` on it. Without a key and with netbird installed, log the `Management:` and `NetBird IP:` lines of `netbird status`.
12. Output watchdog. When `scurebox` and the unit file exist: install, enable and restart `scurebox-watchdog.service`, then log `systemctl is-active`.
13. When `/etc/NetworkManager` exists: install the wired conf and run `nmcli general reload conf`. Do not force a reconnect, so an install over SSH never cuts itself off.
14. PicoLog TC-08 driver. File `libusbtc08_2.0.151-1r6217_arm64.deb`, SHA-256 `26c85ce1365064164002ec6d0e5edcdd2b5a36cdde61c000c9bf55b27309ed27`, URL `https://labs.picotech.com/rc/picoscope7/debian/pool/main/libu/libusbtc08/<deb>`. Skip when `dpkg -s libusbtc08` succeeds, and skip on a non-arm64 system. Use `deploy/vendor/<deb>` when it is shipped; otherwise download it with curl (`--max-time 120`). Check the checksum with `sha256sum -c`, then `dpkg -i` and `ldconfig`. Every failure is logged and is not fatal. No apt source is added.
15. DVT bench: install, enable and restart `scurebox-dvt-bench.service` (a failure is logged), then log `http://localhost:3002/bench/status`.
16. Log "done (ui=<mode>)…". Reboot when `--reboot` was given. Exit 0.
**Configuration:** the command-line flags above. The uid-1000 user is the kiosk user.
**Acceptance criteria:**
- After a run in native mode: `/opt/scurebox/data` resolves to `/var/lib/scurebox`. `scurebox-ui`, `scurebox-io-safe`, `scurebox-watchdog` and `scurebox-dvt-bench` are enabled and active. `scurebox.service` and `scurebox-kiosk.service` do not exist. `getty@tty1` is masked.
- A second run appends nothing more to `config.txt` or `cmdline.txt`.
- An existing `/etc/scurebox/components.json` is untouched.
- Without internet the install still finishes with exit 0, and the TC-08 and NetBird steps only log.
- `http://localhost:3001/api/state` answers after the install.
**Tests:** manual on a unit (and indirectly through OPS-13, which checks `/api/system/version` and `/api/state` after the install).
**Reference (source):** `deploy/install.sh`, `deploy/networkmanager-scurebox.conf`, `src/SCureBox.Hardware/native/build-pio-helpers.sh`

---

### OPS-05 — Firmware systemd units (scurebox-ui.service / scurebox.service)
**Summary**
- **What it is for:** The system service files that start and supervise the sCure Box firmware on the Pi.
- **Problem it solves:** If the firmware crashes or freezes and nothing restarts it, the machine stops working until someone reboots it.
- **How we solve it:** Run the firmware as a system service that restarts it after a crash, and also when it stops sending 'I am alive' signals for 60 seconds. There are two versions: native screen or browser.

**Project / folder:** `deploy/scurebox-ui.service`, `deploy/scurebox.service`
**Goal:** Run the firmware as a supervised systemd service with sd_notify readiness and a watchdog. There are two variants: the native UI (one process that owns the display) or the headless API for the browser kiosk.
**Depends on:** OPS-06. Api (Microsoft.Extensions.Hosting.Systemd: notify and watchdog pings; ASPNETCORE_URLS/PORT), Native UI (DRM/KMS on tty1).
**Files to create:** the two unit files.
**Public contract:**
- `scurebox-ui.service`:
  - `[Unit]`: `After=network.target scurebox-io-safe.service systemd-logind.service plymouth-quit-wait.service`, `Wants=scurebox-io-safe.service`, `Conflicts=getty@tty1.service scurebox.service scurebox-kiosk.service`.
  - `[Service]`: `Type=notify`, `NotifyAccess=all`, `User=root`, `WorkingDirectory=/opt/scurebox`, `ExecStartPre=+-/usr/bin/chvt 1`, `ExecStart=/opt/scurebox/scurebox-ui`, `ExecStartPost=-/bin/sh -c 'sleep 4; /usr/bin/plymouth quit'`, `Restart=always`, `RestartSec=3`, `WatchdogSec=60`, `TTYPath=/dev/tty1`.
  - Environment: `ASPNETCORE_URLS=http://*:3001`, `PORT=3001`, `SCURE_DATA_DIR=/var/lib/scurebox`, `SCURE_COMPONENTS=/etc/scurebox/components.json`, `XDG_RUNTIME_DIR=/run/scurebox`, `DOTNET_gcServer=0`, `DOTNET_TieredPGO=1`.
  - Also `RuntimeDirectory=scurebox`, `LimitNOFILE=65536`, and `[Install] WantedBy=multi-user.target`.
- `scurebox.service`: the same, except `After=network.target scurebox-io-safe.service`, no Conflicts, no chvt, no plymouth, no TTYPath, no XDG_RUNTIME_DIR, no RuntimeDirectory, and `ExecStart=/opt/scurebox/scurebox`.
**Behaviour & rules:**
1. `http://*:3001` binds IPv4 and IPv6. A unit on a direct cable to a PC has only an IPv6 link-local address, so IPv6 must work.
2. The two units are mutually exclusive. `install.sh` removes the one that is not chosen.
3. Plymouth is told to quit 4 s after the native UI started, so the splash covers the gap until the first frame.
**Configuration:** the environment variables above. The full host variable set is owned by Api: PORT, SCURE_SIMULATE, SCURE_COMPONENTS, SCURE_DATA_DIR, DATABASE_URL, SCURE_UI_DIR, SCURE_NATIVE_DIR, SCURE_HEARTBEAT_FILE, SCURE_SUPERVISOR_URL, SCURE_SD_DIR, SCURE_SERIAL, SCURE_SIM_TC08/NFC/METER, SCURE_UI_* .
**Acceptance criteria:**
- `systemctl show scurebox-ui -p Type,WatchdogUSec` gives `notify`, `1min`.
- Killing the process restarts it within about 3 s.
- A firmware that stops pinging is restarted by systemd after 60 s.
- `curl -6 http://[::1]:3001/api/state` works.
**Tests:** `tests/SCureBox.Api.Tests/SystemdWatchdogTests.cs` (watchdog ping integration); manual check on the unit.
**Reference (source):** `deploy/scurebox-ui.service`, `deploy/scurebox.service`

---

### OPS-06 — Early-boot IO safe state (scurebox-io-safe + config.txt fragment)
**Summary**
- **What it is for:** Puts the UV LED switches and the LED relay into a safe 'off' state very early during boot.
- **Problem it solves:** Between power-on and the firmware start, pins could drift and turn on UV outputs by accident.
- **How we solve it:** Boot settings force those pins low from the start, and a small early-boot script sets the relay chip to safe levels. It never blocks the boot, even on errors.

**Project / folder:** `deploy/scurebox-io-safe.service`, `deploy/io-safe-boot.sh`, `deploy/config-txt-fragment.txt`
**Goal:** Make sure the UV SSRs, the wavelength routing line and the LED_SWITCH relay are at rest (off) from the firmware stage of boot until the .NET firmware takes over. This closes the window in which pull-ups could engage an output.
**Depends on:** Hardware (pin map: GPIO16 = 450 nm SSR, GPIO17 = routing / PCA9685 OE, GPIO20 = 405 nm SSR, TCA6424A at i2c-0 0x23, P01 = NFC_RESET, P05 = LED_SWITCH relay K4).
**Files to create:** the three files.
**Public contract:**
- `config-txt-fragment.txt`, inserted between markers `# >>> scurebox` and `# <<< scurebox`:
  - `dtparam=i2c_arm=on`, `dtparam=i2c_vc=on` (with a comment: i2c-1 on GPIO2/3 for U7/U10, i2c-0 on GPIO0/1 for PCA9685/TCA6424A/U6/U8)
  - `gpio=16,17,20=op,dl`
  - `dtparam=spi=off` (comment: the damper servo on GPIO8 must not be claimed by SPI)
  - `dtparam=audio=off`, `camera_auto_detect=0`, `disable_splash=1`
  - `gpio=27=ip,pn`
- `scurebox-io-safe.service`: `DefaultDependencies=no`, `After=sysinit.target`, `Before=scurebox.service`, `Type=oneshot`, `ExecStart=/bin/bash /opt/scurebox/deploy/io-safe-boot.sh`, `RemainAfterExit=yes`, `WantedBy=sysinit.target`. (The scurebox-ui unit orders itself after this unit.)
- `io-safe-boot.sh` (`set -u`):
  1. For p in 16 17 20, run `pinctrl set $p op dl`.
  2. When `i2cset` exists, run `i2cset -y 0 0x23 0x04 0x02` (port-0 output register: P01 = 1, P05 = 0), then `i2cset -y 0 0x23 0x0C 0xDD` (port-0 config: P01 and P05 as outputs).
  3. Ignore every error and always exit 0.
**Behaviour & rules:**
1. Write the output register before the config register, so the pins become outputs already at the safe levels.
2. The script must never fail the boot.
**Configuration:** none.
**Acceptance criteria:**
- After boot, `pinctrl get 16,17,20` reports output low.
- The TCA6424A register 0x0C reads 0xDD and register 0x04 has bit 5 clear and bit 1 set.
- The unit is `active (exited)`.
**Tests:** manual on the unit.
**Reference (source):** `deploy/scurebox-io-safe.service`, `deploy/io-safe-boot.sh`, `deploy/config-txt-fragment.txt`

---

### OPS-07 — Output watchdog and DVT bench services
**Summary**
- **What it is for:** Two helper services: an output watchdog that guards the heaters and UV LEDs, and the DVT test bench service.
- **Problem it solves:** If the firmware dies, heaters or UV LEDs could stay on; test runs also need a service that keeps running on its own.
- **How we solve it:** Both run separately from the firmware. The watchdog turns heaters and UV off if the firmware heartbeat stops for 20 seconds. The bench waits on port 3002 for test runs.

**Project / folder:** `deploy/scurebox-watchdog.service`, `deploy/scurebox-dvt-bench.service`
**Goal:** Two companion processes, started from the same `scurebox` executable, that must keep running when the firmware dies. The output watchdog cuts the heaters and the UV LEDs when the firmware heartbeat goes silent. The DVT bench runs catalog tests with the TC-08 and the StarBright meter on port 3002.
**Depends on:** OPS-04. Hardware (`OutputWatchdog`, `HeartbeatFile`), Dvt-Hdt (`DvtBenchHost`), Api (`CommandLine.TryRun`).
**Files to create:** the two unit files.
**Public contract:**
- Command-line modes of `scurebox`:
  - `--watchdog [--timeout <s>]` and `--watchdog --cut-now`
  - `--dvt-bench [--port 3002] [--firmware <url>]`
  - `--version`
  - `--make-update-package <folder> <privateKeyPem> <out.scu>` (exit 2 on wrong usage, exit 1 on a build failure)
- Heartbeat: the file named by `SCURE_HEARTBEAT_FILE` (default `/run/scurebox-heartbeat`; `off` disables it). It holds one line `"<Environment.TickCount64 ms> <pid>\n"` and is replaced atomically (written to `.tmp`, then renamed).
- `scurebox-watchdog.service`: `Documentation=file:///opt/scurebox/docs/02-hardware-map.md`, `After=scurebox-io-safe.service`, `Type=simple`, `User=root`, `ExecStart=/opt/scurebox/scurebox --watchdog --timeout 20`, `Environment=SCURE_COMPONENTS=/etc/scurebox/components.json`, `SCURE_HEARTBEAT_FILE=/run/scurebox-heartbeat`, `DOTNET_gcServer=0`, `Restart=always`, `RestartSec=2`, `Nice=-5`, `WantedBy=multi-user.target`.
- `scurebox-dvt-bench.service`: `Documentation=file:///opt/scurebox/docs/01-api-contract.md`, `After=network.target`, `Type=simple`, `User=root`, `WorkingDirectory=/opt/scurebox`, `ExecStart=/opt/scurebox/scurebox --dvt-bench --port 3002 --firmware http://127.0.0.1:3001`, `Environment=SCURE_COMPONENTS=/etc/scurebox/components.json`, `DOTNET_gcServer=0`, `Restart=always`, `RestartSec=3`, `WantedBy=multi-user.target`.
**Behaviour & rules:**
1. Neither unit has `BindsTo`, `PartOf` or `Requires` on a firmware unit. They must survive the firmware stopping or crashing. A comment in each unit says so.
2. The watchdog timeout is 20 s. Its behaviour is specified by the Hardware area.
3. The bench stays idle until the DVT web page starts a run.
**Configuration:** none beyond the unit environment.
**Acceptance criteria:**
- `systemctl stop scurebox-ui` leaves both services active.
- About 20 s after the firmware is killed with SIGKILL, the heater and UV outputs are off.
- `curl http://localhost:3002/bench/status` answers.
**Tests:** `tests/SCureBox.Api.Tests/WatchdogHeartbeatTests.cs`, `DvtBenchHostTests.cs`, `DvtHangApiTests.cs`; Domain `WatchdogMonitorTests.cs`; Hardware `SafetyCutTests.cs`.
**Reference (source):** `deploy/scurebox-watchdog.service`, `deploy/scurebox-dvt-bench.service`, `src/SCureBox.Api/Infrastructure/CommandLine.cs`, `src/SCureBox.Hardware/Safety/HeartbeatFile.cs`

---

### OPS-08 — NetBird remote access (enroll script + retry unit)
**Summary**
- **What it is for:** Sets up NetBird remote access so each machine can be reached from anywhere.
- **Problem it solves:** Without remote access, engineers cannot reach units in the field; a setup key left on the device would also be a security risk.
- **How we solve it:** A script installs NetBird, joins the unit with a one-time key under a name with its serial number, retries every minute until online, then deletes the key.

**Project / folder:** `deploy/netbird-enroll.sh`, `deploy/scurebox-netbird-enroll.service`
**Goal:** Install the NetBird WireGuard mesh client and enroll the unit with a one-off setup key, named after its eMMC serial, so that every unit can be reached from anywhere over SSH and the API. The script retries until the unit is online and deletes the key after use.
**Depends on:** OPS-04. Consumers: OPS-12 (key on the boot partition), OPS-13 (key from the PC).
**Files to create:** the script and the unit.
**Public contract:**
- `sudo deploy/netbird-enroll.sh [--key KEY] [--hostname NAME] [--management-url URL] [--install-only]`. Key sources, first found wins: `--key`, then `$NETBIRD_SETUP_KEY`, then `/etc/scurebox/netbird-setup-key`, then `/boot/firmware/netbird-setup-key` (or `/boot/netbird-setup-key`).
- Exit codes: 0 = enrolled, already connected, or nothing to do (no key). 1 = not root. 2 = bad option or bad key format. 75 = no network yet or enrollment failed (retry).
- Key format `^[A-Za-z0-9-]{8,128}$`. The key value is never committed or logged.
- Unit: `After=network-online.target`, `Wants=network-online.target`, `ConditionPathExists=|/etc/scurebox/netbird-setup-key`, `ConditionPathExists=|/boot/firmware/netbird-setup-key`, `Type=oneshot`, `ExecStart=/bin/bash /opt/scurebox/deploy/netbird-enroll.sh`, `Restart=on-failure`, `RestartSec=60`, `RestartPreventExitStatus=2`, journal output, `WantedBy=multi-user.target`.
**Behaviour & rules:**
1. If a non-empty key is on the boot partition (FAT, readable by everyone), move it at once with `install -m 600 -o root -g root` to `/etc/scurebox/netbird-setup-key` and delete the boot copy.
2. Read the key from the etc file when no other source gave one (whitespace stripped). An invalid format logs "unexpected format - refusing" and exits 2.
3. When `netbird` is not installed:
   - no key and not `--install-only`: log "remote access not configured" and exit 0.
   - otherwise: `curl -fsSL --max-time 30 https://pkgs.netbird.io/debian/public.key` (failure → exit 75); `gpg --dearmor` it to `/usr/share/keyrings/netbird-archive-keyring.gpg`; write `deb [signed-by=…] https://pkgs.netbird.io/debian stable main` to `/etc/apt/sources.list.d/netbird.list`; `apt-get update` limited to that list (`-o Dir::Etc::sourcelist=… -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0`); `apt-get install -y netbird` (failure → exit 75).
4. Run `netbird service install` and `systemctl enable --now netbird.service` (fallback `netbird service start`). Log `netbird version`. With `--install-only` and no key, exit 0.
5. When `netbird status` shows `^Management: Connected`: log the FQDN and IP, delete both key files, exit 0. When there is no key: exit 0.
6. Peer name: `$(hostname)-<serial>`. The serial is the first `/sys/block/mmcblk*/device` whose `type` is `MMC`, with spaces removed and a `0x` prefix stripped. Run `timeout 120 netbird up --setup-key KEY --hostname NAME [--management-url URL]` (failure → exit 75). Poll the status up to 30 times, 2 s apart. Log the FQDN and IP, delete both key files, exit 0.
7. The unit stays enrolled through its own WireGuard identity in `/var/lib/netbird`. A setup-key peer needs no user login and does not expire.
**Configuration:** setup key (secret), optional management URL.
**Acceptance criteria:**
- With a valid key and network: the unit shows as `<host>-<serial>` in the NetBird dashboard and no key file is left anywhere.
- Without network: exit 75, and the service retries every minute.
- With a malformed key: exit 2 and no retry.
- With no key: exit 0 and nothing installed.
**Tests:** manual. `build-image.py` and `install-scurebox.ps1` validate the key format with the same rule.
**Reference (source):** `deploy/netbird-enroll.sh`, `deploy/scurebox-netbird-enroll.service`

---

### OPS-09 — Branded boot splash and 10.1" display profile
**Summary**
- **What it is for:** The branded boot screen and the settings for the 10.1 inch touch display.
- **Problem it solves:** Without it, the unit shows Linux text at boot and the screen may run in the wrong direction, also on both slots of the factory image.
- **How we solve it:** A dark splash with the white sCure logo and a progress bar, plus a display profile for landscape 1920x1200. A tool adds this profile to OS images once, without changing anything else.

**Project / folder:** `deploy/plymouth/scurebox/`, `deploy/display-10inch.txt`, `deploy/image/patch-display.py`, `deploy/image/test_patch_display.py`
**Goal:** The unit boots to a dark screen with the white sCure "S" logo and a thin progress bar. No distro branding and no console text are shown. The Raspberry Pi Touch Display 2 (10.1", ILI79600, 1200x1920 native portrait, DSI-1) runs landscape at 1920x1200 on every image, including both slots of a factory A/B image.
**Depends on:** OPS-04 (installs the theme and edits cmdline/config), OPS-12, OPS-13.
**Files to create:**
- `display-10inch.txt`: a comment block (if touch feels mirrored, append `,invx`, `,invy` or `,swapxy` to the overlay line), then `dtoverlay=vc4-kms-v3d`, `max_framebuffers=2`, `disable_overscan=1`, `dtoverlay=vc4-kms-dsi-ili79600-10-1inch,rotation=90`.
- `plymouth/scurebox/scurebox.plymouth`: `[Plymouth Theme] Name=sCureBox`, `ModuleName=script`; `[script] ImageDir=/usr/share/plymouth/themes/scurebox`, `ScriptFile=/usr/share/plymouth/themes/scurebox/scurebox.script`.
- `plymouth/scurebox/scurebox.script`, `plymouth/scurebox/logo.png`.
- `image/patch-display.py`, `image/test_patch_display.py`.
**Public contract:**
- Plymouth script:
  - Background top and bottom colour (0.055, 0.078, 0.094) = `#0e1418`.
  - Logo scaled to window height / 3.2, centred, 30 px above the middle, z = 10.
  - Progress bar 22 % of the window width, 4 px high, 60 px under the logo. Background sprite opacity 0.18 (z 5). The foreground width is `bar.width * progress`, at least 1 px (z 6). It is driven by `Plymouth.SetBootProgressFunction`.
  - Messages: `Image.Text(text, 0.90,0.92,0.94,1, "Sans 16")`, centred 24 px under the bar.
  - Empty callbacks for quit, password and normal.
- `patch-display.py --image <.img|.img.xz> [--out F] [--in-place] [--probe] [--check] [--profile F]`:
  - `--probe` prints `factory` (GPT with partitions named boot_a and boot_b), `rpios` (MBR with a FAT partition of type 0x06/0x0B/0x0C/0x0E) or `unknown`. It reads only the first 2 MiB, and decompresses at most 8 MiB of a `.xz`.
  - `--check` reports which partitions lack the overlay and exits 1 when any does (it needs an uncompressed image).
  - The default output is `<stem>-display.img` next to the input. `.xz` input is decompressed to it (`.part` file, then rename).
  - The profile must contain the overlay name, or the tool exits.
- Requires Python 3.10+ and `pip install pyfatfs "setuptools<81"`.
**Behaviour & rules:**
1. FAT partitions:
   - MBR: types 0x06/0x0B/0x0C/0x0E whose boot sector has `55AA` and `FAT` at offset 0x36 or 0x52.
   - GPT: entries with the Basic Data or EFI System type GUID, or a name starting with "boot", and a FAT boot sector.
   - A GPT image is detected by MBR type 0xEE, then the "EFI PART" header at LBA 1.
2. For each partition with a `config.txt` (case-insensitive name): skip it when a stripped line starts with `dtoverlay=vc4-kms-dsi-ili79600-10-1inch` (a commented line does not count). Otherwise append `\n[all]\n<profile>\n`. pyfatfs cannot rewrite a file in place, so remove the file and write it again. Read it back and verify the overlay is there. Change nothing else.
3. `install.sh` applies the same rule on a running A/B unit (OPS-04 step 5).
**Configuration:** none.
**Acceptance criteria:**
- An A/B test image gets the profile in both boot_a and boot_b and nothing else changes.
- `--probe` tells factory from rpios even for a `.xz`.
- An MBR image is patched once; a second run changes nothing.
- An image that already enables the panel is left alone.
**Tests:** `python deploy/image/test_patch_display.py` (unittest on synthetic 16 MB FAT16 volumes): `test_ab_image_gets_the_display_in_both_slots_and_nothing_else_changes`, `test_probe_tells_the_factory_ab_image_from_raspberry_pi_os_even_when_compressed`, `test_mbr_raspberry_pi_os_image_is_patched_once`, `test_an_image_that_already_enables_the_panel_is_left_alone`, `test_commented_overlay_does_not_count`.
**Reference (source):** `deploy/plymouth/scurebox/*`, `deploy/display-10inch.txt`, `deploy/image/patch-display.py`, `deploy/image/test_patch_display.py`, `deploy/image/README.md`

---

### OPS-10 — Browser kiosk shell (Step A: labwc + Chromium)
**Summary**
- **What it is for:** The browser 'kiosk' mode that shows the web UI full screen in a locked Chromium browser.
- **Problem it solves:** In browser mode, operators could leave the app, or see an empty screen before the software is ready.
- **How we solve it:** Run Chromium locked to the app on a small window manager, show a branded loading page until the API answers, and block ways out of the app.

**Project / folder:** `deploy/kiosk/`
**Goal:** In `--ui browser` mode, run the React UI full-screen in a locked Chromium on a minimal Wayland compositor (labwc) on tty1. A branded loading page is shown until the API answers. The operator must not be able to leave the app.
**Depends on:** OPS-04, OPS-05 (`scurebox.service`), OPS-11.
**Files to create:** `scurebox-kiosk.service` (template), `scurebox-kiosk.sh`, `chromium-policy.json`, `labwc/rc.xml`, `loading.html`, `logo.png`.
**Public contract:**
- Unit template (placeholders `__KIOSK_USER__`, `__KIOSK_UID__`, `__KIOSK_HOME__`):
  - `After=scurebox.service systemd-logind.service systemd-user-sessions.service plymouth-quit-wait.service`, `Wants=scurebox.service`, `Conflicts=getty@tty1.service`, `StartLimitIntervalSec=0`.
  - `User` and `Group` = the kiosk user, `PAMName=login`, `TTYPath=/dev/tty1`, `TTYReset`, `TTYVHangup`, `TTYVTDisallocate=yes`, `StandardInput=tty-fail`, `UtmpIdentifier=tty1`, `UtmpMode=user`.
  - Environment: `XDG_SEAT=seat0`, `XDG_VTNR=1`, `XDG_SESSION_TYPE=wayland`, `XDG_RUNTIME_DIR=/run/user/<uid>`, `WLR_NO_HARDWARE_CURSORS=1`, `XCURSOR_SIZE=1`, `HOME=<home>`.
  - `ExecStartPre`: `-plymouth deactivate`; `+-/usr/bin/chvt 1`; remove `/run/user/<uid>/wayland-*` and `<home>/.config/chromium/Singleton*`.
  - `ExecStart=/usr/bin/labwc -C /etc/scurebox/labwc -s /opt/scurebox/deploy/kiosk/scurebox-kiosk.sh`, `ExecStartPost=-/bin/sh -c 'sleep 6; /usr/bin/plymouth quit'`.
  - `Restart=always`, `RestartSec=2`, `KillMode=control-group`, `TimeoutStopSec=8`, `WantedBy=graphical.target`.
- `scurebox-kiosk.sh`:
  - Browser: `chromium`, else `chromium-browser`.
  - Run `wlr-randr --output DSI-1 --on` when the tool exists.
  - Loop forever: start the browser with `--kiosk --noerrdialogs --disable-infobars --no-first-run --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-features=Translate,TranslateUI --disable-translate --lang=en-US --touch-events=enabled --enable-features=OverlayScrollbar --password-store=basic --check-for-update-interval=31536000 --disable-component-update --autoplay-policy=no-user-gesture-required --ozone-platform=wayland --default-background-color=0e1418ff --hide-scrollbars --start-maximized --app=file:///opt/scurebox/deploy/kiosk/loading.html`, then `sleep 2`.
- `chromium-policy.json`:
  - `URLBlocklist ["*"]`, `URLAllowlist ["localhost:3001","127.0.0.1:3001","file://*"]`
  - `DeveloperToolsAvailability 2`, `PrintingEnabled false`, `DownloadRestrictions 3`, `AllowFileSelectionDialogs false`, `ExtensionInstallBlocklist ["*"]`, `BrowserSignin 0`
  - `RestoreOnStartup 4`, `RestoreOnStartupURLs ["http://localhost:3001"]`
  - `TranslateEnabled false`, `PasswordManagerEnabled false`, `DefaultNotificationsSetting 2`
- `labwc/rc.xml`: decoration none, gap 0, adaptiveSync no, cornerRadius 0. Empty keybinds neutralise A-Tab, A-F4, W-Return, A-Escape and C-A-BackSpace. A windowRule for `*` toggles decorations off and maximizes. Touch naturalScroll is no.
- `loading.html`:
  - Background `#0e1418`, text `#e6ebf0`, `cursor:none`.
  - `logo.png` at 32vh, an animated bar 22vw wide and 4px high, a message line in `#8f9aa5`.
  - Script: poll `GET http://localhost:3001/api/state` (`cache:no-store`) once a second. On `r.ok`, run `location.replace("http://localhost:3001/")`. After more than 180 tries, show "Service required - the application did not start" and keep polling.
**Behaviour & rules:**
1. The compositor and browser restart forever: `StartLimitIntervalSec=0` plus the shell loop.
2. Stale Wayland sockets and Chromium Singleton locks are removed before each start.
3. Stopping must never hang: the whole cgroup is killed after 8 s.
**Configuration:** the kiosk user (uid 1000) is rendered by `install.sh`.
**Acceptance criteria:**
- After boot in browser mode the loading page appears, then the React UI.
- Navigating to another host is blocked.
- Alt+F4 and Alt+Tab do nothing.
- Killing chromium brings it back within about 2 s.
**Tests:** manual on the unit.
**Reference (source):** `deploy/kiosk/*`

---

### OPS-11 — Vendored React web UI (ui/dist, served as wwwroot)
**Summary**
- **What it is for:** The existing React web UI, shipped as a ready-made build and served by the machine.
- **Problem it solves:** Browser mode and tools need the web UI available without rebuilding or changing it.
- **How we solve it:** Keep the finished web build in the repo unchanged; the API server hosts it at the main address, and it uses the same API as the native screen.

**Project / folder:** `ui/dist/` (build output of the separate sCure-A React project), served by `src/SCureBox.Api`
**Goal:** Ship the existing React kiosk UI (Step A) unchanged, as a vendored build artifact. The API host serves it at `/` with an SPA fallback. The React UI drives the machine through the same `/api` contract as the native UI and the QA tools.
**Depends on:** OPS-01. Api (StaticUi mapping, CORS open, port 3001), Kiosk-Web (if that area rebuilds the React source).
**Files to create:** copy `ui/dist/` as built. Do not hand-edit it. The 15 files:
- `index.html`
- `assets/index-<hash>.js`, `assets/index-<hash>.css`
- `assets/geist-{cyrillic,latin,latin-ext}-wght-normal-<hash>.woff2`
- `favicon.svg`, `icons.svg`
- `config/errors.json`, `config/system.json`, `config/versions.json`
- `materials/st45.csv`
- `videos/usb-insert.mp4`, `videos/usb-org.mp4`
- `compliance/sbom.json` (CycloneDX 1.5, component `scure-a-temp` 0.0.0)
Total about 1.9 MB.
**Public contract:**
- How it is produced: `npm run build` (Vite) in the sibling `sCure-A` repo, then its `dist/` is copied to `ui/dist`. The build is sCure-A web version 0.9.4 (`ui/dist/config/versions.json` history[0] = 0.9.4, 2026-09-15). `VITE_HW_API_URL` is set at build time to `http://localhost:3001/api`. Asset paths are absolute (`/assets/...`), so the UI must be served from the domain root.
- `index.html`: `lang="en"` (must stay "en", or Chromium offers to translate from Hebrew), `dir="ltr"`, `translate="no"`, `<meta name="google" content="notranslate">`, viewport `user-scalable=no`, title `sCure`, `<div id="root">`.
- Packaging: `SCureBox.Api.csproj` copies `../../ui/dist/**` to `wwwroot/` (only when `ui/dist/index.html` exists). At runtime `SCURE_UI_DIR` (default `<app>/wwwroot`) is served with `UseStaticFiles(ServeUnknownFileTypes=true)`. The fallback returns `index.html` for any non-`/api` path. An unknown `/api/*` path returns `404 {ok:false,message:"Not found"}`. When there is no build, any non-API path returns `404 {ok:false,message:"UI not built"}`. `/config/*.json` is served from the UI dir, so the React UI reads its own errors.json, system.json and versions.json, not the firmware's `config/`.
- Client routes: `/`, `/alerts`, `/cure-history`, `/cure-process`, `/material-editor`, `/network`, `/settings`, `/dev`, `/dev/led-calibration`, `/dev/hdt-calibration`.
- Endpoints the bundle calls. The base is `http://localhost:3001/api`; materials, print-history and cure-history use a hard-coded `http://localhost:3001`.
  - State and system: `GET /api/state` (1 s poll, 3 s timeout), `GET /api/system/version`, `POST /api/system/datetime`, `/api/system/export-csv`, `/api/system/export-report`, `/api/system/export-logs`, `/api/system/reboot`, `GET /api/system/update/manifest`, `GET /api/system/update/package`, `POST /api/system/update`.
  - Cure: `POST /api/cure/heat?target=`, `/cure/dry?target=`, `/cure/cure-405?target=&intensity=`, `/cure/cure-450?target=&intensity=`, `/cure/uv-only?wavelength=&intensity=&vent=`, `/cure/cool?target=&mode=`, `/cure/nitrogen?on=`, `/cure/stop[?immediate=1]`.
  - Chamber and outputs: `/chamber/temperature?target=`, `/chamber/stop`, `/door/open`, `/door-abort/ack`, `/damper/open|close`, `/fans/<group>?speed=`.
  - Data: `GET /api/materials/presets`, `GET/POST /api/materials/user`, `GET/POST /api/print-history`, `GET /api/cure-history`, `POST /api/cure-runs/<id>/start|telemetry|phase|finish`, `/api/cure-runs/<id>/report`.
  - Developer: `/api/dev/log`, `/api/dev/led-calibration` (+ `/reset`), `/api/dev/led-power`, `/api/dev/picolog/status`, `/api/dev/hdt/status|start|abort|reset`, `/api/dev/hdt/report.csv`.
  - Also network and alerts pages (`/api/network/*`). See docs/03: "pre-flight = diagnostics/fan-test?fan=all (+ fans/override)".
- Polling only, no SSE or WebSocket: state 1 s, telemetry 5 s, alert summary 30 s, network status 3 s on the network page, HDT status 1 s. The UI is a fixed 800x480 canvas scaled to the window.
**Behaviour & rules:**
1. Treat `ui/dist` as a binary drop. To update it, rebuild sCure-A and replace the whole folder.
2. The API must listen on 3001 and keep CORS open, because the bundle hard-codes the absolute origin.
3. The program sequencing state machine of the React UI is in the bundle (it calls one endpoint per phase). The firmware additionally offers `/api/recipe/*` (Application-Process).
**Configuration:** `SCURE_UI_DIR`.
**Acceptance criteria:**
- `GET /` returns text/html with `<div id="root"`.
- `GET /settings` and `GET /cure/process/123` return the same index body.
- `GET /config/errors.json` is JSON with at least 46 records, each with the keys code, key, severity, category, layer, message, description, troubleshooting, supportUrl, and code 7001 present.
- `GET /api/no-such-route` returns 404 `{ok:false,"Not found"}`.
**Tests:** `tests/SCureBox.Api.Tests/StaticUiTests.cs` (skips when ui/dist is missing); QA category `static`.
**Reference (source):** `ui/dist/**`, `src/SCureBox.Api/SCureBox.Api.csproj`, `src/SCureBox.Api/Endpoints/StaticUi.cs`, `src/SCureBox.Api/Infrastructure/HostSettings.cs`, `docs/03-ui-and-qa.md`

---

### OPS-12 — OS image builder and CM5 eMMC flashing
**Summary**
- **What it is for:** A tool that builds the ready-to-flash sCure Box OS image and writes it to the CM5 memory.
- **Problem it solves:** Preparing a new unit by hand is slow, and building images normally needs Linux tools or admin rights on the PC.
- **How we solve it:** On Windows, take the official Raspberry Pi OS image, edit only its boot partition, add a first-boot script that installs everything, then flash it to the CM5 over USB.

**Project / folder:** `deploy/image/` (`build-image.py`, `flash-cm5.ps1`, `unxz.py`, `README.md`), `deploy/prepare-cm5.ps1`, `deploy/install-desktop-shortcut.ps1`
**Goal:** On a Windows PC, without WSL, Docker or admin rights for the build step, turn an official Raspberry Pi OS arm64 image into a ready-to-flash sCureBox image. Only the FAT boot partition is edited, and a first-boot script installs everything. The image is then written to the CM5 eMMC over rpiboot.
**Depends on:** OPS-03 (payload), OPS-04, OPS-08, OPS-09.
**Files to create:** the files listed above.
**Public contract:**
- `python deploy/image/build-image.py`. Options:
  - `--payload <tgz>` (default: newest `deploy/out/scurebox-*-linux-arm64.tar.gz`)
  - `--base-url` (default `https://downloads.raspberrypi.com/raspios_arm64_latest`) or `--base-image <.img|.img.xz>`
  - `--user` (default `scure`), `--password` (OPEN QUESTION / secret: the original uses a fixed well-known default; make it a required or configurable value), `--hostname scurebox`, `--timezone Asia/Jerusalem`, `--no-ssh`
  - `--out`, `--compress` (also writes `.img.xz`, preset 6), `--cache deploy/image/cache`
  - one of `--netbird-setup-key` / `--netbird-setup-key-file`
  - Output: `deploy/image/out/scurebox-<version>-cm5.img`. The version is token [1] of the payload name. Requires `pip install pyfatfs "setuptools<81" passlib`.
- `flash-cm5.ps1 -Image <img> [-DiskNumber N] [-ResumeFrom bytes] [-Yes] [-Elevated]`.
- `prepare-cm5.ps1 [-BaseImage] [-Payload] [-User scure] [-Password …] [-Hostname scurebox] [-Timezone Asia/Jerusalem] [-DiskNumber] [-SkipTests] [-PrepareOnly] [-Yes] [-NoSsh] [-NetbirdSetupKeyFile] [-Help]` runs publish.ps1, then build-image.py, then flash-cm5.ps1.
- `install-desktop-shortcut.ps1 [-Name "sCureBox CM5 Installer"]` creates a desktop .lnk to `powershell -NoProfile -ExecutionPolicy Bypass -File deploy\prepare-cm5.ps1` and creates `deploy\image\input`.
- `unxz.py <src.xz> <dst>` decompresses a file unchanged (8 MiB chunks).
**Behaviour & rules:**
1. Download: resolve the redirect with a HEAD request. Download into the cache, reusing a cached file (`.part`, then rename, with a progress line). Verify against `<url>.sha256`; skip the check if that file is unavailable; stop on a mismatch. Decompress with lzma.
2. The boot partition is the first MBR entry of type 0x0B, 0x0C or 0x0E; anything else stops the build ("not an MBR image" / "no FAT partition"). Stop when the payload plus 32 MiB is larger than the partition.
3. `config.txt`: append `config-txt-fragment.txt` and `display-10inch.txt` (CRLF normalised) when the first line of each is not already present. Replace `\ndtparam=spi=on` with `\n#dtparam=spi=on`.
4. `cmdline.txt`: remove ` splash` and ` quiet`, then append ` quiet loglevel=0 vt.global_cursor_default=0`. If `systemd.run=` is absent, also append ` systemd.run=/boot/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target`.
5. Write `firstrun.sh` (template placeholders `@USER@ @HASH@ @HOSTNAME@ @TIMEZONE@ @SSH@`) and `scurebox-payload.tar.gz`. Write `userconf.txt` as `user:<sha512-crypt hash>`; Trixie needs it, or it boots into the first-user wizard. Write an empty `ssh` file unless `--no-ssh`. Write `netbird-setup-key` when a key is given; its format is validated like OPS-08. The password hash is passlib `sha512_crypt` with 5000 rounds, falling back to `openssl passwd -6`. Existing files are removed and written again (pyfatfs limitation).
6. `firstrun.sh` (logs to `/var/log/scurebox-firstrun.log`, `set +e`):
   - Create the user: `/usr/lib/userconf-pi/userconf USER HASH`, or `useradd -m -u 1000` and add the user to adm, dialout, cdrom, audio, video, plugdev, games, users, input, render, netdev, gpio, i2c, spi, sudo.
   - Hostname, ssh, keymap `us` and timezone through `imager_custom`, or a manual fallback.
   - Extract the payload to `/opt/scurebox-stage`, chmod the scripts, run `bash <dir>/deploy/install.sh --no-reboot --payload <dir>`, then remove the stage and the payload.
   - Remove `firstrun.sh` and strip ` systemd.run.*` from cmdline.txt. The systemd.run success action reboots. First boot takes about 2 to 3 minutes.
7. `flash-cm5.ps1`:
   - Re-launch itself elevated through UAC when needed. The elevated run logs to `%TEMP%\flash-cm5.log` and the parent relays that log live.
   - When no gadget disk is present (USB bus, friendly name matching `mmcblk|nvme0n1|RPi|Raspberry`), look for the boot-ROM device `USB\VID_0A5C&PID_2712` (CM5) or `2711` (CM4). Run `C:\Program Files (x86)\Raspberry Pi\rpiboot.exe -d mass-storage-gadget64` and wait up to 60 s for the disk.
   - Exactly one candidate disk is required, unless `-DiskNumber` is given. The disk must be USB. The image must not be larger than the disk. Ask for the typed word `FLASH` unless `-Yes`.
   - `diskpart clean`. Raw write to `\\.\PhysicalDrive<N>` in 4 MiB chunks with WriteThrough, padded to 512 bytes. The first 4 MiB (the partition table) are written LAST, so Windows does not mount the boot partition during the write.
   - Up to 12 retries on transient errors, re-running rpiboot when the disk vanished. Progress lines `"  NN%  X MB  Y MB/s"` every 5 %.
   - Verify by SHA-256 of the first 64 MiB. Print "flash complete … Power-cycle the CM5 (remove the nRPIBOOT jumper)".
**Configuration:** user, password, hostname, timezone, SSH on/off, NetBird key file.
**Acceptance criteria:**
- The output `.img` boots on a CM5. The first boot creates the user and installs sCure, the unit reboots, and the native UI shows the Setup screen.
- `/var/log/scurebox-firstrun.log` ends with "firstrun done".
- No `netbird-setup-key` remains on the boot partition after enrollment.
- The flasher refuses a non-USB disk and refuses when 0 or 2 or more candidates are found.
**Tests:** manual (flash a unit). patch-display has unit tests (OPS-09).
**Reference (source):** `deploy/image/build-image.py`, `deploy/image/flash-cm5.ps1`, `deploy/image/unxz.py`, `deploy/image/README.md`, `deploy/prepare-cm5.ps1`, `deploy/install-desktop-shortcut.ps1`

---

### OPS-13 — Field installer (developer tool, portable bundle and GUI)
**Summary**
- **What it is for:** The field installer that puts a release on a unit from a PC.
- **Problem it solves:** Updating or flashing units needed developer skills, and there was no clear proof that the unit really runs the new version.
- **How we solve it:** One tool updates over SSH or flashes the memory, with a progress bar and a final health check. A password-protected portable bundle with a simple window lets non-developers use it on any Windows PC.

**Project / folder:** `deploy/install-scurebox.ps1`, `deploy/make-installer.ps1`, `deploy/installer/`
**Goal:** Take a release from a PC to a working unit, either by SSH update or by flashing the eMMC, with a progress bar and a final health check that only reports success when the unit runs the new version. A portable, password-gated bundle (CLI plus WPF GUI) lets non-developers do the same on any Windows 10/11 PC with no SDK or Python.
**Depends on:** OPS-03, OPS-04, OPS-08, OPS-09, OPS-12. Api (`/api/system/version`, `/api/state` with `hwSource` and `internetOk`). Application-Platform (device unlock challenge: Supervisor ChallengeSolve).
**Files to create:** `deploy/install-scurebox.ps1`; `deploy/make-installer.ps1`; `deploy/installer/Install-sCureBox.ps1`; `Install-sCureBox-GUI.ps1`; `Install-sCureBox.cmd`; `sCureBox Installer.cmd`; `README.txt`.
**Public contract:**
- `install-scurebox.ps1` parameters:
  - `-Mode auto|deploy|flash` (default auto), `-Target <host>` (named Target because `$Host` is read-only in PowerShell; default is a lab IP)
  - `-User scure`, `-Key`, `-Payload`, `-BaseImage`, `-DiskNumber`, `-Port 3001`
  - `-SkipBuild`, `-SkipTests`, `-NoKiosk`, `-Reboot`, `-Force`, `-InstallKey`
  - `-NetbirdSetupKey` | `-NetbirdSetupKeyFile`, `-NoNetbird`, `-Yes`, `-ImageOnly`
- `make-installer.ps1 [-Payload] [-SkipBuild] [-SkipTests] [-Password] [-NoPassword] [-OutDir]` writes `deploy/out/sCureBox-Installer-<v>/` and `.zip`. The bundle holds `Install-sCureBox.ps1`, `.cmd`, `-GUI.ps1`, `sCureBox Installer.cmd`, `README.txt`, `payload/scurebox-<v>-linux-arm64.tar.gz` and optionally `access.json`. The version comes from the tarball name.
- `access.json` = `{"salt": base64(16 random bytes), "hash": lowercase hex SHA-256(UTF-8 "<salt>:<password>")}`. The password itself is never stored.
- `Install-sCureBox.ps1` parameters:
  - `-Target`, `-User scure`, `-UnitPassword` (default = the fixed device default; secret, see OPEN QUESTION in OPS-12), `-Key`, `-Payload`, `-Port 3001`
  - `-InstallKey`, `-NoKiosk`, `-Reboot`, `-Force`
  - `-NetbirdSetupKey` | `-NetbirdSetupKeyFile`, `-NoNetbird`, `-NetbirdLogin`, `-NetbirdLoginOnly`, `-Password` (the installer gate)
  - Env `SCUREBOX_INSTALLER_PASSWORD` is an alternative to `-Password`.
  - Exit 1 on any failure (`[install] ERROR: …`).
- GUI env: `SCUREBOX_NO_ELEVATE` (skip the UAC request), `SCUREBOX_REPO` (source tree for the Flash tab). Parameters `-BundleDir`, `-RepoDir`, `-ShowNextSteps`.
- `.cmd` launchers: `Install-sCureBox.cmd` runs the CLI with `-ExecutionPolicy Bypass` and pauses. `sCureBox Installer.cmd` starts the GUI with a hidden window.
**Behaviour & rules:**
1. Phases use weighted progress (`Write-Progress`): Preflight 5, Build 35, Version check 5, Deploy 45 or Build image 25 + Flash 25, Verify 10.
2. Auto mode picks deploy when TCP 22 or `/api/system/version` answers on the target. Otherwise it picks flash when a CM5 gadget disk is present. Otherwise it fails.
3. Version check: when the unit already reports the same `appVersion` and `-Force` is not given, warn and stop with no changes.
4. Deploy:
   - Optionally append `~/.ssh/id_ed25519.pub` (or `id_rsa.pub`; the bundle generates an ed25519 key if none exists) to the unit's `~/.ssh/authorized_keys`.
   - scp the tarball to `/tmp`. Remotely: extract, `chmod +x deploy/install.sh`, run `sudo ./deploy/install.sh <opts>`. Opts: `--no-kiosk`, `--reboot`, `--no-netbird` or `--netbird-key K`.
   - The developer tool tries `sudo -n` first and falls back to interactive `sudo`.
   - The bundle sends the device password over stdin to `sudo -S -p ''` and strips non-printable characters on the unit, because Windows PowerShell adds a CR or BOM. The remote command contains no double quotes (PowerShell 5.1 does not escape them for ssh.exe).
   - The bundle feeds ssh and scp the password through a temporary `SSH_ASKPASS` .cmd file (`SSH_ASKPASS_REQUIRE=force`, `DISPLAY` set), deleted at the end. ssh options: `StrictHostKeyChecking=no`, `UserKnownHostsFile=NUL`, `LogLevel=ERROR`, `ConnectTimeout=10`. Units are reflashed often and get new host keys.
   - The bundle reads `deploy/install.sh` out of the tarball and passes NetBird flags only when it contains `netbird-key` (releases from 1.0.18 on).
   - With `-Reboot`, ssh exit 255 is treated as the expected reboot.
   - The boot config changed when the output has "scurebox fragment|Touch Display 2 profile|Plymouth theme". If it changed and there was no reboot, advise a reboot.
5. Verify: poll `/api/system/version` every 4 s for up to 180 s until `appVersion` equals the new version and `/api/state` answers. Then print version, commit, os, kernel and eMMC. Read `netbird status` over SSH and print Connected, IP and FQDN.
6. NetBird web login (`-NetbirdLogin`, no key): a base64-encoded bash script is piped over SSH and run with sudo. It:
   - sets the unit clock from the PC epoch when it is off by more than 300 s;
   - installs NetBird with `netbird-enroll.sh --install-only` when it is missing (exit 75 = no internet);
   - exits 0 with `ALREADY_CONNECTED` when connected;
   - checks `curl https://api.netbird.io` (exit 75 when unreachable);
   - prints `LOGIN_START`, then runs `timeout 600 netbird up --no-browser --hostname <host>-<serial>`;
   - prints `CONNECTED` on success, or exits 4.
   The PC opens in the browser the first https URL that appears after `LOGIN_START` and is not a `[netbird]` line.
7. Flash mode:
   - `-ImageOnly`: write the image unchanged; an `.xz` is decompressed with `unxz.py` into `deploy\image\out`, and that copy is deleted after a successful flash.
   - Otherwise `patch-display.py --probe` decides. `factory`: run patch-display to `<stem>-display.img` and flash it as it is. `rpios`: build-image.py, with the NetBird key passed through a temporary file that is deleted afterwards. `unknown`: refuse before the eMMC is touched.
   - After the flash, print the next steps: remove the jumper, connect, power on.
8. GUI (WPF, dark tokens: bg `#0a0a0a`, card `#111`, accent `#0ea5e9`, window 760x980):
   - Asks for admin once at start; declining keeps the tool usable without Flash.
   - Three mode pills: Update unit / Flash new unit / Unlock code. One Install / Go button, a progress bar, a status line and a coloured log.
   - Child processes are run through a compiled C# `ProcessPump`: the output lines go into a ConcurrentQueue that a 150 ms DispatcherTimer drains (PowerShell script blocks cannot run on thread-pool threads).
   - Update tab: target address, "Enroll in NetBird" checkbox plus key file or pasted key, Reboot checkbox. With NetBird checked and no key, it uses `-NetbirdLogin`.
   - NetBird key auto-discovery, first usable file with at least 20 characters: `<bundle>\netbird-setup-key.txt`, then `%USERPROFILE%\.scurebox\netbird-setup-key.txt`, then `%TEMP%\netbird-setup-key.txt`. A pasted key is saved to the user store.
   - Flash tab:
     - Enabled only when `deploy\install-scurebox.ps1` and Python are present (that is, run from the repo or with `-RepoDir`).
     - Pre-start checklist: jumper, USB-C, network with internet, power, and a "red LED dim" confirmation button that must be pressed before flashing.
     - A background runspace polls every 2.5 s:
       - the USB state (ready = gadget disk, boot = boot-ROM device, none, error);
       - after a flash: whether the USB disk or ROM is still present;
       - `http://scurebox.local:3001/api/state` and the AAAA fe80 address with each interface zone, for `hwSource`, `internetOk` and `/api/system/version`.
     - It drives a "Next steps" tracker: jumper removed; machine IO board seen (`hwSource == "io_controller"`); API up; internet; NetBird Connect button.
     - The Flash tab always calls `install-scurebox.ps1 -Mode flash -BaseImage <img> -ImageOnly -Yes` (since 1.0.96).
   - Unlock tab: a 4-digit challenge is turned into a 6-digit code. The code is HMAC-SHA256 over UTF-8 `"<context>|<challenge>|<step>"` with context "" and step 0, followed by RFC 4226 dynamic truncation mod 10^6, printed with 6 digits. The 32-byte HMAC secret is embedded in the GUI as base64 and must equal the device's Supervisor secret. SECRET: do not copy it; supply it from secure configuration. The installer password gate also protects this tab.
   - The gate password is checked against `access.json`: next to the GUI, or else `%LOCALAPPDATA%\Programs\sCureBox Installer\access.json`. It is passed to the CLI through `SCUREBOX_INSTALLER_PASSWORD`, never on the command line. The CLI allows 3 tries.
**Configuration:** `access.json`; NetBird key files; `SCUREBOX_*` env vars above.
**Acceptance criteria:**
- Updating a unit already on the version prints "already runs … -Force" and changes nothing.
- A successful update prints `SUCCESS - sCureBox <v> is running on <target> and answering /api/state`.
- A wrong gate password three times exits 1.
- The bundle zip contains no NetBird key and no plain password.
- The Flash tab refuses an image that is neither rpios nor factory.
**Tests:** manual. No automated tests exist for these scripts.
**Reference (source):** `deploy/install-scurebox.ps1`, `deploy/make-installer.ps1`, `deploy/installer/*`

---

### OPS-14 — Windows PC demo installer (simulator)
**Summary**
- **What it is for:** A Windows setup program for a demo version of the sCure Box with simulated hardware.
- **Problem it solves:** Demos and training need the machine's screen without a real machine, on ordinary PCs without admin rights.
- **How we solve it:** One setup .exe installs the native UI with the simulator. It needs no .NET install and no admin rights.

**Project / folder:** `deploy/make-demo-installer.ps1`; consumes `src/SCureBox.Ui` (`DemoWinExe`, `Hosting/DemoMode.cs`)
**Goal:** A single setup `.exe` that installs the native UI with the simulated firmware on any Windows 10/11 x64 PC, with no .NET and no admin rights. It is used for demos and training.
**Depends on:** OPS-02. Native UI (DemoMode marker, `DemoWinExe` property in `SCureBox.Ui.csproj`).
**Files to create:** `deploy/make-demo-installer.ps1`.
**Public contract:**
- `make-demo-installer.ps1 [-SkipTests]` writes `deploy/out/sCureBox-Demo-Setup-<version>.exe`. The work folder is `deploy/out/demo-installer-<version>/` and contains `app/`, `payload.zip`, `install.ps1` and `demo.sed`.
- Publish: `dotnet publish src/SCureBox.Ui/SCureBox.Ui.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -p:DebugType=none -p:UseAppHost=true -p:DemoWinExe=true`. `DemoWinExe=true` switches `OutputType` to WinExe, so no console window opens.
- Marker `app/demo.mode` (any text) plus `app/VERSION`. With the marker present, `DemoMode` sets each of these variables only when it is not already set:
  - `SCURE_SIMULATE=1`, `SCURE_UI_WINDOW=1`, `SCURE_UI_SIZE=1600x1000`
  - `PORT=3011`, `ASPNETCORE_URLS=http://127.0.0.1:3011`
  - `SCURE_DATA_DIR=%LOCALAPPDATA%\sCureBox Demo\data`
**Behaviour & rules:**
1. Runs `dotnet test SCureBox.sln` unless `-SkipTests` is given.
2. `install.ps1` (UTF-8 with BOM) runs after IExpress has unpacked the package. It:
   - kills only a running `scurebox-ui` whose path is the install folder;
   - replaces `%LOCALAPPDATA%\Programs\sCureBox Demo` and extracts `payload.zip` into it;
   - writes `uninstall.ps1`;
   - creates a Desktop shortcut and a Start Menu folder with the app shortcut (description "sCureBox - PC demo (simulator)") and "Uninstall sCureBox Demo";
   - registers `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\sCureBox Demo` with DisplayName, DisplayVersion (from VERSION), Publisher "sCure", InstallLocation, UninstallString and NoModify = 1;
   - starts the app. Any error is shown in a MessageBox and exits 1.
3. `uninstall.ps1 [-Data keep|delete|ask]`: kills the app, removes the shortcuts and the registry key, asks before deleting `%LOCALAPPDATA%\sCureBox Demo` (with `ask`), and deletes the install folder from a detached process after 2 s.
4. IExpress SED: `PackagePurpose=InstallApp`, hidden windows, `UseLongFileName=1`, `RebootMode=N`, `FriendlyName=sCureBox Demo Setup`, `AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File install.ps1`, files `payload.zip` and `install.ps1`. Run `iexpress.exe /N /Q /M demo.sed`. It returns at once, so wait up to 300 s until the exe is larger than 1 MB and its size has not changed for 3 s.
**Configuration:** none.
**Acceptance criteria:**
- Running the exe as a normal user installs the demo and starts it.
- The window shows the simulator at 1600x1000.
- `http://127.0.0.1:3011/api/state` shows `hwSource: "simulation"`.
- Settings > Apps lists "sCureBox Demo".
- The uninstaller removes everything except the data, unless asked to delete it.
**Tests:** `tests/SCureBox.Ui.Tests/DemoModeTests.cs` (marker → environment); manual install.
**Reference (source):** `deploy/make-demo-installer.ps1`, `src/SCureBox.Ui/SCureBox.Ui.csproj`, `src/SCureBox.Ui/Hosting/DemoMode.cs`

---

### OPS-15 — Origin application package (.tgz for the factory A/B image)
**Summary**
- **What it is for:** Packages sCure Box as an application for the Origin factory image.
- **Problem it solves:** The factory image has a read-only system and its own supervisor, so the normal installer cannot be used there.
- **How we solve it:** Build a .tgz app package that the Origin supervisor installs; the firmware with its screen and the output watchdog run as managed services, with saved data in a separate folder.

**Project / folder:** `deploy/package-origin-app.ps1` (canonical), `deploy/package-origin-app.sh`, `deploy/origin-app/`
**Goal:** Package sCureBox as an application for the Origin supervisor on the factory image (read-only root, .NET 10 runtime installed, labwc session). The firmware with the native UI and the output watchdog become supervisor-managed services, with persistent state in `/opt/data`.
**Depends on:** OPS-02, OPS-07. Hardware (`native/linux-arm64`: prebuilt `pio_rgb`, `pio_servo`, `lib/libusbtc08.so`). Application-Platform (`SCURE_SUPERVISOR_URL`, default `http://127.0.0.1:8080`). Dvt-Hdt (DVT runner from the sibling sCure-A repo).
**Files to create:** `deploy/package-origin-app.ps1`, `deploy/package-origin-app.sh`, `deploy/origin-app/run.sh`, `run-watchdog.sh`, `run-dvt-runner.sh`.
**Public contract:**
- Output `deploy/out/scurebox-<v>-origin-app.tgz`, staged in `origin-app-<v>/`. Archive root:
  - `manifest.json`
  - `SHA256SUMS`: one `"<sha256 lowercase>  <relative/path>"` line per file of `main/` plus `manifest.json`, sorted by path, LF line endings
  - `main/`
- `main/` holds:
  - the framework-dependent publish of SCureBox.Api and SCureBox.Ui (`-c Release -r linux-arm64 --self-contained false -p:PublishSingleFile=false -p:DebugType=none -p:UseAppHost=false -p:RollForward=Major`)
  - `keys/scure-update.pub`, `VERSION`, `GITINFO`
  - `native/linux-arm64/*` (when `pio_rgb` exists)
  - `dvt-runner/runner/dvt-runner.cjs`, `dvt-runner/web/{dvt-tool.html,dvt-catalog.js,dvt-criteria.js,dvt-auto.js}`, `dvt-runner/VERSION`, all copied from `../sCure-A/DVT/`. If sCure-A is missing, a warning is printed and the runner is left out.
  - `run.sh`, `run-watchdog.sh`, `run-dvt-runner.sh`, with LF line endings and no BOM.
- `manifest.json` (ps1):
```
{"id":"scurebox","name":"sCureBox","version":"<v>","services":[
 {"name":"scurebox-main","type":"simple","user":"root","exec":["/bin/sh","main/run.sh"]},
 {"name":"scurebox-watchdog","type":"simple","user":"root","exec":["/bin/sh","main/run-watchdog.sh"]},
 {"name":"scurebox-dvt-runner","type":"simple","exec":["/bin/sh","main/run-dvt-runner.sh"]}]}
```
  The `.sh` variant produces only main and watchdog, without `user` keys, and leaves out the native helpers and the runner. OPEN QUESTION: whether to keep the `.sh` variant in sync with the ps1. The ps1 is the one in use.
- Install on a device: `scp <tgz> origin@<device>:/tmp/`, then `POST http://<device>:8080/api/application/install` with body `{"path":"/tmp/<tgz>"}`. The supervisor checks SHA256SUMS. Installing does not restart the app; the operator restarts it through the firmware's `/api/system/reboot`.
- `SCURE_STATE_DIR` (default `/opt/data/scurebox`) is the persistent root.
**Behaviour & rules:**
1. Services run through `/bin/sh`, because tar on Windows cannot set the executable bit.
2. Main and watchdog run as root. The Origin image keeps `/dev/gpiochip*`, `/dev/gpiomem*` and `/dev/pio0` root-only. Running as `origin` made the firmware fall back to simulation and stopped the watchdog from cutting the SSRs.
3. `run.sh`:
   - cd to its own directory;
   - `mkdir $DATA/data`; seed `$DATA/components.json` once from `config/components.json` (never replaced by an update);
   - copy `native/linux-arm64/pio_*` to `$DATA/native/`, `chmod 755`, export `SCURE_NATIVE_DIR`;
   - prepend `native/linux-arm64/lib` to `LD_LIBRARY_PATH`;
   - export `SCURE_DATA_DIR=$DATA/data`, `SCURE_COMPONENTS`, `ASPNETCORE_URLS` (default `http://*:3001`), `PORT=3001`, `DOTNET_gcServer=0`, `DOTNET_TieredPGO=1`, `DOTNET_CLI_TELEMETRY_OPTOUT=1`, `SCURE_HEARTBEAT_FILE=/dev/shm/scurebox-heartbeat`, `SCURE_UI_WINDOW=1`, `SCURE_UI_FULLSCREEN=1`, `SCURE_UI_HIDE_CURSOR=1`;
   - source `$DATA/ui.env` when it exists (per-machine overrides), then `SCURE_UI_RENDER` defaults to `gles`;
   - set `WAYLAND_DISPLAY=wayland-0` when `${XDG_RUNTIME_DIR:-/run/user/0}/wayland-0` is a socket; set `DISPLAY` from the first `/tmp/.X11-unix/X<n>`;
   - echo the display env, set `DOTNET_ROLL_FORWARD=Major`, find dotnet on PATH or `/usr/share/dotnet/dotnet`, set `DOTNET_ROOT` from its resolved directory;
   - `exec dotnet ./scurebox-ui.dll "$@"`.
4. `run-watchdog.sh`: the same data and components seeding, `SCURE_HEARTBEAT_FILE=/dev/shm/scurebox-heartbeat` (the `origin` user cannot write `/run`; tmpfs, so no eMMC wear), `DOTNET_gcServer=0`, then `exec dotnet ./scurebox.dll --watchdog --timeout 20`.
5. `run-dvt-runner.sh`: config `$DATA/dvt-runner.json` (mode 600, holds portalUrl, key, machine, unit, machineApi, resultsFile …; secret, per machine). If the runner file, `node` or the config is missing, print "not configured … idle" and `exec sleep infinity`, so the supervisor does not restart it in a loop. Otherwise `exec node dvt-runner/runner/dvt-runner.cjs <cfg>`.
6. Unless `-SkipTests` is given, run `dotnet test` first. Write GITINFO. Create the tar with `%SystemRoot%\System32\tar.exe -czf <tgz> -C <stage> manifest.json SHA256SUMS main`.
**Configuration:** `/opt/data/scurebox/ui.env` (e.g. `SCURE_UI_RENDER=software|gles`); `/opt/data/scurebox/dvt-runner.json`.
**Acceptance criteria:**
- `sha256sum --strict -c SHA256SUMS` passes inside the extracted package.
- The supervisor accepts the install. After a restart the native UI shows full-screen, `/api/state` reports `hwSource: "io_controller"` (not simulation), and the watchdog is running.
- `components.json` and the data survive a version update.
**Tests:** manual on an Origin unit. The `.sh` variant self-checks SHA256SUMS after packing.
**Reference (source):** `deploy/package-origin-app.ps1`, `deploy/package-origin-app.sh`, `deploy/origin-app/*`, `src/SCureBox.Hardware/native/linux-arm64/README.txt`

---

### OPS-16 — sCure Org Key phone PWA
**Summary**
- **What it is for:** A small phone web app that saves the Origin organization ID to a USB drive.
- **Problem it solves:** The sCure Box links to an organization by reading a CSV file from USB, and users need an easy way to create that file.
- **How we solve it:** A phone app, which also works offline, writes the organization ID as the right CSV file to USB. No data leaves the phone.

**Project / folder:** `pwa/`
**Goal:** A static phone web app (installable PWA that also works offline) that writes the Origin organization ID to a USB drive as the CSV the sCure Box reads (Settings > Organization > Link Organization). No data leaves the phone.
**Depends on:** Native UI (the machine lists `*.csv` on USB and takes the first UUID; the pattern matches SetupViewModel.OrganizationIdPattern).
**Files to create:** `pwa/index.html`, `app.js`, `styles.css`, `sw.js`, `manifest.webmanifest`, `icons/{icon.svg,icon-192.png,icon-512.png,icon-maskable-512.png,apple-touch-icon.png}`, `tests/test_pwa.py`, `README.md`.
**Public contract:**
- `app.js` exports (CommonJS when `module` exists): `extractOrgId(text)`, `buildCsv(orgId,name)`, `fileNameFor(name)`, `csvCell(v)`, `saveCsv(fileName,text,env)`.
- UUID regex `/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i`. The first match is lower-cased.
- CSV = `"organization_id,organization_name\r\n" + id + "," + csvCell(name) + "\r\n"`. `csvCell` replaces line breaks with a space, trims, and quotes the value (doubling `"`) when it contains `,` or `"`.
- File name: `scure-organization.csv`, or `scure-organization-<slug>.csv`. The slug is the name lower-cased, NFKD-normalised, with non-`[a-z0-9]` runs turned into `-`, trimmed and cut to 32 characters.
- Manifest: name "sCure Org Key", short_name "Org Key", `id`, `start_url` and `scope` `./`, display standalone, orientation portrait, background and theme `#0a0a0c`. Icons 192 and 512 "any", maskable-512 "maskable", svg "any".
- Service worker: cache `scure-org-key-v1` holding the shell (`./`, index.html, styles.css, app.js, manifest, icons). Install runs `skipWaiting`. Activate deletes other caches and runs `clients.claim`. Fetch (same-origin GET only) is cache-first, then network, storing OK responses. A failed navigation falls back to `index.html`.
- localStorage key `scure-org-key.recent`: at most 5 `{id,name}` entries. Every read and write is wrapped in try/catch.
**Behaviour & rules:**
1. Step 1: ID input. Pasting a whole message keeps only the ID. A Paste button uses `navigator.clipboard.readText`; when that is not allowed, show "long-press the field". A "From a file" input (`.csv,.txt,.json,text/*`) reads the ID from the file and clears the field when none is found. Optional organization name, at most 80 characters. Status texts: "Valid organization ID" and "This is not an organization ID yet (8-4-4-4-12 letters and digits)".
2. Step 2: Save stays disabled until the ID is valid. The save order is:
   - `showSaveFilePicker` (types limited to text/csv `.csv`; AbortError = cancelled);
   - else `navigator.share({files})` when `canShare` (AbortError = cancelled);
   - else an anchor download. The help `<details>` then opens and the message names Downloads.
   A successful save is remembered in the Recent list. Tapping a Recent entry restores the ID and the name.
3. Step 3: static instructions for the box. An install button appears on `beforeinstallprompt`. An iOS "Share > Add to Home Screen" hint is shown when the app is not standalone.
4. Bump `CACHE` whenever any file changes. All paths are relative, so the app works from a sub-path (e.g. GitHub Pages). HTTPS is required to install it and to save files.
**Configuration:** none.
**Acceptance criteria:** the checks in the Tests line pass, including:
- the header row holds no UUID;
- a name with a comma and quotes is quoted correctly: `"Acme, ""Dental"" Lab"`;
- the app opens offline after the first load.
**Tests:** `python pwa/tests/test_pwa.py [--shots DIR]` (Playwright + Chrome, a phone-sized viewport, serves pwa/ on a random 127.0.0.1 port). It checks:
- the title, Save disabled until there is an ID, the manifest and icons;
- refusal of bad IDs, an upper-case ID accepted, paste and file extraction;
- the CSV header and row, the picker filename and filter;
- the Recent list;
- cancelling the picker or the share sheet saves nothing;
- the share file name and type, the download name and content, and the help opening;
- offline opening;
- no script errors.
Local serve: `python -m http.server 8080 --directory pwa`.
**Reference (source):** `pwa/*`

---

### OPS-17 — QA tool (shared test table, headless runner, browser tool, run-all)
**Summary**
- **What it is for:** The QA tool: one shared table of API tests that can run automatically or in a browser.
- **Problem it solves:** Without shared tests, there is no quick way to prove that the simulator or a real machine follows the API contract before a release.
- **How we solve it:** About 125 tests in one table, run by a command-line runner or a browser page against any machine; one script runs all builds and tests and gives a single PASS or FAIL.

**Project / folder:** `qa/`
**Goal:** One table of API contract tests (about 125 rows in 15 categories) that runs headless in CI-like runs (`run-qa.mjs`) and interactively in a browser (`qa-tool.html`) against any live firmware: simulation on the PC or the real machine. `run-all.ps1` chains build, unit and integration tests, a simulated API server, the headless QA and the native UI QA into one PASS/FAIL result.
**Depends on:** OPS-01. Api (every endpoint under test), Native UI (`/api/ui/route|navigate|screenshot|tap|swipe`).
**Files to create:** `qa/qa-tests.js`, `qa/run-qa.mjs`, `qa/qa-tool.html`, `qa/run-all.ps1`, `qa/README.md`. `qa/last-qa-report.json` is generated by `run-all.ps1`.
**Public contract:**
- `qa-tests.js`: a plain script with no dependencies. It defines `globalThis.SCURE_QA = {CATEGORIES, CHECKS, runTest, STATE_KEYS}` and `globalThis.SCURE_QA_TESTS = CATEGORIES`.
- Record: `{id, name, desc, endpoint?, method?, body?, expect?|expectArray?|check?, code?, url?, timeout?, reason?, route?}`.
  - `expect:'ok'` → `ok === true`.
  - `expect:'<field>'` → the field exists.
  - `expectArray` → the body is an array.
  - `check:'<name>'` → `CHECKS[name](ctx,test,res)` returns `{status:'pass'|'fail'|'warn'|'skip', msg}`.
  - `url` → a static asset fetched without the `/api` prefix.
  - No endpoint and no url → the check makes its own calls.
- `runTest` returns `{status,msg,ms}`. A timeout gives `fail 'timeout'`. `ctx = {apiUrl, fetch, timeoutMs:10000}`. Run ids `qa-test-run` and `qa-recipe-run`.
- `STATE_KEYS` (all must be in `/api/state`): chamberTemp, targetTemp, internetOk, offlineMode, doorClosed, doorAborted, isHeating, isCooling, coolingMode, uvOn, uvIntensity, uvWavelength, uvOutputs, ventOn, damperOpen, damperDriver, fans, fanRpm, fanRpmEach, fanOverride, stripMode, uiAlerts, ledTemps, uvSensors, nitrogenActive, n2Pressure, n2LinePressure, bofaOn, bofaConnected, bofaDutyPercent, bofaPowered, bofaDetected, atTemp, heaterPwm, heaterOut, coolingRate, coolingFanPwm, faults, sensors, fanHealth, ledHealth, ledChecksEnabled, alerts, alertDetails, hwSource, counters, cloudSync, nfcEnabled, nfcReader, recipe. Fans: FAN_HEATER, FAN_DOOR, FAN_RIGHT, FAN_LEFT, FAN_BACK, FAN_COOLING.
- Categories, in order: connectivity, state, cure, chamber, hardware, diagnostics, data, system, network, nfc, dev, dvt, recipe, static, performance, native_ui. The README lists the categories without dvt and native_ui. The table is the source of truth.
- `node qa/run-qa.mjs [--api http://localhost:3001] [--category <id>] [--json out.json] [--quiet]`.
  - Node 18 or newer, no dependencies. It loads `qa-tests.js` with `createRequire`.
  - Connectivity gate: `GET /api/state` with a 5 s timeout. If it fails, exit 1.
  - Tests run in order with a 50 ms pause between them.
  - Coloured output on a TTY. Exit 1 when any test fails (warn and skip do not count). Exit 2 for bad arguments.
  - The JSON report is `{api, date, seconds, summary:{pass,fail,warn,skip}, results:[{category,id,name,status,msg,ms}]}`.
- `qa-tool.html` (title "sCureBox QA Tool"):
  - Loads `qa-tests.js` from the same folder and shows a banner when it cannot.
  - API URL input (default `http://localhost:3001`, remembered in localStorage `scure-qa-api`); Connect shows the server version and hwSource.
  - Run All, Stop, Run per category and per row. Tiles for Total, Pass, Fail, Warn, Skip, plus a progress bar and a log.
  - Export report opens a textarea modal with Copy and Download.
  - Works from `file://`, because the API's CORS is open.
- `run-all.ps1 [-Port 3111] [-SkipBuild] [-SkipTests] [-HangTimeout '3m'] [-ExcludeTests <names>] [-SkipUi]`.
**Behaviour & rules:**
1. `run-all.ps1` steps:
   - `dotnet build SCureBox.sln -nologo -v q`. A failure stops the run with exit 1.
   - `dotnet test` for Domain, Hardware, Application and Api tests (`--no-build --blame-hang --blame-hang-timeout <HangTimeout>`). The Ui.Tests project is not in this list.
   - Start `src/SCureBox.Api/bin/Debug/net10.0/scurebox.dll` with dotnet. Env: `SCURE_SIMULATE=1`, `SCURE_SIM_TC08=1`, `SCURE_DATA_DIR=<temp scurebox-qa-<guid>>`, `SCURE_UI_DIR=<repo>/ui/dist`, `PORT=<Port>`, `ASPNETCORE_URLS=''`, `DOTNET_ROOT`. stdout and stderr go to files.
   - Wait up to 90 s (180 × 0.5 s) for a `/api/state` body containing `"hwSource"`.
   - Run `node run-qa.mjs --api http://127.0.0.1:<Port> --json <tmp>`, copy the report to `qa/last-qa-report.json`, stop the server and show the last 20 stderr lines.
   - Native UI stage (unless `-SkipUi`, and only when `src/SCureBox.Ui/bin/Debug/net10.0/scurebox-ui.dll` exists): run it with `SCURE_UI_WINDOW=1` on Port+1. Wait up to 120 s for `/api/ui/route` to contain `"route"`, then sleep 8 s for the boot screen. Run `--category native_ui`.
   - Print an ordered summary (PASS green, SKIPPED yellow, others red), then `OVERALL: PASS` (exit 0) or `FAIL` (exit 1).
2. Rows that are never executed (marked skip): `system/reboot`, `system/shutdown`, `network/static`. `system/datetime` with a valid value only runs when `/api/system/version.os` matches /windows/i.
3. Tests that change outputs leave the machine idle: every cure sequence ends with `cure/stop`, the recipe run is aborted, the fans go back to 0, the LED calibration is restored. On the real machine the door test opens the door magnet.
4. Performance thresholds: median of 5 `/api/state` calls < 200 ms passes, < 500 ms warns. Presets and user materials in parallel: < 500 ms passes, < 1500 ms warns.
5. Representative expectations to keep:
   - cure rejections: heat 99 → 7001, heat 10 → 7001, intensity 5 → 7002, mode turbo → 7003, cool 15 → 7001, wavelength 500 refused without a code;
   - `cure/stop` is always ok;
   - recipe second start → 6015;
   - network diagnostics: unknown tool → 9080, shell-injection address → 9085;
   - NFC without a reader → 9052;
   - USB exports pass when they answer 9081 (no drive);
   - update manifest: 404 with 9081/9086/9087, or `{version, sha256}`;
   - `cloud/config` without a key → 400;
   - LED calibration factor 2.0 → 400; LED power 101 → 400;
   - in simulation: `n2LinePressure 6`, `n2Pressure {mpa 0.6, bar 6, mode analog_voltage}`.
**Configuration:** `--api` / API URL; the env above for run-all.
**Acceptance criteria:**
- `powershell -ExecutionPolicy Bypass -File qa\run-all.ps1` prints OVERALL: PASS on a clean checkout.
- `node qa/run-qa.mjs --api http://127.0.0.1:3111` gives 0 failures against a simulated server. The stored report shows 96 pass, 0 fail, 8 skip; that is an older run and the count grows with the table.
- Opening `qa-tool.html` from disk connects and runs.
**Tests:** this ticket is the test harness. It is verified by running it against a simulated server.
**Reference (source):** `qa/*`, `docs/03-ui-and-qa.md`

---

### OPS-18 — Test strategy across tests/* (projects, conventions, how they run)
**Summary**
- **What it is for:** The plan for how automated tests are organized and run across the project.
- **Problem it solves:** Without shared rules, each area tests differently and gaps appear between layers.
- **How we solve it:** Fix the test projects, frameworks, helpers and conventions, so each layer is tested alone and together, without hardware, before every release.

**Project / folder:** `tests/SCureBox.Domain.Tests`, `tests/SCureBox.Hardware.Tests`, `tests/SCureBox.Application.Tests`, `tests/SCureBox.Api.Tests`, `tests/SCureBox.Ui.Tests`, plus the non-.NET tests (`pwa/tests`, `deploy/image/test_patch_display.py`, `qa/`)
**Goal:** Define how the automated tests are organised and run, so that every layer is proven by itself and together, with no hardware, before any release. Each area writes its own test cases; this ticket fixes the projects, frameworks, fixtures and conventions they share.
**Depends on:** OPS-01, OPS-17. All src areas.
**Files to create:** the five test `.csproj` files plus the shared fixtures named below. Test classes come from each area's tickets.
**Public contract:**
- Domain, Hardware, Application and Api tests:
  - Packages: `Microsoft.NET.Test.Sdk 18.11.0`, `xunit 2.9.3`, `xunit.runner.visualstudio 4.0.1`, `coverlet.collector 10.1.0`, `Microsoft.Extensions.TimeProvider.Testing 10.11.0`. Api also uses `Microsoft.AspNetCore.Mvc.Testing 10.0.13`.
  - `IsPackable=false`, `IsTestProject=true`.
  - Project references: Domain → Domain; Hardware → Hardware; Application → Application + Hardware; Api → Api.
- Ui.Tests:
  - `OutputType=Exe`, `NoWarn xUnit1051`.
  - Packages: `xunit.v3 3.2.2`, `xunit.runner.visualstudio 3.1.5`, `Avalonia.Headless.XUnit 12.1.4`, `Microsoft.Extensions.TimeProvider.Testing 10.11.0`, `Microsoft.NET.Test.Sdk 18.11.0`.
  - References SCureBox.Ui. The Ui project grants `InternalsVisibleTo SCureBox.Ui.Tests`.
- Counts at 1.0.152 (`[Fact]`/`[Theory]`/`[AvaloniaFact]` attributes): Domain 163, Hardware 66, Application 294, Api 55, Ui 238.
- Run everything: `dotnet test SCureBox.sln -nologo -v q`. publish.ps1, package-origin-app.* and make-demo-installer.ps1 run this before building, unless `-SkipTests` is given.
**Behaviour & rules:**
1. Layer split:
   - Domain: pure logic with a fake `TimeProvider`. Areas: Control evaluators, PI/delta-sigma, recipe state machine, Programs validator/CSV/estimator/error registry, Sensors math.
   - Hardware: drivers against fake I2C and GPIO in `Fakes/` (FakeI2cBus, FakeGpioPins, FakeRgbDriver, FakeServoDriver, I2cWrite), plus HardwareConfig, the simulated system and the safety cut.
   - Application: process loops, supervision, persistence, platform and reports, with `Fakes/` (FakeHardwareSystem, FakeHardwareConfig, FakeSystemService, ProcessRig, TimePump) and `Persistence/TempDataDir`.
   - Api: integration tests with `WebApplicationFactory<Program>`.
   - Ui: headless Avalonia.
2. Api fixture `ApiFixture : WebApplicationFactory<Program>`:
   - The static constructor sets env `SCURE_SIMULATE=1`, `SCURE_SIM_TC08=1`, `SCURE_SIM_METER=1` and clears `SCURE_SIM_NFC`.
   - Per class: a fresh `SCURE_DATA_DIR` under `%TEMP%/scurebox-api-tests/<guid>` (deleted on dispose), `SCURE_UI_DIR` = the repo `ui/dist` (or a missing dir), `DATABASE_URL=""`.
   - Helpers: `GetAsync`, `PostAsync(path, body?)`, `PostRawAsync`, `StateAsync`, `WaitStateAsync(predicate, timeout)`, `ApiResponse{Status, Ok, Message, Body, Json, ContentType}`.
   - Static UI tests return early when `ui/dist/index.html` is missing.
3. Ui fixture `UiHostFixture`:
   - Builds the real host with `ScureApiHost.Build(args, …)`. Args: `--SCURE_SIMULATE=1 --SCURE_SIM_TC08=1 --SCURE_DATA_DIR=<temp scurebox-ui-tests/<guid>> --DATABASE_URL= --ASPNETCORE_URLS=http://127.0.0.1:0 --urls=http://127.0.0.1:0 --SCURE_UI_DIR=<missing>`.
   - Registers `BootTimings.Fast`, a scriptable `FakeBootSelfTest`, a `FakeOriginBrowser` (no request leaves the test) and `AddSCureBoxUi()`.
   - Exposes Navigation, Settings, Store and the Simulation (it unwraps `FreezableHardwareSystem`).
   - `TestAppBuilder` sets `[assembly: AvaloniaTestApplication]` with `UseSkia().WithInterFont().UseHeadless(UseHeadlessDrawing=false)`, so `RenderTargetBitmap` produces real pixels.
4. Repo-file lookup helpers walk up from the test binary or `[CallerFilePath]`: `RepoFiles.Config(name)` (config/presets.json, errors.json) and `RepoFiles.Source()` (src/, for tests that read the code itself, e.g. `ErrorCoverageTests`), and `TestPaths.ComponentsJson()`. Tests use the real repo config files, not copies.
5. Naming: test methods are written as plain-English sentences with underscores (e.g. `The_uv_fans_pulling_the_chamber_below_its_target_never_raise_9007`). Every release note in versions.json names its proving tests (OPS-02).
6. Time-dependent logic is tested with `FakeTimeProvider` or a time pump, never with wall-clock sleeps. Live polling in Api tests is allowed through `WaitStateAsync` with a timeout.
7. Hung test hosts: `run-all.ps1` uses `--blame-hang-timeout 3m` per project, so a hang counts as FAIL instead of blocking the run.
8. Tests that need Postgres (`PostgresSmokeTests`) run only when a database is configured. OPEN QUESTION: check the exact skip condition in that file (Application-Platform).
9. Non-.NET tests: `python deploy/image/test_patch_display.py` (unittest, pyfatfs); `python pwa/tests/test_pwa.py` (Playwright); `node qa/run-qa.mjs` (live contract). No CI configuration exists in the repo (no `.github/` or other pipeline files). Everything is run locally on the Windows dev PC with the user-local SDK and Node 18 or newer.
10. `TestResults/` folders are git-ignored.
**Configuration:** env vars set by the fixtures (above).
**Acceptance criteria:**
- `dotnet test SCureBox.sln` passes on Windows with no hardware attached, and with no ui/dist (static tests skip).
- No test writes outside its own temp folder.
- No test needs network access beyond loopback.
**Tests:** the projects themselves; `qa/run-all.ps1` as the aggregate gate.
**Reference (source):** `tests/*/*.csproj`, `tests/SCureBox.Api.Tests/ApiFixture.cs`, `tests/SCureBox.Ui.Tests/UiHostFixture.cs`, `tests/SCureBox.Ui.Tests/TestAppBuilder.cs`, `tests/SCureBox.Domain.Tests/Programs/RepoFiles.cs`, `tests/SCureBox.Hardware.Tests/TestPaths.cs`, `tests/SCureBox.Application.Tests/Fakes/*`, `qa/run-all.ps1`
