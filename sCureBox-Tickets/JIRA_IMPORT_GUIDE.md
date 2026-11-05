# Importing into Jira — sCureBox_jira_hierarchy.csv

Structure: 12 Epics (one per area incl. the sCure Cloud portal + owner decisions + SRS) → 311 Tasks (192 subsystem tickets incl. 55 CLOUD, 78 OD + 12 EP decisions, 29 SRS chapters) → 999 Sub-tasks.

## Before importing (once, by a Jira admin)
1. The project must support the Epic, Task and Sub-task issue types (any Software / Business project does).
2. Optional: create a link type named **Implements** (Settings → Issues → Issue linking: outward "implements", inward "is implemented by"). Without it, map the Implements columns to **Relates**.

## Import
Settings → System → External System Import → CSV → choose the file (encoding UTF-8).

Field mapping:
| CSV column | Jira field |
|---|---|
| Issue Id | Issue ID |
| Parent Id | Parent ID (Epic → Task, and Task → Sub-task) |
| Issue Type | Issue Type |
| Summary | Summary |
| Description | Description (already in Jira wiki format) |
| Labels (all columns) | Labels |
| Component (all columns) | Component/s (the importer creates any missing components) |
| Blocked by (all columns) | Link: **Blocks** — direction "is blocked by" (inward) |
| Relates (all columns) | Link: **Relates** |
| Implements (all columns) | Link: **Implements** (or Relates) |
| Ticket Key | Do not map, or map to a custom text field "Ticket Key" |

## After importing — useful filters
- All of one feature: `component = "Status strip (RGB)"`
- Build order: `labels = build-wave-01` … `build-wave-22` (a ticket only needs tickets from earlier waves)
- Owner decisions: `labels = owner-decision`; open questions: `labels = open-question`; untested: `labels = untested`; safety: `labels = safety`
- Every Task also has a "Links" section at the top of its description (Features / Blocked by / Blocks / Relates to / Implements / Implemented by) using the ticket keys (HW-10, PROC-10, ...), so the links are visible even if the link columns are not mapped.
