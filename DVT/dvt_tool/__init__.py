"""dvt_tool — the sCure DVT campaign application (SRS-DVT-SW Rev B).

    catalog   load + validate DVT_test_catalog.yaml, expand the run set
    criteria  safe evaluator for pass_criteria expressions
    store     SQLite campaign store (units, runs, values, NCR, waivers, redlines, calibration)
    engine    wizard: phase gates, dependencies, next action, verdicts
    export    JSON / CSV / XLSX / Markdown exports of the campaign
    drive     Google Drive sync (Drive API with the engineer's account, or a synced folder)
    app       desktop application (PySide6)
"""

__version__ = "0.1.0"
