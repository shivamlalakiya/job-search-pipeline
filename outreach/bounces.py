#!/usr/bin/env python3
"""Find outreach emails that bounced, mark them on the tracker, and retry.

    python3 outreach/bounces.py                  # read the inbox, mark bounces, change nothing else
    python3 outreach/bounces.py --retry          # also build the next-address draft for each bounce
    python3 outreach/bounces.py --retry --send   # and send it
    python3 outreach/bounces.py followup         # draft one in-thread follow-up per owed row
    python3 outreach/bounces.py followup --send  # and send them
    python3 outreach/bounces.py selfcheck        # offline

Reads the active profile's Gmail over IMAP with the same keychain app password
mkemail.py sends with. A bounce is a mailer-daemon report whose failed
recipient is the Email on an Outreach row still marked `sent`. That row goes
to `bounced`. With --retry, the next untried address shape for the same named
person is built from the row's body file and, with --send, sent; the row goes
back to `sent` on the new address and the address joins the Tried column.

Stops for a row after --max emails (default 2: set by the user 4 Nov 2026,
"keep only max 2 email", counting every address tried plus a follow-up), when the report is a
policy block (5.7.x: the gateway refused the message, so every other shape at
that domain hits the same filter), or when the row has no contact name.
Set by the user 24 Sep 2026: retry a bounce until it is delivered, up to a
limit, instead of the earlier one-attempt rule in docs/outreach.md.

A `sent` row two or more days old with no bounce is marked Address Verified
`delivered`. A `submitted` application whose rejection email is in the mailbox
goes to `rejected` (whole-word company match, a clear rejection phrase, and the
role named or the only one there). A row whose contact (or a colleague, on a "Re:" subject) wrote
back gets its Reply column filled. Inbox subjects that look like an interview
invite are printed as `check:` lines only; record those with add-app --status
interview by hand. The bulk Stop hook runs `--retry` (with `--send` when <profile>/autosend exists) every
five submissions, logging to <profile>/outreach/bounces.log.
"""
import argparse, email, email.utils, html, imaplib, pathlib, re, sys
from datetime import date, timedelta
from email import policy

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import jobs, profiles

SHAPES = ["{f}{last}", "{first}", "{first}.{last}", "{first}{last}", "{first}{l}",
          "{f}.{last}", "{first}_{last}", "{last}{f}", "{last}.{first}", "{last}"]
# Ordered by docs/outreach.md "Measured on 19 Sep 2026": shorter shapes bounced
# less than first.last, so they go first after whatever was tried already.


def candidates(name, domain):
    """Address shapes for one person, best first."""
    parts = [re.sub(r"[^a-z]", "", p) for p in name.lower().split()]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return []
    first, last = parts[0], parts[-1]
    out = []
    for s in SHAPES:
        a = s.format(first=first, last=last, f=first[0], l=last[0]) + "@" + domain
        if a not in out:
            out.append(a)
    return out


def parse_bounce(raw):
    """[(address, status code)] for every recipient a DSN says failed.
    Delay notices ("will retry") carry Action: delayed and are ignored."""
    msg = email.message_from_bytes(raw, policy=policy.compat32)
    failed = []
    for part in msg.walk():
        if part.get_content_type() != "message/delivery-status":
            continue
        for block in part.get_payload():
            if str(block.get("Action", "")).strip().lower() != "failed":
                continue
            rcpt = str(block.get("Final-Recipient") or block.get("Original-Recipient") or "")
            addr = rcpt.split(";")[-1].strip().strip("<>").lower()
            if addr:
                failed.append((addr, str(block.get("Status", "")).strip()))
    if not failed:  # Gmail always sets this, some relays skip the DSN part
        for addr in str(msg.get("X-Failed-Recipients", "")).split(","):
            if addr.strip():
                failed.append((addr.strip().lower(), ""))
    return failed


def inbox_bounces(days):
    import mkemail
    since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(mkemail.FROM, mkemail.password())
    out = []
    try:
        for box in ("INBOX", '"[Gmail]/Spam"'):
            if m.select(box, readonly=True)[0] != "OK":
                continue
            _, ids = m.search(None, f'(SINCE {since} FROM "mailer-daemon")')
            for i in ids[0].split():
                _, data = m.fetch(i, "(BODY.PEEK[])")
                out += parse_bounce(data[0][1])
    finally:
        m.logout()
    return out


NOREPLY = re.compile(r"no-?reply|do-?not-?reply|mailer-daemon|postmaster|notifications?@")
INTERVIEW = re.compile(r"(?i)interview|phone screen|schedul|next steps|availability")
AUTO = re.compile(r"(?i)automatic reply|auto-?reply|out of office|\booo\b|maternity leave")
RECEIPT = re.compile(r"(?i)hiring event|open interviews|survey|thank you for (your )?appl|application (received|submitted)|we received your")


def inbox_headers(days):
    """[(from address, subject, date)] for every INBOX message since `days` ago, headers only."""
    import mkemail
    since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(mkemail.FROM, mkemail.password())
    out = []
    try:
        # All Mail, not INBOX: on 4 Nov 2026 a recruiter's reply that had been
        # archived was missed and the contact got a follow-up anyway.
        m.select('"[Gmail]/All Mail"', readonly=True)
        _, ids = m.search(None, f"(SINCE {since})")
        if ids[0]:
            _, data = m.fetch(b",".join(ids[0].split()), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            for d in data:
                if isinstance(d, tuple):
                    h = email.message_from_bytes(d[1], policy=policy.default)
                    frm = email.utils.parseaddr(str(h["From"] or ""))[1].lower()
                    if frm != mkemail.FROM.lower():
                        out.append((frm, str(h["Subject"] or ""), str(h["Date"] or "")))
    finally:
        m.logout()
    return out


def match_replies(rows, msgs):
    """{(company, role): note} for outreach rows a human answered: the sender is
    an address tried for that row, or the same domain on a "Re:" subject (a
    colleague answering the thread). Rows that already have a Reply are skipped."""
    found = {}
    for r in rows:
        if r.get("Reply") or not r["Email"] or r["Status"] not in ("sent", "bounced"):
            continue
        addrs = set(tried(r))
        doms = {a.split("@")[-1] for a in addrs}
        for frm, subj, when in msgs:
            if NOREPLY.search(frm) or "no_such_address" in frm or "@" not in frm or AUTO.search(subj):
                continue
            if frm in addrs or (frm.split("@")[1] in doms and subj.lower().startswith("re:")):
                found[(r["Company"], r["Role"])] = f"{when[:16]} {frm}: {subj[:80]}"
                break
    return found


REJECT = ('"newer_than:120d (unfortunately OR \\"other candidates\\" OR \\"another candidate\\" '
          'OR \\"not to move forward\\" OR \\"not moving forward\\" OR \\"not be moving forward\\" '
          'OR \\"decided to pursue\\" OR \\"not a fit\\" OR \\"did not select\\" OR \\"not been selected\\" '
          'OR \\"no longer under consideration\\" OR \\"position has been filled\\")"')
FOLLOWUP = """Hi {first},

Following up on my note from {sent} about the {role} role. I am still very interested, and I would welcome a short conversation if the team is moving forward.

Thank you for your time,
{me}
"""


STRONG = re.compile(r"other candidates?|another candidate|not to move forward|not be moving forward|"
                    r"not moving forward with|decided to pursue|not been selected|did not select|"
                    r"no longer under consideration|position has been filled|decided not to|"
                    r"move forward with other|not to proceed|will not be proceeding|won.t be moving forward|"
                    r"unable to move forward|pursue other|not a fit for", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def plain_name(co):
    """Lowercase company name without legal suffixes or brackets."""
    return re.sub(r"(?i)[,.]?\s*\b(inc|llc|ltd|corp|corporation|company|co|services)\b\.?|\(.*?\)", "", co or "").strip().lower()


def match_rejection(sent, frm, subj, body, by_company, out_domains):
    """[(company, role)] a rejection email is about, or None when it names a
    company but not which of its several roles. The company must appear as a
    whole word in the sender or subject ("Forma" is not "information"), or the
    mail comes from the outreach contact's domain and names the role (a shared
    ATS domain carries every hosted employer's mail). A role is picked by
    its title in the subject or body, else when it is the only one there."""
    if not STRONG.search(body) and not STRONG.search(subj):
        return []
    head, dom, text = (frm + " " + subj).lower(), frm.split("@")[-1].strip(">").lower(), norm(subj + " " + body[:4000])
    title = lambda role: norm(re.sub(r"\(.*?\)", "", role))[:30]
    found = []
    for co, rows in by_company.items():
        rows = [r for r in rows if str(r["Date"] or "")[:10] <= sent]
        named = [r for r in rows if len(title(r["Role"])) > 5 and title(r["Role"]) in text]
        name = co
        by_name = len(name) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", head)
        # A sender like summitrentals@myworkday.com only counts with the role named.
        squashed = len(norm(name)) >= 6 and norm(name) in norm(head) and named
        if not rows or not (by_name or squashed or (dom in out_domains.get(co, ()) and named)):
            continue
        # Every role applied to there counts, not only open ones: with one
        # role already rejected, its email was once hung on the other open one.
        pick = named or (rows if len(rows) == 1 else None)
        if pick is None:
            return None
        found += [(r["Company"], r["Role"]) for r in pick if r.get("Status", "submitted") == "submitted"]
    return found


def rejections(days):
    """Mark `submitted` applications `rejected` from rejection emails in All Mail."""
    import mkemail
    from email.utils import parsedate_to_datetime
    apps = [r for r in jobs.app_rows() if r["Status"] in ("submitted", "rejected", "interview", "offer")]
    # Keyed by plain name: the tracker has both "Toyco" and "Toyco, Inc.",
    # and two groups each looked like a company with one role.
    by_company, out_domains = {}, {}
    for r in apps:
        by_company.setdefault(plain_name(r["Company"]), []).append(r)
    for o in out_rows():
        if o["Email"]:
            out_domains.setdefault(plain_name(o["Company"]), set()).add(o["Email"].split("@")[1].lower())
    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(mkemail.FROM, mkemail.password())
    marks = {}
    try:
        m.select('"[Gmail]/All Mail"', readonly=True)
        _, ids = m.search(None, "X-GM-RAW", REJECT.replace("newer_than:120d", f"newer_than:{days}d"))
        for i in ids[0].split():
            _, d = m.fetch(i, "(BODY.PEEK[])")
            h = email.message_from_bytes(d[0][1], policy=policy.default)
            try:
                sent = parsedate_to_datetime(str(h["Date"])).date().isoformat()
                part = h.get_body(preferencelist=("plain", "html"))
                body = re.sub(r"<[^>]+>|&nbsp;|\s+", " ", part.get_content() if part else "")
            except Exception:
                continue
            subj = str(h["Subject"] or "")
            hit = match_rejection(sent, str(h["From"] or ""), subj, body, by_company, out_domains)
            if hit is None:
                print(f"check:   rejection names no role, {sent} {str(h['From'])[:40]}: {subj[:70]}")
            for k in hit or []:
                marks[k] = f"rejection email {sent}: {subj[:80]}"
    finally:
        m.logout()
    old = {(r["Company"], r["Role"]): r for r in apps}
    marks = {k: v for k, v in marks.items() if old[k]["Status"] == "submitted"}
    for (co, role), note in marks.items():
        print(f"rejected: {co} | {role}")
    if marks:
        jobs.add(jobs.APPS, [{"Company": co, "Role": role, "Date": old[(co, role)]["Date"], "Status": "rejected",
                              "Notes": note + ". " + (old[(co, role)]["Notes"] or "")}
                             for (co, role), note in marks.items()])


def company_key(name):
    """Lowercase company name without legal suffixes, for matching inbox text."""
    n = re.sub(r"(?i)[,.]?\s*\b(inc|llc|ltd|corp|corporation|company|co|services)\b\.?", "", name or "")
    return re.sub(r"[^a-z0-9]", "", n.lower())


def followup_rows(rows, apps, rejected_text, today):
    """Outreach rows owed one follow-up: delivered, a week old, no reply, the
    application still `submitted`, no rejection in the inbox naming the
    company, and no follow-up drafted or sent before."""
    status = {(r["Company"], r["Role"]): r["Status"] for r in apps}
    week = (today - timedelta(days=7)).isoformat()
    out = []
    seen = {(r["Email"] or "").lower() for r in rows if "followup" in (r["Notes"] or "").lower()}
    for r in rows:
        k = company_key(r["Company"])
        if (r["Status"] == "sent" and not r.get("Reply") and r["Email"]
                and r.get("Address Verified") in ("delivered", "verified")
                and str(r["Date"] or "")[:10] <= week
                and status.get((r["Company"], r["Role"])) == "submitted"
                and not (len(k) > 2 and k in rejected_text)
                and company_key(r["Email"].split("@")[1]) not in rejected_text  # sender domain
                and "followup" not in (r["Notes"] or "").lower()
                and len(tried(r)) < 2  # a bounce retry already made it two emails
                and r["Email"].lower() not in seen):  # one nudge per person, even across two roles
            seen.add(r["Email"].lower())
            out.append(r)
    return out


def followup(send):
    """Draft (and with send, send) one in-thread follow-up per owed row."""
    import mkemail
    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(mkemail.FROM, mkemail.password())
    try:
        m.select('"[Gmail]/All Mail"', readonly=True)
        _, ids = m.search(None, "X-GM-RAW", REJECT)
        rejected = ""
        if ids[0]:
            _, data = m.fetch(b",".join(ids[0].split()), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            rejected = re.sub(r"[^a-z0-9]", "", " ".join(d[1].decode("utf-8", "replace")
                                                          for d in data if isinstance(d, tuple)).lower())
        # Replies are re-read here rather than trusted from the Reply column,
        # which is only as fresh as the last plain bounces.py run.
        live = match_replies(out_rows(), inbox_headers(120))
        rows = [r for r in followup_rows(out_rows(), jobs.app_rows(), rejected, date.today())
                if (r["Company"], r["Role"]) not in live]
        m.select('"[Gmail]/Sent Mail"', readonly=True)
        # Every original's Message-ID first, so the follow-up lands in the same
        # thread. Looked up before any send: on 4 Nov 2026 Gmail dropped the
        # IMAP connection after 59 SMTP sends interleaved with these fetches.
        todo = []
        for r in rows:
            body = body_for(r["Email"])
            hi = re.match(r"Hi ([^,\n]+),", body.read_text()) if body else None
            if not hi:
                print(f"skip:  {r['Company']} | {r['Email']} | no body file with a 'Hi <name>,' line")
                continue
            _, ids = m.search(None, "TO", r["Email"])
            msgid = None
            if ids[0]:
                _, d = m.fetch(ids[0].split()[-1], "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
                msgid = email.message_from_bytes(d[0][1]).get("Message-ID")
            todo.append((r, body, hi.group(1), msgid))
    finally:
        try:
            m.logout()
        except (imaplib.IMAP4.abort, OSError):
            pass
    sig_first = mkemail.SIG.strip().split()[0]
    today = date.today().isoformat()
    for r, body, first, msgid in todo:
        sent = date.fromisoformat(str(r["Date"])[:10])
        txt = body.with_name(f"{body.stem}_followup.txt")
        txt.write_text(FOLLOWUP.format(first=first, sent=f"{sent.day} {sent:%B}",
                                       role=r["Role"], me=sig_first))
        msg = mkemail.build(r["Email"], "Re: " + (r["Subject"] or r["Role"]), txt, None)
        if msgid:
            msg["In-Reply-To"] = msg["References"] = msgid
        txt.with_suffix(".eml").write_bytes(bytes(msg))
        if not send:
            print(f"draft: {r['Company']} | {r['Email']} | {'threaded' if msgid else 'NOT threaded'} | {txt.name}")
            continue
        mkemail.send(msg)
        print(f"sent:  {r['Company']} | {r['Email']}")
        jobs.add(jobs.OUT, {"Company": r["Company"], "Role": r["Role"], "Date": r["Date"],
                            "Notes": f"followup sent {today}. " + (r["Notes"] or "")})
    print(f"{len(rows)} rows owed a follow-up" + ("" if send else ", drafts only; add --send to deliver"))


def out_rows():
    import openpyxl
    if not jobs.XLSX.exists():
        return []
    ws = openpyxl.load_workbook(jobs.XLSX, read_only=True)[jobs.OUT]
    hdr = [c.value for c in next(ws.iter_rows(max_row=1))]
    return [dict(zip(hdr, r)) for r in ws.iter_rows(min_row=2, values_only=True) if r and r[1]]


def body_for(addr):
    """The .txt body behind the .eml that went to addr. mkemail writes the
    .eml next to its body with the same stem, so the To header finds both."""
    for eml in (profiles.DIR / "outreach").glob("*.eml"):
        if eml.stem.endswith("_followup"):
            continue
        head = eml.read_bytes()[:4000].decode("utf-8", "replace").lower()
        if re.search(rf"^to: .*{re.escape(addr)}", head, re.M):
            txt = eml.with_suffix(".txt")
            if txt.exists():
                return txt
    return None


def backup(entry):
    """"addr|First" -> (addr, "First"); a bare "addr" is the same person -> (addr, "")."""
    addr, _, first = entry.partition("|")
    return addr.strip().lower(), first.strip()


def emails(r):
    """Emails a row has cost: every address tried, plus a follow-up if one went."""
    return len(tried(r)) + ("followup sent" in (r.get("Notes") or "").lower())


def tried(r):
    t = (r.get("Tried") or "").split()
    return t if r["Email"] in t else t + [r["Email"]]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", nargs="?")
    p.add_argument("--retry", action="store_true")
    p.add_argument("--send", action="store_true")
    p.add_argument("--max", type=int, default=2, help="emails per row (addresses tried plus a follow-up) before giving up")
    p.add_argument("--days", type=int, default=21, help="how far back to read the inbox")
    a = p.parse_args()
    if a.cmd == "selfcheck":
        return selfcheck()
    if a.cmd == "followup":
        return followup(a.send)

    failed = dict(inbox_bounces(a.days))
    rows = out_rows()
    today = date.today().isoformat()
    for r in rows:
        addr = (r["Email"] or "").lower()
        if r["Status"] == "sent" and addr in failed:
            code = failed[addr]
            print(f"bounced: {r['Company']} | {addr} {code}")
            jobs.add(jobs.OUT, {"Company": r["Company"], "Role": r["Role"], "Status": "bounced",
                                "Address Verified": "bounced", "Tried": " ".join(tried(r)),
                                "Notes": f"bounced {today} {code}. " + (r["Notes"] or "")})
            r.update(Status="bounced", Tried=" ".join(tried(r)), bounce=code)
    # No bounce two days after sending is as close to "delivered" as SMTP
    # gets; Gmail's DSNs arrive within minutes. Only upgrades unverified or
    # blank, so a "verified" address keeps that stronger meaning.
    old = (date.today() - timedelta(days=2)).isoformat()
    ok = [{"Company": r["Company"], "Role": r["Role"], "Date": r["Date"],
           "Address Verified": "delivered"}
          for r in rows if r["Status"] == "sent" and str(r["Date"] or "")[:10] <= old
          and (r["Email"] or "").lower() not in failed
          and (r.get("Address Verified") or "unverified") == "unverified"]
    if ok:
        jobs.add(jobs.OUT, ok)
    rejections(a.days)
    msgs = inbox_headers(a.days)
    replies = match_replies(rows, msgs)
    for (co, role), note in replies.items():
        print(f"reply:   {co} | {note}")
    if replies:
        dates = {(r["Company"], r["Role"]): r["Date"] for r in rows}
        jobs.add(jobs.OUT, [{"Company": co, "Role": role, "Date": dates[(co, role)], "Reply": note, "Status": "replied"}
                            for (co, role), note in replies.items()])
    # Print only: an interview is recorded by hand with add-app --status
    # interview, because that row blocks every other application at the company.
    known = {company_key(r["Company"]) for r in jobs.app_rows() if r["Status"] in ("interview", "offer")}
    for frm, subj, when in msgs:
        subj = html.unescape(subj)
        text = re.sub(r"[^a-z0-9]", "", (frm + subj).lower())
        if (INTERVIEW.search(subj) and not RECEIPT.search(subj) and "@" in frm
                and not any(len(k) > 2 and k in text for k in known)):
            print(f"check:   possible interview, {when[:16]} {frm}: {subj[:80]}")
    if not a.retry:
        print("marked only. --retry builds the next address, --retry --send sends it.")
        return

    import mkemail
    for r in rows:
        if r["Status"] != "bounced" or not r["Email"]:
            continue
        seen = tried(r)
        why = None
        if (r.get("bounce", "").startswith("5.7") or "blocked" in (r["Notes"] or "").lower()
                or re.search(r"bounced \S+ 5\.7", r["Notes"] or "")):
            why = "policy block, the domain refuses the message not the mailbox"
        elif re.search(r"(?i)already left|has left|no longer (at|with)", r["Notes"] or ""):
            why = "the note says this person left, retarget a current human instead"
        elif emails(r) >= a.max:
            why = f"{emails(r)} emails sent for this role, the --max"
        greet = dict(backup(e) for e in (r.get("Backups") or "").split())
        nxt = [c for c in list(greet) + candidates(r["Contact Name"] or "", r["Email"].split("@")[1])
               if c not in seen]
        body = body_for(r["Email"]) or next((body_for(t) for t in seen if body_for(t)), None)
        why = why or ("no contact name to build an address from" if not nxt and not r["Contact Name"]
                      else "every address shape already tried" if not nxt
                      else "no body file found for the bounced .eml" if not body
                      else f"attachment {r['Attachment']} is missing"
                      if r["Attachment"] and not profiles.path(r["Attachment"]).exists() else None)
        if why:
            print(f"stop:  {r['Company']} | {r['Contact Name']} | {why}")
            continue
        new = nxt[0]
        if greet.get(new):  # a different person: same letter, their name on it
            txt = body.with_name(f"{body.stem}_try{len(seen) + 1}.txt")
            txt.write_text(re.sub(r"\AHi [^,\n]+,", f"Hi {greet[new]},", body.read_text()))
            body = txt
        m = mkemail.build(new, r["Subject"], body, r["Attachment"] and profiles.path(r["Attachment"]))
        eml = body.with_name(f"{body.stem}_try{len(seen) + 1}.eml")
        eml.write_bytes(bytes(m))
        if not a.send:
            print(f"draft: {r['Company']} | {new} (try {len(seen) + 1}) {eml.name}")
            continue
        mkemail.send(m)
        print(f"sent:  {r['Company']} | {new} (try {len(seen) + 1})")
        jobs.add(jobs.OUT, {"Company": r["Company"], "Role": r["Role"], "Email": new,
                            "Status": "sent", "Address Verified": "unverified",
                            "Tried": " ".join(seen + [new]),
                            "Notes": f"retry {len(seen) + 1} {today} after bounce. " + (r["Notes"] or "")})


def selfcheck():
    c = candidates("Jane Q. Doe", "example.org")
    assert c[:3] == ["jdoe@example.org", "jane@example.org", "jane.doe@example.org"], c
    assert len(c) == len(set(c)) == 10
    assert candidates("Cher", "x.com") == []
    dsn = (b"From: Mail Delivery Subsystem <mailer-daemon@googlemail.com>\r\n"
           b"X-Failed-Recipients: a@x.com\r\nMIME-Version: 1.0\r\n"
           b'Content-Type: multipart/report; report-type=delivery-status; boundary="B"\r\n\r\n'
           b"--B\r\nContent-Type: text/plain\r\n\r\nnot delivered\r\n"
           b"--B\r\nContent-Type: message/delivery-status\r\n\r\n"
           b"Reporting-MTA: dns; googlemail.com\r\n\r\n"
           b"Final-Recipient: rfc822; A@x.com\r\nAction: failed\r\nStatus: 5.1.1\r\n\r\n"
           b"Final-Recipient: rfc822; late@x.com\r\nAction: delayed\r\nStatus: 4.4.1\r\n\r\n"
           b"--B--\r\n")
    assert parse_bounce(dsn) == [("a@x.com", "5.1.1")], parse_bounce(dsn)
    plain = b"From: mailer-daemon@googlemail.com\r\nX-Failed-Recipients: b@y.com\r\n\r\nbounced\r\n"
    assert parse_bounce(plain) == [("b@y.com", "")]
    assert tried({"Email": "b@x.com", "Tried": "a@x.com"}) == ["a@x.com", "b@x.com"]
    assert tried({"Email": "a@x.com", "Tried": None}) == ["a@x.com"]
    assert backup("Bob@x.com|Bob") == ("bob@x.com", "Bob") and backup("a@x.com") == ("a@x.com", "")
    row = {"Company": "X", "Role": "R", "Email": "b@x.com", "Tried": "a@x.com", "Status": "sent", "Reply": None}
    hit = lambda msgs: match_replies([row], msgs)
    assert hit([("a@x.com", "hello", "d")]) == {("X", "R"): "d a@x.com: hello"}
    assert hit([("c@x.com", "Re: Analyst", "d")]) and not hit([("c@x.com", "New role", "d")])
    assert not hit([("no-reply@x.com", "Re: Analyst", "d")]) and not hit([("b@y.com", "Re: hi", "d")])
    assert not match_replies([dict(row, Reply="done")], [("b@x.com", "hi", "d")])
    assert not hit([("a@x.com", "Automatic reply: Analyst", "d")]) and not hit([("a@x.com", "Out of Office Re: R", "d")])
    assert company_key("Tailored Brands, Inc.") == "tailoredbrands" and company_key("Acme Co.") == "acme"
    t = date(2026, 11, 4)
    o = {"Company": "Acme", "Role": "R", "Status": "sent", "Reply": None, "Email": "a@acme.com",
         "Address Verified": "delivered", "Date": "2026-10-20", "Notes": ""}
    ok = [{"Company": "Acme", "Role": "R", "Status": "submitted"}]
    assert followup_rows([o], ok, "", t) == [o]
    assert not followup_rows([o], ok, "yourapplicationtoacme", t)
    assert not followup_rows([dict(o, Company="Zz")], [dict(ok[0], Company="Zz")], "noreplyacmecomwehavedecided", t)
    assert not followup_rows([dict(o, Date="2026-11-01")], ok, "", t)
    assert not followup_rows([dict(o, Notes="followup sent 2026-11-04")], ok, "", t)
    assert not followup_rows([o], [dict(ok[0], Status="interview")], "", t)
    assert not followup_rows([dict(o, Reply="x")], ok, "", t)
    assert not followup_rows([dict(o, Tried="b@acme.com a@acme.com")], ok, "", t)
    assert emails({"Email": "a@x.com", "Tried": "", "Notes": "followup sent 2026-11-04"}) == 2
    assert emails({"Email": "b@x.com", "Tried": "a@x.com", "Notes": ""}) == 2
    assert emails({"Email": "a@x.com", "Tried": None, "Notes": None}) == 1
    assert len(followup_rows([o, dict(o, Role="R2")], ok + [dict(ok[0], Role="R2")], "", t)) == 1
    assert not followup_rows([dict(o, Role="R2"), dict(o, Notes="followup sent 2026-11-04")],
                             ok + [dict(ok[0], Role="R2")], "", t)
    apps = {"forma": [{"Role": "Business Analyst", "Date": "2026-10-01"}],
            "urap": [{"Role": "Senior Data Analyst", "Date": "2026-10-01"}],
            "hirebox": [{"Role": "GTM Systems Analyst", "Date": "2026-10-01"}],
            "calmly": [{"Role": "Senior Product Data Scientist", "Date": "2026-10-01"}],
            "brightly": [{"Role": "Lead Product Analyst - Growth", "Date": "2026-10-01"},
                     {"Role": "Graduate Analyst", "Date": "2026-10-01"}],
            "grove health": [{"Role": "A Analyst", "Date": "2026-10-01"}, {"Role": "B Analyst", "Date": "2026-10-01"}],
            "state university school of medicine - eastside": [{"Role": "Data Analyst - School of Medicine, Eastside", "Date": "2026-09-20"}]}
    doms = {"hirebox": {"hireboxhq.com"}, "state university school of medicine - eastside": {"stateu.edu"}}
    for co in ("Forma", "Urap", "Hirebox", "Calmly", "Brightly", "Grove Health",
               "State University School of Medicine - Eastside"):
        for r in apps[plain_name(co)]:
            r["Company"] = co
    assert plain_name("Toyco, Inc.") == plain_name("Toyco") == "toyco"
    apps["summit rentals"] = [{"Company": "Summit Rentals, Inc.", "Role": "Reporting Analyst", "Date": "2026-09-01"},
                               {"Company": "Summit Rentals, Inc.", "Role": "Other Analyst Role", "Date": "2026-09-01"}]
    no = "we have decided not to move forward"
    mr = lambda f, s, b, d="2026-11-01": match_rejection(d, f, s, b, apps, doms)
    assert mr("x@northwind.com", "Important information about your application to Northwind Capital", no) == []
    assert mr("Calmly <no-reply@hireboxhq.com>", "Update from Calmly",
              no + " for the Senior Product Data Scientist role") == [("Calmly", "Senior Product Data Scientist")]
    assert mr("Brightly <n@brightly.jobs>", "Your application to Brightly for the role Lead Product Analyst - Growth", no) == \
        [("Brightly", "Lead Product Analyst - Growth")]
    assert mr("Grove <n@hireboxhq.com>", "Thank you for your interest in Grove Health", no) is None
    apps["brightly"][0]["Status"] = "rejected"
    assert mr("Brightly <n@brightly.jobs>", "Brightly application", no + " Lead Product Analyst - Growth") == []
    assert mr("Brightly <n@brightly.jobs>", "Brightly application", no) is None
    assert mr("Talent@stateu.edu", "Applicant Status Change",
              no + " Data Analyst - School of Medicine, Eastside") == [("State University School of Medicine - Eastside", "Data Analyst - School of Medicine, Eastside")]
    assert mr("Brightly <n@brightly.jobs>", "Thanks for applying to Brightly", "we received your application") == []
    assert mr("Brightly <n@brightly.jobs>", "Thank You for Applying", "unfortunately we cannot respond. If you are not selected") == []
    assert mr("summitrentals@myworkday.com", "Your application for Reporting Analyst", no) == \
        [("Summit Rentals, Inc.", "Reporting Analyst")]
    assert mr("Brightly <n@brightly.jobs>", "Brightly", no + " Lead Product Analyst - Growth", "2026-09-01") == []
    assert INTERVIEW.search("Interview invitation") and RECEIPT.search("Thank you for applying")
    print("ok")


if __name__ == "__main__":
    main()
