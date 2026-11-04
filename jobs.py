#!/usr/bin/env python3
"""Job-board helpers for this folder. Two jobs: compile a tailored resume and
keep tracker.xlsx up to date. Run `python3 jobs.py` for usage.

    python3 jobs.py resume profiles/YourName/resumes/Acme.tex
    python3 jobs.py add-app --company Acme --role "Data Analyst" --status found --url https://...
    python3 jobs.py add-outreach --company Acme --email jane@acme.com --status sent
    python3 jobs.py drop --company Acme --role "Data Analyst"
    python3 jobs.py show
    python3 jobs.py browser               # is this person's browser profile in use, and by which pid
    python3 jobs.py queue                 # what a bulk run still has to do, next role first
    python3 jobs.py parked [--reopen]     # account walls grouped by host, for one signup sitting
    python3 jobs.py answer --ats workday --question "Are you a protected veteran?"
    python3 jobs.py answers
    python3 jobs.py selfcheck
    python3 jobs.py profile YourName

Every path above is read out of the folder named in PROFILE at the repo root,
so tracker.xlsx, answers.json and the base resume all belong to one person.
"""
import argparse, fcntl, json, pathlib, re, shutil, subprocess, sys, tempfile
from datetime import date

import openpyxl

import profiles

ROOT = profiles.DIR
XLSX = ROOT / "tracker.xlsx"
ANSWERS = ROOT / "answers.json"
LOCK = ROOT / ".tracker.lock"

APPS = "Applications"
OUT = "Outreach"
COLS = {
    APPS: ["Date", "Company", "Role", "Location", "Apply URL", "ATS", "Resume",
           "Status", "Confirmation", "Salary Answered", "Notes"],
    OUT: ["Date", "Company", "Role", "Contact Name", "Contact Title", "Email",
          "Email Confidence", "Subject", "Attachment", "Status", "Reply",
          "Address Verified", "Tried", "Backups", "Notes"],
}
APP_STATUS = ["found", "skipped", "tailoring", "ready", "submitted", "blocked",
              "stopped", "rejected", "interview", "offer"]
# "verified" means an actual example address at that domain was seen (a byline,
# a press release, a media kit), not an aggregator's pattern percentage or a
# masked prefix. "unverified" is everything else that was still sent under a
# standing per-person authorisation. "bounced" is a confirmed non-delivery.
# Added 15 Sep 2026 so a parallel agent can find and re-check unverified rows
# without re-reading the whole Outreach sheet.
# "delivered" is set by outreach/bounces.py: sent two or more days ago and no
# bounce report came back.
ADDRESS_VERIFIED = ["verified", "unverified", "bounced", "delivered"]
OUT_STATUS = ["draft", "sent", "bounced", "replied", "no-reply"]
# "Tried" is every address sent to for that row, space separated, oldest first.
# outreach/bounces.py appends to it on each retry and stops at its --max.
# "Backups" is the outreach agent's ranked list of further addresses, "addr|First"
# for another named person (the retry rewrites "Hi <name>,"), bare "addr" for the
# same person. Space separated, best first. bounces.py sends to the first untried one before it falls back
# to guessing address shapes. Added 24 Sep 2026 at the user's request.

# A bulk run's to-do list: rows that exist on the tracker and have not reached
# an outcome. Everything else (submitted, skipped, blocked, ...) is done.
PENDING = ("ready", "tailoring", "found")
ACCOUNT_NOTE = re.compile(r"(?i)account|password|sign.?in|log.?in|register|PARKED")


def book():
    if XLSX.exists():
        return openpyxl.load_workbook(XLSX)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, cols in COLS.items():
        ws = wb.create_sheet(name)
        ws.append(cols)
        for c in ws[1]:
            c.font = openpyxl.styles.Font(bold=True)
        ws.freeze_panes = "A2"
    return wb


def widths(ws):
    for i, col in enumerate(ws.columns, 1):
        n = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(max(n + 2, 10), 60)


def locked(fn):
    """Serialise tracker writes. Every write is load-modify-save, so the
    outreach subagent running add-outreach while the main thread runs add-app
    would otherwise drop one of the two rows."""
    def wrap(*a, **kw):
        with open(LOCK, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            return fn(*a, **kw)
    return wrap


def migrate(ws, cols):
    """Bring an existing sheet's columns in line with COLS[sheet], including
    a new column inserted in the middle rather than only at the end. Reads
    every row keyed by its OWN current header, so no cell moves to the wrong
    column, then rewrites the sheet in the new column order. No-op, and cheap,
    once the header already matches.

    Not locked on its own: it is only ever called from inside add(), which
    holds the lock for its whole load-modify-save cycle. A second decorator
    here would try to flock the same lock file twice from one thread and
    self-deadlock, since flock blocks the second acquisition rather than
    reentering it."""
    header = [c.value for c in ws[1]]
    if header == cols:
        return
    old_idx = {name: i for i, name in enumerate(header) if name}
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if any(v is not None for v in row):
            rows.append({name: row[i] for name, i in old_idx.items() if i < len(row)})
    ws.delete_rows(1, ws.max_row)
    ws.append(cols)
    for c in ws[1]:
        c.font = openpyxl.styles.Font(bold=True)
    for r in rows:
        ws.append([r.get(c) for c in cols])


def save(wb):
    """Write to a temp file and rename it over the tracker. Readers do not
    take the lock, and on 25 Sep 2026 one read the workbook mid-save and got
    "File is not a zip file"; a rename is atomic, so a reader sees either the
    old file or the new one, never half of one."""
    tmp = XLSX.with_name(f".{XLSX.name}.tmp")
    wb.save(tmp)
    tmp.replace(XLSX)


# Hard rule set by the user 30 Oct 2026: never apply to a job already applied
# to. add() used to dedupe only on the exact company + role string, so the same
# posting came back as "Allara" after "Allara Health", or under a new LinkedIn
# id, and agents caught it by hand (bulk_runs.log, Sep-Oct 2026). A row now
# counts as already applied when it shares a posting id (any URL in Apply URL
# or Notes) or a normalised company + role with a row in APPLIED. Also no new
# role at all at a company where the user is interviewing or holds an offer: a
# Data Analyst role was applied to on 30 Oct 2026 at a company already
# interviewing the user for Senior Data Analyst, a different posting the id and
# title checks could not see.
ACTIVE = ("interview", "offer")
APPLIED = ("submitted", "rejected", "interview", "offer")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def posting_ids(text):
    """Posting ids in every URL in `text`. Ids of 7+ digits and uuids are
    unique across ATSs on their own; shorter ones (Oracle 70304, Workday R12345)
    are qualified by host."""
    ids = set()
    for url in re.findall(r"https?://\S+", text or ""):
        host = re.sub(r"^www\.", "", url.split("/")[2].lower())
        ids.update(UUID.findall(url.lower()))
        query = " ".join(re.findall(r"(?:gh_jid|jid|pid|jobId|job_id|id)=(\d+)", url))
        for n in re.findall(r"(?<![A-Za-z0-9.%])R?-?(\d{5,})(?![\d.])", url.split("?")[0] + " " + query):
            ids.add(n if len(n) >= 7 else f"{host}:{n}")
    return ids


def name_key(company, role):
    co = " ".join(w for w in re.sub(r"[^a-z0-9]+", " ", str(company or "").lower()).split()
                  if w not in ("inc", "llc", "corp", "corporation", "company", "co", "the", "ltd"))
    role = re.sub(r"\s*[-–#(]\s*(req\w*\s*)?[a-z]{0,3}-?\d{4,}\)?\s*$", "", str(role or "").lower())
    return co, " ".join(re.sub(r"[^a-z0-9]+", " ", role).split())


def applied_index(rows):
    """(ids, name keys, active companies) of every row that was actually applied to."""
    ids, names, active = {}, {}, {}
    for r in rows:
        if r.get("Status") in APPLIED:
            for i in posting_ids(f"{r.get('Apply URL') or ''} {r.get('Notes') or ''}"):
                ids.setdefault(i, r)
            names.setdefault(name_key(r.get("Company"), r.get("Role")), r)
            if r.get("Status") in ACTIVE:
                active.setdefault(name_key(r.get("Company"), "")[0], r)
    return ids, names, active


def already_applied(r, index):
    """The applied row this one duplicates, or None. Never the row itself."""
    ids, names, active = index
    same = lambda h: (h.get("Company"), h.get("Role")) == (r.get("Company"), r.get("Role"))
    for i in posting_ids(f"{r.get('Apply URL') or ''} {r.get('Notes') or ''}"):
        if i in ids and not same(ids[i]):
            return ids[i]
    co, role = name_key(r.get("Company"), r.get("Role"))
    for (hco, hrole), h in names.items():
        if hrole == role and co and hco and (co.startswith(hco) or hco.startswith(co)) and not same(h):
            return h
    for hco, h in active.items():
        if co and hco and (co.startswith(hco) or hco.startswith(co)) and not same(h):
            return h
    return None


@locked
def add(sheet, values, key=("Company", "Role")):
    """Append a row, or update the existing row with the same key.

    Locked for the whole load-modify-save cycle, not just the schema-migration
    step. Without this, two concurrent add() calls each load their own copy
    of the workbook, and the second wb.save() silently discards whatever the
    first one wrote: a measured selfcheck run of 8 concurrent add() calls
    against a fresh file left 1 row, not 8. Found 15 Sep 2026 while cleaning
    up after a separate outreach audit, in a tracker.xlsx two sessions were
    writing at the same time; the reasoning in `locked`'s own docstring, that
    add-app and add-outreach need serialising, was correct, it just was not
    applied to the function it describes.

    `values` may be a list of rows, written in one load and one save; an
    850-row workbook costs about a second per save."""
    wb = book()
    ws = wb[sheet]
    cols = COLS[sheet]
    migrate(ws, cols)
    idx = {c: i for i, c in enumerate(cols)}
    many = isinstance(values, list)
    batch = values if many else [values]
    if sheet == APPS:
        index = applied_index([dict(zip(cols, r)) for r in ws.iter_rows(min_row=2, values_only=True)])
    for values in batch:
        unknown = set(values) - set(cols)
        if unknown:
            sys.exit(f"unknown columns for {sheet}: {sorted(unknown)}")
        values.setdefault("Date", date.today().isoformat())
        match = None
        for row in ws.iter_rows(min_row=2):
            if all(str(row[idx[k]].value or "") == str(values.get(k, "")) for k in key):
                match = row
                break
        if sheet == APPS:
            merged = dict(zip(cols, (c.value for c in match))) if match else {}
            merged.update(values)
            dup = merged.get("Status") in PENDING and already_applied(merged, index)
            if dup:
                values["Status"] = "skipped"
                values["Notes"] = (f"DUPLICATE: already applied as {dup['Company']} / {dup['Role']} "
                                   f"({dup['Status']} {dup['Date']}). " + str(merged.get("Notes") or ""))[:2000]
                print(f"duplicate, skipped: {values.get('Company')} / {values.get('Role')} = "
                      f"{dup['Company']} / {dup['Role']}")
        if match:
            for col, val in values.items():
                match[idx[col]].value = val
            action = "updated"
        else:
            ws.append([values.get(c) for c in cols])
            action = "added"
        if not many:
            print(f"{action} {sheet}: {values.get('Company')} / {values.get('Role')}")
    if many:
        print(f"wrote {len(batch)} rows to {sheet}")
    widths(ws)
    save(wb)


@locked
def drop(sheet, company, role):
    """Delete the row for one company and role."""
    wb = book()
    ws = wb[sheet]
    idx = {c: i for i, c in enumerate(COLS[sheet])}
    hits = [r[0].row for r in ws.iter_rows(min_row=2)
            if str(r[idx["Company"]].value or "") == company
            and (role is None or str(r[idx["Role"]].value or "") == role)]
    for row in reversed(hits):
        ws.delete_rows(row)
    save(wb)
    print(f"dropped {len(hits)} row(s) from {sheet}: {company} / {role or 'any role'}")


def show(match=None):
    """Every row, or with `match` only rows containing it (case-insensitive).
    The whole tracker is 200KB of output by 24 Sep 2026, which the outreach
    agent's double-send check was pulling into context every time."""
    if not XLSX.exists():
        sys.exit(f"{XLSX.name} does not exist yet")
    wb = openpyxl.load_workbook(XLSX)
    for name in wb.sheetnames:
        ws = wb[name]
        print(f"\n== {name} ({ws.max_row - 1} rows)")
        for row in ws.iter_rows(min_row=2, values_only=True):
            line = " | ".join(str(v or "") for v in row[:10])
            if any(row) and (not match or match.casefold() in line.casefold()):
                # Notes is past column 10, so without this agents never saw it
                notes = str(row[COLS[name].index("Notes")] or "") if name in COLS else ""
                print("  " + line + (f" | {notes[:160]}" if notes else ""))


def app_rows():
    if not XLSX.exists():
        return []
    ws = openpyxl.load_workbook(XLSX, read_only=True)[APPS]
    return [dict(zip(COLS[APPS], r)) for r in ws.iter_rows(min_row=2, values_only=True)
            if r and r[1]]


# What a pending row needs next. A row moves resolve -> tailor -> apply, or
# resolve -> park. Until 24 Sep 2026 the queue only knew ready/found, so the
# Stop hook told the main thread to "spawn the apply agent" for 148 rows that
# still had a LinkedIn URL and no resume, and each agent spent its whole setup
# finding that out.
STAGES = ("apply", "tailor", "resolve", "park")


def stage(r):
    import ats
    url = r["Apply URL"] or ""
    if not url or ats.detect(url).endswith("aggregator") or "click.appcast.io" in url:
        return "resolve"
    if r["park"]:
        return "park"
    res = r["Resume"] or ""
    if not (res.endswith(".pdf") and profiles.path(res).exists()):
        return "tailor"
    return "apply"


def pending():
    """Rows a bulk run still owes an outcome, in the order to work them:
    apply, tailor, resolve, park (see STAGES). The Stop hook reads this list,
    so a run is not over while it is non-empty."""
    import ats
    accts = profiles.accounts()
    allrows = app_rows()
    index = applied_index(allrows)
    rows = [r for r in allrows if r["Status"] in PENDING and not already_applied(r, index)]
    for r in rows:
        r["park"] = ats.needs_account(r["Apply URL"] or "", accts)
        r["stage"] = stage(r)
    return sorted(rows, key=lambda r: (STAGES.index(r["stage"]), PENDING.index(r["Status"])))


def queue():
    rows = pending()
    by = {s: sum(r["stage"] == s for r in rows) for s in STAGES}
    print(f"{len(rows)} pending: " + ", ".join(f"{n} {s}" for s, n in by.items()))
    for r in rows:
        print(f"  {r['stage'].upper():7} {r['Status']} | {r['Company']} | {r['Role']} | {r['ATS'] or ''} | {r['Apply URL'] or ''}")


RESOLVE_JS = profiles.ROOT / ".li_resolve.js"
LI_ID = re.compile(r"linkedin\.com/jobs/view/(?:[^/\s]*-)?(\d{6,})")


def resolve(ingest=None, limit=40):
    """LinkedIn rows resolved to the employer's own apply URL in one browser
    call instead of one apply agent each. Without --ingest, writes
    .li_resolve.js for the next `limit` LinkedIn rows; run it with
    browser_run_code_unsafe (filename .li_resolve.js) in a tab you opened, save
    the JSON it returns, then `jobs.py resolve --ingest <file>`.

    Measured 24 Sep 2026: a guest LinkedIn page in the browser carries the
    employer link as a[href*="safety/go"] (plain curl does not, the markup is
    rendered client side), about 0.6s a page. Ingest writes the employer URL
    and ATS onto the row, skips closed postings, parks Easy-Apply-only rows,
    and parks every account-gated row in the queue, so none of them ever
    reaches tailoring or an apply agent."""
    import ats
    if not ingest:
        ids, careers = [], []
        for r in pending():
            if r["stage"] == "resolve" and "CAREERS" in (r["Notes"] or ""):
                careers.append(r)
                continue
            m = r["stage"] == "resolve" and LI_ID.search(f"{r['Apply URL']} {r['Notes']}")
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
        ids = ids[:limit]
        for r in careers:
            print(f"CAREERS | {r['Company']} | {r['Role']} | {r['Apply URL'] or ''}")
        if not ids:
            print("no LinkedIn rows left to resolve")
        else:
            RESOLVE_JS.write_text(
                (profiles.ROOT / "pw" / "li_resolve.js").read_text().replace("__IDS__", json.dumps(ids)))
            print(f"{len(ids)} ids -> {RESOLVE_JS.name}. Run it with browser_run_code_unsafe "
                  f"filename {RESOLVE_JS.name} in your own tab, then resolve --ingest <json>.")
        return
    got = json.loads(pathlib.Path(ingest).read_text())
    if isinstance(got, str):  # the helper returns JSON.stringify(...)
        got = json.loads(got)
    today = date.today().isoformat()
    batch = []
    for r in pending():
        m = r["stage"] == "resolve" and LI_ID.search(f"{r['Apply URL']} {r['Notes']}")
        hit = next((g for g in got if m and g[0] == m.group(1)), None)
        if not hit or "CAREERS" in (r["Notes"] or ""):
            continue
        li, url, flag = r["Apply URL"], hit[1], hit[2]
        row = {"Company": r["Company"], "Role": r["Role"]}
        if "error=true" in url:  # Greenhouse's answer for a removed job
            flag = "closed"
        if flag == "closed":
            row.update(Status="skipped", Notes=f"dead posting {today}: LinkedIn says no longer "
                       f"accepting applications. {r['Notes'] or ''}")
        elif url:
            row.update({"Apply URL": url, "ATS": ats.detect(url),
                        "Notes": f"resolved {today} from {li}. {r['Notes'] or ''}"})
        else:
            # User pref 3 Oct 2026: a LinkedIn Easy Apply or error row is applied
            # to on the company's own careers site, never parked for LinkedIn.
            row.update(Notes=f"CAREERS {today}: LinkedIn gave '{flag}', find this role on the "
                       f"company careers site. {r['Notes'] or ''}")
        batch.append(row)
    add(APPS, batch)
    park()


def park():
    """Record every account-gated pending row skipped with a PARKED note, so
    it shows up in `parked` for the user's one signup sitting and leaves the
    queue. No tailoring, no browser."""
    today = date.today().isoformat()
    import ats
    batch = [{"Company": r["Company"], "Role": r["Role"], "Status": "skipped",
              "Notes": f"PARKED {today}: account-gated {ats.detect(r['Apply URL'])} on "
                       f"{ats.host(r['Apply URL'])}. {r['Notes'] or ''}"}
             for r in pending() if r["stage"] == "park"]
    if batch:
        add(APPS, batch)
    print(f"parked {len(batch)}")


NOT_A_WALL = re.compile(r"(?i)dead posting|no longer (accepting|available)|not currently accepting"
                        r"|clearance|duplicate|Easy Apply|staffing|removed")
CLOSED = re.compile(r"(?i)no longer (available|accepting|open)|job (has been )?(filled|closed|expired)"
                    r"|position (is |has been )?(closed|filled)|posting (has )?expired|page not found")


def posting_live(url):
    import ats, urllib.request
    try:
        if ats.detect(url) == "workday" and ats.workday_cxs_url(url):
            return bool(ats.workday_posting(url).get("title"))
        req = urllib.request.Request(url, headers={"User-Agent": ats.UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return not CLOSED.search(resp.read(400000).decode("utf-8", "replace"))
    except Exception:
        return False


def parked(reopen=False, live=False):
    """Account-walled rows grouped by host, so the user creates each account
    once and every role on that tenant opens up. With --reopen, rows on a host
    now listed in accounts.txt go back to `found` for the next run."""
    import ats
    accts = profiles.accounts()
    by_host = {}
    for r in app_rows():
        url = r["Apply URL"] or ""
        if "linkedin.com" in url:
            # the employer URL was often found but only written into the note
            found = [u for u in re.findall(r"https?://[^\s,;)'\"]+", r["Notes"] or "")
                     if "linkedin.com" not in u]
            url = found[0].rstrip(".") if found else url
        if r["Status"] in ("skipped", "blocked") and url and not NOT_A_WALL.search(r["Notes"] or "") and (
                ats.detect(url) in ats.ACCOUNT_ATS or ACCOUNT_NOTE.search(r["Notes"] or "")):
            h = "linkedin, employer URL never resolved" if "linkedin.com" in url else ats.host(url)
            by_host.setdefault(h, []).append(r)
    ready = [h for h in by_host if h in accts]
    if reopen:
        for h in ready:
            for r in by_host[h]:
                add(APPS, {"Company": r["Company"], "Role": r["Role"], "Status": "found",
                           "Notes": f"reopened {date.today()}: account exists on {h}. "
                                    + (r["Notes"] or "")})
        return
    todo = sorted((h for h in by_host if h not in accts), key=lambda h: -len(by_host[h]))
    if live:
        # Only accounts worth making: a Workday posting still on its CxS API,
        # anything else still answering without a closed-posting message.
        # ponytail: text heuristic on the page body, a JS-only board reads live.
        from concurrent.futures import ThreadPoolExecutor
        rows = [r for h in todo for r in by_host[h]]
        alive = dict(zip([id(r) for r in rows], ThreadPoolExecutor(12).map(
            lambda r: posting_live(r["Apply URL"] or ""), rows)))
        for h in todo:
            by_host[h] = [r for r in by_host[h] if alive[id(r)]]
        todo = sorted((h for h in todo if by_host[h]), key=lambda h: -len(by_host[h]))
        out = [f"# Accounts to create for {profiles.DIR.name}, {date.today()}", "",
               "One account per host unlocks every role under it. Use the email in profile.md "
               "and the password ALT_ATS_PASSWORD from ATS-CREDENTIALS.txt (ALT_ATS_PASSWORD_16 "
               "where a site caps length). Then add a line `<host> <key>` to accounts.txt and "
               "run `python3 jobs.py parked --reopen`.", ""]
        for h in todo:
            out.append(f"- [ ] **{h}** ({len(by_host[h])}): {by_host[h][0]['Apply URL']}")
            out += [f"    - {r['Company']} | {r['Role']}" for r in by_host[h]]
        (profiles.DIR / "signup_list.md").write_text("\n".join(out) + "\n")
        print(f"{sum(len(by_host[h]) for h in todo)} live roles behind {len(todo)} accounts "
              f"-> {profiles.DIR.name}/signup_list.md")
        return
    print(f"{sum(len(by_host[h]) for h in todo)} roles behind {len(todo)} accounts not yet made"
          f" ({len(ready)} hosts already in accounts.txt, run --reopen)")
    for h in todo:
        print(f"\n  {h}  ({len(by_host[h])})")
        for r in by_host[h]:
            print(f"    {r['Company']} | {r['Role']} | {r['Apply URL']}")


def browser():
    """Whether the active profile's Chromium user-data-dir is held, by reading
    its SingletonLock ("host-pid"), which is the lock Chromium itself obeys.

    Replaces `ps -ef | grep "Chrome for Testing|chromium"`, which the
    runbook used to prescribe and which misses the real holder when the
    server launches system Google Chrome: on 24 Sep 2026 that check said
    "free" while PID 81888 (Google Chrome, up since 12:32) held the profile, a
    peer session passed the "free" on, and the next apply agent hit
    "Browser is already in use". Exits 1 when held so it can gate a spawn."""
    import os
    d = pathlib.Path((ROOT / "browser.txt").read_text().strip()).expanduser()
    lock = d / "SingletonLock"
    pid = None
    if lock.is_symlink():
        tail = os.readlink(lock).rsplit("-", 1)[-1]
        pid = int(tail) if tail.isdigit() else None
    if pid:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pid = None
        except PermissionError:
            pass
    if not pid:
        print(f"free: {d}")
        return
    # The Playwright MCP server keeps its Chrome alive between tool calls, and
    # browser_close only closes pages, so after the first apply agent of a
    # stretch the lock stays held by this very session. Reading that as
    # "another session" stalled every later agent on 29 Sep 2026. A Claude
    # process that is an ancestor of both the holder and this command is the
    # same session, so the browser is ours to keep using.
    claude = next((p for p in _ancestors(os.getpid())
                   if _comm(p).endswith("/claude")), None)
    if claude and claude in _ancestors(pid):
        print(f"own: {d} held by this session's Playwright server (pid {pid}). Use it.")
        return
    cmd = subprocess.run(["ps", "-p", str(pid), "-o", "lstart=,comm="],
                         capture_output=True, text=True).stdout.strip()
    sys.exit(f"in use: {d} held by pid {pid} ({cmd}). Do not launch a browser agent.")


def _comm(pid):
    return subprocess.run(["ps", "-p", str(pid), "-o", "comm="],
                          capture_output=True, text=True).stdout.strip()


def _ancestors(pid):
    out = []
    while pid > 1 and len(out) < 30:
        out.append(pid)
        ppid = subprocess.run(["ps", "-p", str(pid), "-o", "ppid="],
                              capture_output=True, text=True).stdout.strip()
        if not ppid.isdigit():
            break
        pid = int(ppid)
    return out


def bulk(stop=False):
    """Start (or with --stop end) a bulk run owned by this Claude session. The
    Stop hook in .claude/hooks/bulk_continue.py only holds the owner's turn
    open, so a second session in the folder is never pushed to apply."""
    import os
    flag = profiles.ROOT / ".bulk-run"
    if stop:
        flag.unlink(missing_ok=True)
        print("bulk run ended")
        return
    me = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not me:
        sys.exit("CLAUDE_CODE_SESSION_ID is not set; run this from inside the Claude session that will do the run")
    if flag.exists():
        owner = (json.loads(flag.read_text() or "{}")).get("owner")
        if owner and owner != me:
            sys.exit(f"another session ({owner}) owns the bulk run. One session per run.")
    flag.write_text(json.dumps({"owner": me}))
    print(f"bulk run on, owned by this session. {len(pending())} pending.")


def gaps():
    """The two things a fresh session has to know and cannot see in one sheet:
    submitted applications with no outreach sent, and outreach held as a draft
    on an application that did go in. Either role string may carry a suffix the
    other lacks: an outreach role can read "Research Analyst referral", and an
    application role can read "Institutional Research Analyst I - R109275" where
    the outreach row dropped the req id. So the match is prefix in either
    direction. Keeping it one-way reported Louisville as un-emailed on 11 Sep
    2026 when the email had gone, which is how a second copy reaches a real
    person."""
    if not XLSX.exists():
        print(f"{XLSX} does not exist yet, nothing applied for on this profile")
        return
    wb = openpyxl.load_workbook(XLSX)
    ai = {c: i for i, c in enumerate(COLS[APPS])}
    oi = {c: i for i, c in enumerate(COLS[OUT])}
    def rows(sheet, idx):
        return [r for r in wb[sheet].iter_rows(min_row=2, values_only=True) if r[idx["Company"]]]
    sub = [(r[ai["Company"]], r[ai["Role"]]) for r in rows(APPS, ai)
           if r[ai["Status"]] == "submitted"]
    out = [(r[oi["Company"]], r[oi["Role"]] or "", r[oi["Status"]], r[oi["Email"]])
           for r in rows(OUT, oi)]
    # "sent" here means an outreach attempt actually went out, not the literal
    # OUT_STATUS value "sent": a bounced or replied row is still an attempt, and
    # only "draft" means nothing left this machine. Splitting "bounced" out as
    # its own status (15 Sep 2026) broke this when it was still `os == "sent"`,
    # which made a bounced-and-diagnosed email read as never sent at all.
    ATTEMPTED = set(OUT_STATUS) - {"draft"}
    covers = lambda st, c, role: any(
        oc == c and (orole.startswith(role) or (role or "").startswith(orole))
        and (os in ATTEMPTED if st == "sent" else os == st)
        for oc, orole, os, _ in out)

    print("\n== submitted with no outreach sent")
    for c, role in sub:
        if not covers("sent", c, role):
            print(f"  {c} | {role}")
    print("\n== outreach held at draft on a submitted application")
    for c, role in sub:
        for oc, orole, os, email in out:
            if oc == c and orole.startswith(role) and os == "draft":
                print(f"  {c} | {orole} | {email}")


# Words that are ordinary connective prose rather than a claim. Tailoring is
# allowed to reorder, reframe and re-emphasise; it is not allowed to introduce
# an experience, a tool or a domain the base resume does not contain.
FILLER = set("""about across alike alongside also applied applying audiences background balancing based
building built checks clear clearly collaborative collaborators comfortable communicating decisions
delivered depend designing documenting exceeding finding findings fluent giving hands-on higher
includes independently information issues level maintaining managing methods non-technical owning
performing picking producing programming raise record records recurring results routine skilled
stakeholders support supporting teams terms through track translating turning well-documented
working""".split())


def audit(tex):
    """Name every word a tailored resume introduced that the base resume lacks.

    Written 11 Sep 2026 after a tailored summary claimed systems-analyst work
    (functional specifications, test plans) that appears nowhere in the base
    resume, and reached an employer before anyone noticed. A plain `diff` is not
    a usable check here: the rtk shell hook rewrote one and reported "Files are
    identical" for two files with different md5s, so this reads both files
    itself. Filler is ignored; what is left is either a real claim or a
    paraphrase worth a human's eye.
    """
    base = (ROOT / "base" / "resume_base.tex").read_text()
    words = lambda s: set(re.findall(r"[a-z][a-z\-']{4,}", s.lower()))
    new = sorted(words(pathlib.Path(tex).read_text()) - words(base) - FILLER)
    if new:
        print("  claims absent from base/resume_base.tex: " + ", ".join(new))
        print("  tailoring may reorder and reframe. It may not add an experience the base lacks.")
    return new


def resume(tex):
    """Compile a tailored .tex and fail unless the result is exactly one page.

    base/resume_base.tex is exempt, the same way it is already exempt from
    audit(). It is the full record of what may be claimed, not a document that
    gets sent, and docs/resume.md puts the one-page rule on the tailored copy,
    which is cut per posting. One profile's base has held more than a page of content
    since at least 14 Sep 2026, which turned selfcheck red for a file that was
    never meant to fit."""
    tex = pathlib.Path(tex).resolve()
    if not tex.exists():
        sys.exit(f"no such file: {tex}")
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                            f"-output-directory={tmp}", str(tex)],
                           capture_output=True, text=True, cwd=tex.parent)
        log = pathlib.Path(tmp, tex.stem + ".log")
        if r.returncode:
            errs = [l for l in log.read_text(errors="replace").splitlines() if l.startswith("!")]
            sys.exit("pdflatex failed:\n" + "\n".join(errs[:5] or [r.stdout[-800:]]))
        # pdflatex hard-wraps its log at column 79, which can split "(1 page"
        # across lines for long filenames/tempdir paths. Strip newlines first.
        pages = re.search(r"\((\d+)\s*pages?", log.read_text(errors="replace").replace("\n", ""))
        pages = int(pages.group(1)) if pages else 0
        out = tex.with_suffix(".pdf")
        shutil.copy(pathlib.Path(tmp, tex.stem + ".pdf"), out)
    print(f"{out.relative_to(ROOT) if ROOT in out.parents else out}  ({pages} page)")
    if tex.name != "resume_base.tex":
        audit(tex)
        if pages != 1:
            sys.exit(f"NOT ONE PAGE ({pages}). Trim bullets or tighten \\vspace and rebuild.")
        clipped = _clipped_content(out)
        if clipped:
            sys.exit(f"CONTENT MISSING FROM RENDERED PAGE ({clipped}). A margin/\\vspace hack "
                      "pushed real content off the visible page even though pdflatex still "
                      "reports 1 page (negative \\vspace after the last section absorbs the "
                      "overflow silently, so the page-count check alone can't see it). "
                      "Loosen the margin or trim more, then rebuild.")


def _clipped_content(pdf):
    """Catch the 16 Sep 2026 defect class: an aggressive topmargin/textheight
    hack plus trailing negative \\vspace can push the name header above the
    page, or the last Education line below it, while pdflatex still reports
    one page, because the negative glue absorbs the overflow at the final
    page break instead of forcing a second page.

    Checking glyph y-coordinates against the page box was tried first and
    rejected: a resume that legitimately uses the full page (bottom line a
    few pt from the edge, e.g. y=788 on a 792pt-tall page) is fine, but is
    geometrically indistinguishable from one that's actually clipped -- the
    only real difference is whether the content survived into the text
    layer at all. So this checks for presence, not position: the candidate's
    name (read once from base/resume_base.tex's `\\huge ... \\textbf{NAME}`
    line, the same header every tailored resume shares) and the final
    Education entry's degree line (the last `\\resumeSubheading`'s third
    argument in the base) must both appear somewhere in the plain-text
    extraction of the compiled PDF. Returns a short description of the
    problem, or None if clean."""
    base = pdf.parent.parent / "base" / "resume_base.tex" if pdf.parent.name == "resumes" else None
    if base is None or not base.exists():
        return None
    base_text = base.read_text(errors="replace")
    name = re.search(r"\\huge\s*\\textbf\{([^}]+)\}", base_text)
    degree = re.findall(r"\\resumeSubheading\s*\{[^}]*\}\{[^}]*\}\s*\{([^}]*)\}", base_text)
    if not name or not degree:
        return None
    name, degree = name.group(1).strip(), degree[-1].strip()
    r = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True)
    if r.returncode:
        return None
    text = " ".join(r.stdout.split())
    if name not in text:
        return f'name "{name}" not found in the rendered text (pushed above the page)'
    if degree not in text:
        return f'last Education line "{degree}" not found in the rendered text (pushed below the page)'
    return None


def akey(question):
    """The lookup key. Case and whitespace vary with how a form wraps its text.
    Nothing else is normalised, on purpose. "Are you a veteran?" and "Are you a
    protected veteran?" are different questions with different answers, and any
    fuzzy match that collapses them puts a false statement on a signed form."""
    return " ".join(question.split()).casefold()


def answers_load():
    """The bank, keyed by lowercase ATS name. Agents wrote both "Workday" and
    "workday" (and "Greenhouse"/"greenhouse") before 24 Sep 2026, which split
    each bank in two so half the answers were never found. Folding on load
    means an older file still reads whole; the first write saves it folded."""
    raw = json.loads(ANSWERS.read_text()) if ANSWERS.exists() else {}
    data = {}
    for ats, entries in raw.items():
        bank = data.setdefault(ats.casefold(), {})
        for k, v in entries.items():
            bank.setdefault(k, v)
    return data


def answer_get(ats, question):
    return answers_load().get(ats.casefold(), {}).get(akey(question))


def answer_set(ats, question, answer, source, host=None, force=False):
    """Record the exact option label used for one exact question on one ATS."""
    data = answers_load()
    ats = ats.casefold()
    seen = data.setdefault(ats, {})
    key = akey(question)
    old = seen.get(key)
    if old and old["answer"] != answer and not force:
        sys.exit(f"{ats} already answers this differently:\n  stored: {old['answer']}\n"
                 f"  new:    {answer}\nPass --force if the stored one is wrong.")
    entry = old or {"question": " ".join(question.split()),
                    "first_seen": date.today().isoformat(), "seen_on": []}
    entry["answer"] = answer
    entry["source"] = source
    if host and host not in entry["seen_on"]:
        entry["seen_on"].append(host)
    seen[key] = entry
    ANSWERS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"recorded {ats}: {entry['question']} -> {answer}")


def answers_show(only=None):
    """With an ATS name, only that bank: the compact read an apply agent does
    once instead of loading the whole answers.json into context."""
    data = answers_load()
    if not data:
        print(f"{ANSWERS.name} is empty")
    for ats in sorted(data):
        if only and ats != only.casefold():
            continue
        print(f"\n== {ats} ({len(data[ats])})")
        for entry in sorted(data[ats].values(), key=lambda e: e["question"]):
            print(f"  {entry['question']}\n    -> {entry['answer']}  [{entry['source']}]")


def selfcheck():
    global XLSX, ANSWERS
    with tempfile.TemporaryDirectory() as tmp:
        XLSX = pathlib.Path(tmp, "t.xlsx")
        add(APPS, {"Company": "Acme", "Role": "DA", "Status": "found"})
        add(APPS, {"Company": "Acme", "Role": "DA", "Status": "submitted"})
        add(APPS, {"Company": "Acme", "Role": "DE", "Status": "found"})
        ws = openpyxl.load_workbook(XLSX)[APPS]
        rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(r)]
        assert len(rows) == 2, f"upsert made {len(rows)} rows, expected 2"
        assert rows[0][COLS[APPS].index("Status")] == "submitted", rows[0]
        assert rows[0][0] == date.today().isoformat(), rows[0]
        # already-applied gate: same posting id or same company/role under another string
        add(APPS, {"Company": "Allara Health", "Role": "Growth Analyst", "Status": "submitted",
                   "Apply URL": "https://jobs.ashbyhq.com/allara/2192480b-1111-2222-3333-444455556666"})
        add(APPS, {"Company": "Allara", "Role": "Growth Analyst - R12345", "Status": "found"})
        add(APPS, {"Company": "X Corp", "Role": "Analyst", "Status": "found",
                   "Notes": "li https://www.linkedin.com/jobs/view/1/ apply https://jobs.ashbyhq.com/allara/2192480b-1111-2222-3333-444455556666/application"})
        add(APPS, {"Company": "Acme", "Role": "DA II", "Status": "found"})
        st = {r[1]: r[COLS[APPS].index("Status")] for r in
              openpyxl.load_workbook(XLSX)[APPS].iter_rows(min_row=2, values_only=True) if r[1]}
        assert st["Allara"] == "skipped" and st["X Corp"] == "skipped", st
        assert st["Allara Health"] == "submitted", st
        assert ("Acme", "DA II") in {(r["Company"], r["Role"]) for r in pending()}, "DA II is a different job"
        add(APPS, {"Company": "Zeta", "Role": "Senior Data Analyst", "Status": "interview"})
        add(APPS, {"Company": "Zeta", "Role": "Data Analyst", "Status": "found"})
        assert "Zeta" not in {r["Company"] for r in pending()}, "company with an interview must be blocked"
        assert posting_ids("https://acme.wd5.myworkdayjobs.com/x/job/NY/Analyst_R12345") == {"acme.wd5.myworkdayjobs.com:12345"}
        for c in ("Allara Health", "Allara", "X Corp", "Zeta"):
            drop(APPS, c, None)
        drop(APPS, "Acme", "DA II")
        # concurrent writers must not lose a row: flock serialises load-modify-save
        import threading
        ts = [threading.Thread(target=add, args=(OUT, {"Company": f"C{i}", "Role": "R"}))
              for i in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        outs = [r for r in openpyxl.load_workbook(XLSX)[OUT].iter_rows(min_row=2, values_only=True) if any(r)]
        assert len(outs) == 8, f"concurrent adds left {len(outs)} rows, expected 8"

        # gaps() has to see a submitted application with no sent outreach, and
        # must not be fooled by a role suffix like "Research Analyst referral"
        add(APPS, {"Company": "Beta", "Role": "Research Analyst", "Status": "submitted"})
        add(OUT, {"Company": "Beta", "Role": "Research Analyst referral", "Status": "sent"})
        # and the other direction: the application row carries the req id, the
        # outreach row does not. Reported as un-emailed until 11 Sep 2026.
        add(APPS, {"Company": "Gamma", "Role": "IR Analyst I - R109275", "Status": "submitted"})
        add(OUT, {"Company": "Gamma", "Role": "IR Analyst I", "Status": "sent"})
        # audit() has to catch a claim the base resume does not support, and
        # stay quiet about a pure reorder. The real failure it exists for was a
        # summary line claiming "functional specifications" and "test plans".
        import io, contextlib
        base_tex = ROOT / "base" / "resume_base.tex"
        if not base_tex.exists():
            print(f"selfcheck ok (no {base_tex}, so the resume audit was skipped)")
            return
        fake = pathlib.Path(tmp, "tailored.tex")
        base_text = base_tex.read_text()
        fake.write_text(base_text + "\n% developing functional specifications and running test plans\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            flagged = audit(fake)
        assert "specifications" in flagged, flagged
        assert "absent from base" in buf.getvalue(), buf.getvalue()
        fake.write_text("\n".join(reversed(base_text.splitlines())))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert audit(fake) == [], "a pure reorder must not be flagged"
        assert buf.getvalue() == "", buf.getvalue()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gaps()
        g = buf.getvalue()
        assert "Gamma" not in g, f"a req-id suffix on the application role must still match:\n{g}"
        assert "Acme | DA" in g, "a submitted app with no outreach was not reported: " + g
        assert "Beta" not in g, "a suffixed outreach role was not matched: " + g
        drop(APPS, "Beta", "Research Analyst")
        drop(OUT, "Beta", "Research Analyst referral")
        drop(APPS, "Gamma", "IR Analyst I - R109275")
        drop(OUT, "Gamma", "IR Analyst I")

        drop(APPS, "Acme", "DE")
        rows = [r for r in openpyxl.load_workbook(XLSX)[APPS].iter_rows(min_row=2, values_only=True) if any(r)]
        assert len(rows) == 1, f"drop left {len(rows)} rows, expected 1"

        ANSWERS = pathlib.Path(tmp, "a.json")
        vet = "Are you a protected veteran?"
        answer_set("workday", vet, "I am not a protected veteran", "profile.md",
                   host="wgu.wd5.myworkdayjobs.com")
        assert answer_get("workday", vet)["answer"] == "I am not a protected veteran"
        # same question, different wrapping and case, still a hit
        assert answer_get("workday", "  ARE YOU A\n  PROTECTED VETERAN? ")
        # the near miss that a fuzzy matcher gets wrong: different question, no answer
        assert answer_get("workday", "Are you a veteran?") is None
        # the bank is per ATS, because option labels are not shared across them
        assert answer_get("icims", vet) is None
        answer_set("workday", vet, "I am not a protected veteran", "profile.md",
                   host="rit.wd5.myworkdayjobs.com")
        assert answer_get("workday", vet)["seen_on"] == [
            "wgu.wd5.myworkdayjobs.com", "rit.wd5.myworkdayjobs.com"]
        # a second, different answer to a question already recorded has to be refused
        try:
            answer_set("workday", vet, "I identify as a veteran", "profile.md")
            raise AssertionError("overwrote a stored answer without --force")
        except SystemExit as e:
            assert "already answers this differently" in str(e), e
        assert answer_get("workday", vet)["answer"] == "I am not a protected veteran"
        # the ATS name is case-folded, so "Workday" reads the same bank
        assert answer_get("Workday", vet)["answer"] == "I am not a protected veteran"

        # pending(): applyable before account-gated, ready before found
        add(APPS, {"Company": "Q1", "Role": "R", "Status": "found",
                   "Apply URL": "https://x.wd1.myworkdayjobs.com/ext/job/a_1"})
        add(APPS, {"Company": "Q2", "Role": "R", "Status": "found",
                   "Apply URL": "https://job-boards.greenhouse.io/x/jobs/1"})
        add(APPS, {"Company": "Q3", "Role": "R", "Status": "ready",
                   "Apply URL": "https://jobs.lever.co/x/1"})
        order = [(r["Company"], r["park"]) for r in pending()]
        assert order == [("Q3", False), ("Q2", False), ("Q1", True)], order
    ok = pathlib.Path(ROOT, "base/resume_base.tex")
    if ok.exists():
        resume_check = subprocess.run([sys.executable, __file__, "resume", str(ok)],
                                      capture_output=True, text=True)
        both = resume_check.stdout + resume_check.stderr
        # The base is allowed to run long, so what is checked here is that it
        # still compiles and that resume() reported a page count at all. The
        # one-page gate is exercised on tailored copies, where it applies.
        assert re.search(r"\(\d+ page\)", resume_check.stdout), both
        assert resume_check.returncode == 0, both
        pathlib.Path(ROOT, "base/resume_base.pdf").unlink(missing_ok=True)
    # a pending row's stage: LinkedIn resolves, utm_source=linkedin.com does not
    row = lambda url, park=False, res="": {"Apply URL": url, "park": park, "Resume": res}
    assert stage(row("https://www.linkedin.com/jobs/view/4457404632/")) == "resolve"
    assert stage(row("")) == "resolve"
    assert stage(row("https://www.bequad.com/job/1?utm_source=linkedin.com")) == "tailor"
    assert stage(row("https://x.wd1.myworkdayjobs.com/a/job/b", park=True)) == "park"
    assert LI_ID.search("resolved from https://www.linkedin.com/jobs/view/data-at-x-4457404632/.").group(1) == "4457404632"
    print("selfcheck ok")


def profile_switch(name):
    """Point PROFILE and .mcp.json at one person, or print who is active.

    The browser profile and the ATS secrets file are named in .mcp.json, not in
    Python, so switching has to rewrite that file too or one person would
    apply from inside another's logged-in Workday sessions. Claude Code reads .mcp.json at
    startup, so a switch needs a restart before the browser is hers."""
    root = profiles.ROOT
    if not name:
        print(f"{profiles.NAME}  ({profiles.DIR})")
        return
    d = profiles.PROFILES / name
    if not d.is_dir():
        sys.exit(f"{d} does not exist. Create the folder first.")
    mcp = root / ".mcp.json"
    conf = json.loads(mcp.read_text())
    args = conf["mcpServers"]["playwright"]["args"]
    browser = d / "browser.txt"
    if not browser.exists():
        sys.exit(f"{browser} is missing. Put the Chromium user-data-dir for {name} in it, "
                 f"e.g. {pathlib.Path.home() / '.cache' / ('pw-' + name.lower())}. "
                 "It is a file, not a constant, because an existing directory holds logged-in "
                 "ATS sessions and renaming it would sign the user out of every ATS.")
    for flag, value in (("--user-data-dir", browser.read_text().strip()),
                        ("--secrets", str(d / "ATS-CREDENTIALS.txt"))):
        args[args.index(flag) + 1] = value
    shutil.copy2(mcp, profiles.PROFILES / "archive" / f"mcp_{profiles.NAME}_{date.today()}.json")
    mcp.write_text(json.dumps(conf, indent=2) + "\n")
    (root / "PROFILE").write_text(name + "\n")
    print(f"active profile: {name}\nrestart Claude Code so the browser picks up .mcp.json")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("resume").add_argument("tex")
    sub.add_parser("show").add_argument("match", nargs="?")
    sub.add_parser("gaps")
    d = sub.add_parser("drop")
    d.add_argument("--sheet", choices=[APPS, OUT], default=APPS)
    d.add_argument("--company", required=True)
    d.add_argument("--role")
    sub.add_parser("selfcheck")
    sub.add_parser("answers").add_argument("ats", nargs="?")
    sub.add_parser("queue")
    rs = sub.add_parser("resolve")
    rs.add_argument("--ingest", help="JSON file saved from the .li_resolve.js run")
    rs.add_argument("--limit", type=int, default=40)
    sub.add_parser("park")
    sub.add_parser("browser")
    sub.add_parser("bulk").add_argument("--stop", action="store_true")
    pk = sub.add_parser("parked")
    pk.add_argument("--reopen", action="store_true")
    pk.add_argument("--live", action="store_true", help="check each posting, write signup_list.md")
    sub.add_parser("profile").add_argument("name", nargs="?")
    ans = sub.add_parser("answer")
    ans.add_argument("--ats", required=True, help="workday, greenhouse, icims, ...")
    ans.add_argument("--question", required=True, help="the form's exact wording")
    ans.add_argument("--set", dest="value", help="the exact option label to record")
    ans.add_argument("--source", help="where the answer came from, e.g. profile.md")
    ans.add_argument("--host", help="the tenant this was seen on")
    ans.add_argument("--force", action="store_true", help="overwrite a stored answer")
    for cmd, sheet, statuses in (("add-app", APPS, APP_STATUS), ("add-outreach", OUT, OUT_STATUS)):
        s = sub.add_parser(cmd)
        for col in COLS[sheet]:
            flag = "--" + col.lower().replace(" ", "-")
            hint = statuses if col == "Status" else (
                ADDRESS_VERIFIED if col == "Address Verified" else None)
            s.add_argument(flag, dest=col, help=f"one of {hint}" if hint else None)
    a = p.parse_args()
    if a.cmd == "resume":
        resume(a.tex)
    elif a.cmd == "show":
        show(a.match)
    elif a.cmd == "gaps":
        gaps()
    elif a.cmd == "drop":
        drop(a.sheet, a.company, a.role)
    elif a.cmd == "selfcheck":
        selfcheck()
    elif a.cmd == "profile":
        profile_switch(a.name)
    elif a.cmd == "answers":
        answers_show(a.ats)
    elif a.cmd == "bulk":
        bulk(a.stop)
    elif a.cmd == "browser":
        browser()
    elif a.cmd == "queue":
        queue()
    elif a.cmd == "resolve":
        resolve(a.ingest, a.limit)
    elif a.cmd == "park":
        park()
    elif a.cmd == "parked":
        parked(a.reopen, a.live)
    elif a.cmd == "answer":
        if a.value:
            if not a.source:
                sys.exit("--source is required with --set, so the answer stays traceable")
            answer_set(a.ats, a.question, a.value, a.source, a.host, a.force)
        else:
            hit = answer_get(a.ats, a.question)
            if not hit:
                sys.exit(f"miss: {a.ats} has no answer for that exact wording, read profile.md")
            print(f"{hit['answer']}\n  source: {hit['source']}  seen on: {', '.join(hit['seen_on']) or '-'}")
    else:
        sheet = APPS if a.cmd == "add-app" else OUT
        # Empty string clears a cell; only unpassed flags (None) are ignored.
        vals = {c: getattr(a, c) for c in COLS[sheet] if getattr(a, c, None) is not None}
        if not vals.get("Company"):
            sys.exit("--company is required")
        add(sheet, vals)


if __name__ == "__main__":
    main()
