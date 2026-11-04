#!/usr/bin/env python3
"""Stop hook: while a bulk run is on, the main thread may not end its turn
with roles still pending on the tracker (CLAUDE.md Priority 1).

A run is on while the file .bulk-run exists at the repo root and names this
session as its owner. Start one with `python3 jobs.py bulk`, which records
$CLAUDE_CODE_SESSION_ID; the hook deletes the file once `jobs.py queue` is
empty. Every other session in the folder is left alone: on 24 Sep 2026 a flag
with no owner made one session's run block a second session's Stop, telling it
to spawn apply agents while the first session held the browser.

Progress is a fingerprint of every pending row's status, URL and resume, not
the pending count. On 24 Sep 2026 a run stopped at 161 pending because the
work in hand (resolving URLs, tailoring) moves rows between stages without
shrinking the count, so three honest stops looked like a stall and the hook
let go. It still lets go after 3 stops with no change at all, so a genuinely
stuck run cannot loop forever.

Every 5 new submissions it also starts outreach/bounces.py --retry in the
background (with --send when <profile>/autosend marks a standing permission that
covers derived addresses), logging to <profile>/outreach/bounces.log, so the
bounce loop no longer depends on the main thread remembering it.
"""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FLAG = ROOT / ".bulk-run"
if not FLAG.exists():
    sys.exit(0)
try:
    state = json.loads(FLAG.read_text() or "{}")
except ValueError:
    state = {}
try:
    me = json.load(sys.stdin).get("session_id")
except ValueError:
    me = None
if not me or state.get("owner") != me:
    sys.exit(0)
sys.path.insert(0, str(ROOT))
import jobs, profiles

rows = jobs.pending()
if not rows:
    FLAG.unlink()
    sys.exit(0)

submitted = sum(r["Status"] == "submitted" for r in jobs.app_rows())
since = state.get("bounce_at", submitted)
if submitted - since >= 5:
    log = open(profiles.DIR / "outreach" / "bounces.log", "a")
    cmd = [sys.executable, str(ROOT / "outreach" / "bounces.py"), "--retry"]
    if profiles.AUTOSEND:
        cmd.append("--send")
    subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
    since = submitted

fp = hashlib.sha1(json.dumps([[r["Company"], r["Role"], r["Status"], r["Apply URL"], r["Resume"]]
                              for r in rows], default=str).encode()).hexdigest()
stalls = state.get("stalls", 0) + 1 if state.get("fp") == fp else 0
state.update(owner=me, fp=fp, stalls=stalls, bounce_at=since)
FLAG.write_text(json.dumps(state))
if stalls >= 3:
    sys.exit(0)

by = {s: [r for r in rows if r["stage"] == s] for s in jobs.STAGES}
todo = []
if by["apply"]:
    r = by["apply"][0]
    todo.append(f"spawn the apply agent (foreground, subagent_type apply) for {r['Company']} | "
                f"{r['Role']}")
if by["tailor"]:
    todo.append(f"{len(by['tailor'])} rows need a resume and cover letter: keep up to 4 tailor "
                "agents running in the background (subagent_type tailor, one row each)")
if by["resolve"]:
    todo.append(f"{len(by['resolve'])} rows have no employer URL: `python3 jobs.py resolve`, run "
                "the .li_resolve.js it writes in your own tab, then `jobs.py resolve --ingest`")
if by["park"]:
    todo.append("`python3 jobs.py park` for the account-gated rows")
gap = subprocess.run([sys.executable, str(ROOT / "jobs.py"), "gaps"], capture_output=True,
                     text=True, cwd=ROOT).stdout.split("\n== outreach held")[0]
unsent = sum(l.startswith("  ") for l in gap.splitlines())
if unsent:
    todo.append(f"{unsent} submitted rows have no outreach: spawn outreach agents in the "
                "background for the newest ones")
print(json.dumps({"decision": "block", "reason":
    f"Bulk run: {len(rows)} roles still pending. Do all of these now, in one block: "
    + "; ".join(todo) + ". Only one apply agent at a time; if one is still running, or "
    "background agents are all you are waiting on, say so and end the turn. Delete .bulk-run "
    "only if the user told you to stop."}))
