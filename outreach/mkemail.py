#!/usr/bin/env python3
"""Build one outreach email as a .eml draft, and optionally send it.

    python3 outreach/mkemail.py --to jane.doe@example.org \
        --subject "Data Engineer II, req 0000247737" \
        --body profiles/YourName/outreach/example_doe.txt \
        --attach profiles/YourName/resumes/Resume_YourName_Example.pdf

Writes the draft next to the body file. Add --send to deliver it.

The From address, the keychain item and the signature all come from
<profile>/signature.txt, so the wrong person never signs the mail: the header
lines are "from:" and "keychain:", then a line of "--", then the signature
block verbatim. The app password comes from that keychain item and is never
written or logged. GMAIL_APP_PASSWORD is a fallback. Replaces send_emails.py, whose
imports lived in a Downloads folder that is gone; that version is in profiles/archive/.
"""
import argparse, os, pathlib, smtplib, ssl, subprocess, sys
from datetime import date
from email.message import EmailMessage

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import profiles


def identity():
    """From address, keychain item and signature for the active profile."""
    path = profiles.DIR / "signature.txt"
    if not path.exists():
        sys.exit(f"{path} is missing. It needs a from: line, a keychain: line, "
                 "a line of --, then the signature block.")
    head, _, sig = path.read_text().partition("\n--\n")
    fields = dict(l.split(":", 1) for l in head.strip().splitlines())
    frm = fields.get("from", "").strip()
    item = fields.get("keychain", "").strip()
    if not frm or not item or not sig.strip():
        sys.exit(f"{path} needs a from:, a keychain: and a signature block.")
    return frm, item, "\n\n" + sig.strip() + "\n"


FROM, KEYCHAIN_ITEM, SIG = identity()
# Every message send() delivered: date, To, Subject, tab separated. main()
# refuses a second send of the same To and Subject, so an agent restarted
# between sending and recording the Outreach row cannot email the person twice.
LEDGER = profiles.DIR / "outreach" / "sent.log"


def inside(path, subs, suffix):
    """`path` resolved, or exit unless it is a `suffix` file under one of this
    profile's `subs` folders. This script is pre-approved and the agents that
    call it read untrusted posting text, so it must never be able to mail an
    arbitrary file (ATS-CREDENTIALS.txt, say) to an arbitrary address."""
    p = pathlib.Path(path).resolve()
    roots = [(profiles.DIR / s).resolve() for s in subs]
    if p.suffix.lower() != suffix or not any(r in p.parents for r in roots):
        sys.exit(f"{path}: must be a {suffix} file under {' or '.join(subs)}/ of the active profile")
    return p


def build(to, subject, body, attach):
    body = inside(body, ["outreach"], ".txt")
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = FROM, to, subject
    m.set_content(body.read_text().rstrip() + SIG)
    if attach:
        pdf = inside(attach, ["resumes", "base"], ".pdf")
        m.add_attachment(pdf.read_bytes(), maintype="application",
                         subtype="pdf", filename=pdf.name)
    return m


def password():
    """App password from the macOS keychain, the same item PhilanthroPy's
    send_one.py uses. GMAIL_APP_PASSWORD is a fallback for a non-mac shell.
    Never echo the return value."""
    try:
        r = subprocess.run(["security", "find-generic-password",
                            "-s", KEYCHAIN_ITEM, "-w"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            # Google shows an app password as four groups of four. Whichever way
            # it was pasted into the keychain, SMTP wants the 16 characters.
            return "".join(r.stdout.split())
    except FileNotFoundError:
        pass
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not pw:
        sys.exit(f"No credential. Expected keychain item {KEYCHAIN_ITEM!r} "
                 "(security find-generic-password -s "
                 f"{KEYCHAIN_ITEM}) or GMAIL_APP_PASSWORD in the environment.")
    return pw


def ledger_line(to, subject):
    return "\t".join(" ".join(str(v).split()).lower() for v in (to, subject))


def sent_before(to, subject):
    """The ledger date this To and Subject were already sent on, or None."""
    want = ledger_line(to, subject)
    for l in (LEDGER.read_text().splitlines() if LEDGER.exists() else []):
        when, _, rest = l.partition("\t")
        if rest == want:
            return when
    return None


def send(m):
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(FROM, password())
        s.send_message(m)
    with open(LEDGER, "a") as f:
        f.write(f"{date.today()}\t{ledger_line(m['To'], m['Subject'])}\n")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True, help="path to a plain text file")
    p.add_argument("--attach", help="path to a PDF")
    p.add_argument("--send", action="store_true")
    a = p.parse_args()

    m = build(a.to, a.subject, a.body, a.attach)
    out = pathlib.Path(a.body).with_suffix(".eml")
    out.write_bytes(bytes(m))
    print(f"draft: {out}  to: {a.to}  attachment: {pathlib.Path(a.attach).name if a.attach else 'none'}")
    if not a.send:
        print("not sent. re-run with --send to deliver.")
        return
    when = sent_before(a.to, a.subject)
    if when:
        sys.exit(f"not sent: {a.to} already got {a.subject!r} on {when} ({LEDGER.name}). "
                 "Record the Outreach row instead of sending again.")
    send(m)
    print("sent:", a.subject)


if __name__ == "__main__":
    main()
