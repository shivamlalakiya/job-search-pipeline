"""Which person's folder the tools read and write.

Every personal file lives under profiles/<name>/: profile.md, base/, resumes/,
applications/, outreach/, confirmations/, tracker.xlsx, answers.json, LOG.md
and ATS-CREDENTIALS.txt. The scripts themselves are shared. The file PROFILE at
the repo root names the one that is active, and there is deliberately no
default: an unnamed profile would file one person's application under another's name.

Switch with `python3 jobs.py profile <name>`, never by hand, because the
Playwright browser profile and the secrets file are named in .mcp.json and have
to move at the same time. Changing .mcp.json needs a Claude Code restart.
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).parent
MARKER = ROOT / "PROFILE"
PROFILES = ROOT / "profiles"


def active():
    if not MARKER.exists():
        sys.exit("no PROFILE file at the repo root. Write one name into it, "
                 "e.g. printf 'YourName\\n' > PROFILE")
    name = MARKER.read_text().strip()
    d = PROFILES / name
    if not name or not d.is_dir():
        sys.exit(f"PROFILE says {name!r} but {d} is not a directory")
    return name, d



NAME, DIR = active()
# An empty <profile>/autosend file means this person's standing permission
# covers derived addresses, so the bulk run's bounce retry sends, not drafts.
AUTOSEND = (DIR / "autosend").exists()


def path(rel):
    """A tracker path such as a Resume or Attachment cell. Rows written before
    the profiles/ move (4 Nov 2026) say "Name/resumes/x.pdf", newer ones
    "profiles/Name/resumes/x.pdf"; both are relative to the repo root."""
    p = ROOT / rel
    return p if p.exists() else PROFILES / rel


def accounts():
    """Hosts where this person already holds an ATS account, one per line in
    profiles/<name>/accounts.txt as "<host> [<secrets key>]". The user adds a line after creating an account, which
    is what lets an account-gated row leave the parked list."""
    f = DIR / "accounts.txt"
    if not f.exists():
        return set()
    return {l.split()[0].lower() for l in f.read_text().splitlines()
            if l.strip() and not l.startswith("#")}


def account_key(host):
    """The --secrets key an account on this host was created with: the second
    word of its accounts.txt line, ALL_ATS_PASSWORD when the line has none
    (the user's own signups)."""
    f = DIR / "accounts.txt"
    for l in (f.read_text().splitlines() if f.exists() else []):
        w = l.split()
        if w and not l.startswith("#") and w[0].lower() == host.lower():
            return w[1] if len(w) > 1 else "ALL_ATS_PASSWORD"
    return None
