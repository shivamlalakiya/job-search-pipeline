#!/usr/bin/env python3
"""One headless outreach session per submitted row that has no Outreach row at all.

Skips rows submitted today: run_bulk.py already spawns outreach for those.
Results go to <profile>/bulk_runs.log, stage "outreach".
"""
import datetime, subprocess
from concurrent.futures import ThreadPoolExecutor
import openpyxl
import jobs, run_bulk

# Columns by header name, not position, so a column added to jobs.COLS cannot
# shift Company or Role onto the wrong cell.
O = list(openpyxl.load_workbook(jobs.XLSX, read_only=True)[jobs.OUT].iter_rows(values_only=True))
have = {(o["Company"], o["Role"]) for o in (dict(zip(O[0], r)) for r in O[1:])}
today = f"{datetime.date.today()}"
rows = [r for r in jobs.app_rows() if r["Status"] == "submitted"
        and (r["Company"], r["Role"]) not in have and str(r["Date"])[:10] != today]
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
