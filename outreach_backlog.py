#!/usr/bin/env python3
"""One headless outreach session per submitted row that has no Outreach row at all.

Skips rows submitted today: run_bulk.py already spawns outreach for those.
Results go to <profile>/bulk_runs.log, stage "outreach".
"""
import datetime, subprocess
from concurrent.futures import ThreadPoolExecutor
import openpyxl
import profiles, run_bulk

wb = openpyxl.load_workbook(profiles.DIR / "tracker.xlsx", read_only=True)
A = list(wb["Applications"].iter_rows(values_only=True))
h = A[0]
have = {(r[1], r[2]) for r in list(wb["Outreach"].iter_rows(values_only=True))[1:]}
today = f"{datetime.date.today()}"
rows = [dict(zip(h, r)) for r in A[1:] if r[h.index("Status")] == "submitted"
        and (r[1], r[2]) not in have and str(r[0])[:10] != today]
print(len(rows), "rows", flush=True)


def one(r):
    try:
        p = subprocess.run(run_bulk.cmd("outreach", run_bulk.row_text(r)), cwd=run_bulk.ROOT,
                           env=run_bulk.env(), capture_output=True, text=True,
                           timeout=run_bulk.TIMEOUT["outreach"])
        run_bulk.log("outreach", r, p.stdout)
    except subprocess.TimeoutExpired:
        run_bulk.log("outreach", r, "timeout")


with ThreadPoolExecutor(4) as ex:  # ponytail: same cap as MAX_TAILOR
    list(ex.map(one, rows))
