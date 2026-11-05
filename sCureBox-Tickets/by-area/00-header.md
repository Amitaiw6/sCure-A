# sCure Box — System Rebuild Tickets

**Source of truth:** sCureBox-CS 1.0.152 (C# / .NET 10, Avalonia 12, ASP.NET Core minimal API, Raspberry Pi CM5 + sCure IO board).
**Purpose:** this file is the complete brief for a Claude agent to rebuild the whole sCure Box software. Each ticket is one subsystem. Every ticket is self-contained, and its names (types, members, routes, JSON fields, config keys, error codes) must be used EXACTLY as written.

## How to use this file (instructions to the implementing agent)

1. **Read "Owner decisions & standing rules" first.** These rules are mandatory, and they override any ticket text that conflicts with them.
2. **Build in the order given below.** For each ticket:
   - create the files listed under *Files to create*;
   - implement the *Public contract* and *Behaviour & rules*;
   - write the tests listed under *Tests*;
   - make every item under *Acceptance criteria* pass;
   - then move on to the next ticket.
3. **Do not guess.** Some items are marked `OPEN QUESTION:`. Ask the owner about those instead of inventing behaviour.
4. **Keep the build strict.** `TreatWarningsAsErrors` is on. The build and all tests must stay green after every ticket.
5. **Bump the version with every change.** Each change bumps `VERSION` and adds a `config/versions.json` entry (see the Deploy-Ops tickets).
6. **Check coverage at the end.** Every row in "Requirements catalogue (SRS)" and every row in "Owner decisions" must be covered by a ticket and by a test.

## Ticket areas and build order

| # | Area | Ticket prefix | Depends on |
|---|------|---------------|-----------|
| 1 | Repo skeleton, build, versioning, test strategy | OPS- (repo/build tickets first) | — |
| 2 | Domain (models, programs, control algorithms, error registry) | DOM- | 1 |
| 3 | Hardware (bus, drivers, IO board map, safety, simulator) | HW- | 2 |
| 4 | Application: process engine (run, phases, supervision, status) | PROC- | 2, 3 |
| 5 | Application: platform, persistence, reports | PLAT- | 2, 4 |
| 6 | DVT bench & HDT | DVT- | 4, 5 |
| 7 | API host and endpoints | API- | 4, 5, 6 |
| 8 | Native UI: shell, theme, controls, pages | UI- | 7 |
| 9 | Native UI: dialogs | UIDLG- | 8 |
| 10 | Kiosk web, PWA, QA tool, deploy, OS image, services | OPS- (remaining) | 7, 8 |
| 11 | sCure Cloud portal (Google Apps Script + Sheets; separate deployable, talks to the machine via PLAT-10) | CLOUD- | 5 (contract), can be built in parallel |

The DEV/EMB_SCURE branch of github.com/originlabs/SCure is a port of the same system. Its migration log is docs/MIGRATION_TO_SCUREBOX_CS.md. When this file and that port disagree, this file (sCureBox-CS behaviour + owner decisions) wins.

