"""Alarms pulled from the machine — the console's own witness that an alarm popped up.

Twenty tests in the catalog record an alarm (`alarm_raised`, `error_code`, `alarm_text`,
`time_to_alarm`).  Until now every one of those values was typed by the operator and the
wizard advanced whether or not the machine had said anything, so a silent machine looked
exactly like a machine that alarmed — seen 2026-10-29 on DVT-SAF-003 (fixed resistor in
place of the chamber NTC): the firmware never raised 9006, the heater kept driving, and the
run walked on to the next step.  The console now watches the machine itself.

One :class:`AlarmWatch` per step.  The DUT poller (2 s) hands it the machine's active
alerts; it keeps the FIRST appearance of every code with the seconds from the moment the
step opened, and the step stays locked until the machine really raised something.  What it
saw goes into the run's values — the code, the machine's own text and the time — instead of
being typed.

A step may declare the code it expects (`expect_alert: [9006]` in the catalog).  A
different code does **not** lock the step: what the machine really said is recorded and
flagged, because a wrong code is a finding about the machine, not an operator mistake.

Two acknowledgements can open the gate instead, and both are recorded:

* ``no_alarm`` — the machine raised nothing.  Writes ``alarm_raised = false``, so the run
  ends FAIL (not BLOCKED): a silent machine is a result, not missing data.
* ``by_hand`` — the console has no link to the machine (DVT-SAF-010 freezes the firmware on
  purpose, DVT-SAF-014 breaks the stack), so the operator reads the alarm off the screen.

Qt-free on purpose: the wizard draws it, the tests drive it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

# Catalog data fields that are evidence of an alarm.  A step that captures any of them is
# watched, and the ones it captures are the ones filled in from the machine.
ALARM_FIELDS = ("alarm_raised", "error_code", "alarm_text", "time_to_alarm")

# watch states (the wizard turns these into translated prose)
OFFLINE = "OFFLINE"        # no link to the machine and nothing seen yet
WAITING = "WAITING"        # watching, the machine has raised nothing
MATCH = "MATCH"            # the expected alarm (or any alarm, when none is declared) appeared
PRE = "PRE"                # it was already active when the step opened — no time to alarm
WRONG = "WRONG"            # an alarm appeared, but not the declared code
NONE = "NONE"              # operator: nothing appeared (alarm_raised = false)
MANUAL = "MANUAL"          # operator: recorded by hand, the console had no link


@dataclass(frozen=True)
class Alert:
    """One active alarm as the machine reports it."""

    raw: str                        # the code exactly as the machine sent it ("9006")
    text: str = ""                  # the machine's own detail line

    @property
    def code(self) -> int | None:
        try:
            return int(str(self.raw).strip())
        except (TypeError, ValueError):
            return None

    def label(self) -> str:
        return f"{self.raw} · {self.text}" if self.text else str(self.raw)


def normalise_alerts(state: Mapping[str, Any] | None) -> list[Alert]:
    """`/api/state` → alerts, in both shapes the fleet speaks.

    Firmware (sCureBox-CS): ``alerts: [9011]`` with the texts in ``alertDetails:
    {"9011": "Temperature sensor disconnected: Left LED panel (TEMP_LEFT_ORIGIN)"}``.
    Simulator: ``alerts: [{"code": "9010", "message": "..."}]``.  The old reader expected
    the simulator's shape only, so against a real machine ``alarm_text`` was always empty.
    """
    if not state:
        return []
    raw = state.get("alerts") or state.get("activeAlerts") or []
    if isinstance(raw, Mapping):                       # {"9006": "text"}
        raw = [{"code": k, "message": v} for k, v in raw.items()]
    details = state.get("alertDetails") or {}
    details = {str(k): v for k, v in details.items()} if isinstance(details, Mapping) else {}
    out: list[Alert] = []
    for a in raw if isinstance(raw, list) else []:
        if isinstance(a, Mapping):
            code = a.get("code", a.get("id"))
            text = a.get("message") or a.get("detail") or a.get("text") or ""
        else:
            code, text = a, ""
        if code is None:
            continue
        code = str(code).strip()
        out.append(Alert(code, str(text or details.get(code) or "")))
    return out


@dataclass(frozen=True)
class Seen:
    """An alarm the console witnessed on this step."""

    alert: Alert
    at: float | None        # seconds from the step opening; None = already active then


class AlarmWatch:
    """The alarms one step saw, and whether that step may be passed."""

    def __init__(self, fields: Iterable[str] = (), expect: Sequence[int | str] = (),
                 active_now: Iterable[Alert] = ()):
        self.fields = tuple(f for f in fields if f in ALARM_FIELDS)
        self.expect: list[int] = []
        for c in expect or ():
            try:
                self.expect.append(int(str(c).strip()))
            except (TypeError, ValueError):
                pass
        self._seen: dict[str, Seen] = {}
        self.no_alarm = False          # operator: the machine raised nothing
        self.by_hand = False           # operator: no link, recorded by hand
        for a in active_now:           # active before the step started: evidence, but not timed
            self._seen.setdefault(a.raw, Seen(a, None))

    # ---------------------------------------------------------------- watching
    def observe(self, alerts: Iterable[Alert], elapsed: float) -> list[Seen]:
        """One poll, `elapsed` seconds after the step opened.  Returns what is new."""
        new = []
        for a in alerts:
            if a.raw in self._seen:
                continue
            s = Seen(a, max(0.0, float(elapsed)))
            self._seen[a.raw] = s
            new.append(s)
        return new

    @property
    def seen(self) -> list[Seen]:
        """Everything witnessed: what was already active first, then in the order it appeared."""
        return sorted(self._seen.values(), key=lambda s: (s.at is not None, s.at or 0.0))

    @property
    def fresh(self) -> list[Seen]:
        """Only the alarms that appeared after the step opened — the ones with a time."""
        return [s for s in self.seen if s.at is not None]

    def expected(self, s: Seen) -> bool:
        return not self.expect or s.alert.code in self.expect

    @property
    def match(self) -> Seen | None:
        """The alarm this step was waiting for: a timed one first, then one already active."""
        for group in (self.fresh, self.seen):
            for s in group:
                if self.expected(s):
                    return s
        return None

    @property
    def wrong(self) -> list[Seen]:
        """Alarms that appeared although the step declared other codes."""
        return [] if not self.expect else [s for s in self.seen if not self.expected(s)]

    # ------------------------------------------------------------------- gate
    @property
    def witnessed(self) -> bool:
        """The console itself saw the machine raise an alarm."""
        return bool(self._seen)

    @property
    def open(self) -> bool:
        """May the step be passed?"""
        return self.witnessed or self.no_alarm or self.by_hand

    def state(self, online: bool = True) -> str:
        if self.witnessed:
            m = self.match
            if m is None:
                return WRONG
            return MATCH if m.at is not None else PRE
        if self.no_alarm:
            return NONE
        if self.by_hand:
            return MANUAL
        return WAITING if online else OFFLINE

    # ------------------------------------------------------------------ values
    def captured(self) -> dict[str, Any]:
        """What the console recorded for this step, limited to the fields the step captures.

        A wrong code is still recorded (with its own code and text): the run must carry what
        the machine really said.  `time_to_alarm` is filled only when the console timed the
        alarm itself — an alarm that was already active when the step opened has no time.
        """
        if self.no_alarm and not self.witnessed:
            return {k: v for k, v in {"alarm_raised": False}.items() if k in self.fields}
        s = self.match or (self.seen[0] if self.seen else None)
        if s is None:
            return {}
        vals: dict[str, Any] = {"alarm_raised": True, "error_code": s.alert.raw}
        if s.alert.text:
            vals["alarm_text"] = s.alert.text
        if s.at is not None:
            vals["time_to_alarm"] = round(s.at, 1)
        return {k: v for k, v in vals.items() if k in self.fields}


def watches(step: Mapping[str, Any] | None) -> bool:
    """Is this a step whose alarm the console must witness?"""
    if not step:
        return False
    if step.get("expect_alert"):
        return True
    return any(c in ALARM_FIELDS for c in (step.get("capture") or []))
