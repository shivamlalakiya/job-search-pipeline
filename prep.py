#!/usr/bin/env python3
"""Batch the mechanical half of Workflow C, before the browser is touched.

    python3 prep.py <url> [<url> ...]
    python3 prep.py --from-xlsx Data_Jobs_HigherEd_30d_2026-09-09.xlsx
    python3 prep.py selfcheck

Per role it checks the posting is still live, names the ATS, pulls the whole
posting where that is possible without a browser, and runs the three filters
that decide whether the role is worth tailoring for: security clearance, a
licence the user does not hold, and the 60,000 floor. Writes one JSON brief
per role into applications/briefs/ and prints a verdict table.

What it deliberately does not do: tailor the resume or write the cover letter.
Both need judgment against profile.md, and both are the agent's job. This only
removes the fetching, parsing and arithmetic that were being redone by hand.
"""

import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

import ats

import profiles

ROOT = profiles.DIR
BRIEFS = ROOT / "applications" / "briefs"
FLOOR = 60000

# Set by the user 9 Sep 2026: any clearance requirement is out, including
# "able to obtain". The two exclusions are the false positives that a naive
# body search hit on the 9 Sep sweep, both recorded in CLAUDE.md.
CLEARANCE = re.compile(
    r"(?i)\b(security clearance|secret clearance|top secret|ts/sci|"
    r"public trust|suitability determination|polygraph)\b")
CLEARANCE_NOISE = re.compile(
    r"(?i)(employee polygraph protection act|"
    r"requires security clearance, interacts with)")

# Licences and credentials the user does not hold. A hit is a hard skip, so
# the acronyms are matched case-sensitively and only near the word that makes
# them a requirement. Matching `DO` case-insensitively on its own turns every
# "Do you have" into a skip, which is how the first version read the WGU req.
CREDENTIAL_WORD = re.compile(r"(?i)licen[cs]\w*|certification|credential|registration")
CREDENTIAL = re.compile(
    r"\b(RN|LPN|BSN|MD|DO|PharmD|CPA|PMP|LCSW|LPC|PE|P\.E\.)\b"
    r"|(?i:\b(registered nurse|licensed practical nurse|nursing|clinical|"
    r"medical|pharmacy|professional engineer)\b)")
# A driving licence is not a clinical credential and is not a disqualifier.
CREDENTIAL_NOISE = re.compile(r"(?i)driver'?s? licen[cs]e")
DOCTORATE = re.compile(r"(?i)\b(PhD|Ph\.D\.|doctorate|doctoral degree)\b[^.]{0,40}\brequired\b")

# "$91,000.00 - $136,400.00", "42.50/hour", "3,440 to 6,328 biweekly"
# "USD" between the numbers is Greenhouse's format ("$128,000 USD - $192,000 USD"),
# which the first version missed, leaving Okta's brief with no band on 24 Sep 2026.
MONEY = re.compile(r"\$?\s*([\d,]+(?:\.\d\d)?)\s*(?:USD\s*)?(?:-|to|–)\s*\$?\s*([\d,]+(?:\.\d\d)?)")
INTERVALS = {
    "hour": 2080, "hourly": 2080, "/hr": 2080, "per hour": 2080,
    "biweekly": 26, "bi-weekly": 26, "every two weeks": 26,
    "semi-monthly": 24, "semimonthly": 24, "twice a month": 24,
    "month": 12, "monthly": 12, "per month": 12,
    "year": 1, "yearly": 1, "annual": 1, "annually": 1, "per year": 1,
}


def annualize(amount, interval):
    """Pay quoted any of five ways, expressed as a yearly figure.

    The 9 Sep sweep understood hourly and monthly only, so UC Davis at
    "3,440 to 6,328 biweekly" was read as 3,440 a year and nearly dropped."""
    key = (interval or "year").strip().lower()
    for name, mult in INTERVALS.items():
        if name in key:
            return round(amount * mult)
    raise ValueError(f"unknown pay interval: {interval!r}")


def find_salary(text):
    """Lowest number of the first pay range in the text, annualised.

    A range only counts as pay when it carries a currency sign or a pay unit.
    "two (2) to five (5) years of relevant experience" is a range of numbers
    and not a salary, and reading it as one priced a Louisville req at 2 a
    year and skipped it under the floor on 10 Sep 2026."""
    for m in MONEY.finditer(text):
        span = m.group(0)
        tail = text[m.end():m.end() + 40].lower()
        if re.match(r"\s*\)?\s*(years?|yrs?|months?|weeks?|days?|hours? of)\b", tail):
            continue  # a duration, not money
        interval = next((n for n in INTERVALS if n in tail), None)
        if "$" not in span and interval is None:
            continue  # a bare pair of numbers, no reason to read it as pay
        low = float(m.group(1).replace(",", ""))
        if interval is None:
            # A currency sign but no unit. Nobody posts 42 a year, and nobody
            # posts 91,000 an hour, so the magnitude decides.
            interval = "hour" if low < 1000 else "year"
        annual = annualize(low, interval)
        if annual < 5000:
            continue  # not a real wage, keep looking
        return annual, interval
    return None, None


def live(url):
    """(status, page title). GET rather than HEAD, and read the title.

    SilkRoad answers HEAD with 404 for a posting that GET serves as 200, and
    it also answers 200 for a job id that does not exist. The only thing that
    separates a live req from a missing one there is that the missing one's
    title has no job in it, so the title comes back with the status."""
    req = urllib.request.Request(url, headers={"User-Agent": ats.UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            head = r.read(200000).decode("utf-8", "replace")
            return r.status, page_title(head)
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError):
        return 0, ""


def page_title(markup):
    m = re.search(r"(?is)<title>(.*?)</title>", markup)
    return " ".join(ats.strip_tags(m.group(1)).split()) if m else ""


def title_is_empty(title):
    """A title with nothing in it but separators and the employer's name is
    what SilkRoad serves for a req that no longer exists."""
    return not re.sub(r"[-|–·,\s]", "", title.split("-")[0])


def find_credential(text):
    """The snippet asserting a credential requirement, or None.

    A credential only counts when the acronym or the profession sits next to
    the word that makes it a requirement, so `DO` in "Do you have" and a
    driving licence both fall through."""
    hit = DOCTORATE.search(text)
    if hit and not re.search(r"(?i)preferred|not required", hit.group(0)):
        return " ".join(hit.group(0).split())
    for m in CREDENTIAL_WORD.finditer(text):
        window = text[max(0, m.start() - 60):m.end() + 60]
        if CREDENTIAL_NOISE.search(window):
            continue
        if CREDENTIAL.search(window):
            return " ".join(window.split())
    return None


def screen(text):
    """The three filters, as a list of reasons to skip. Empty means proceed."""
    reasons = []
    clean = CLEARANCE_NOISE.sub("", text)
    hit = CLEARANCE.search(clean)
    if hit:
        reasons.append(f"clearance: {hit.group(0)}")
    hit = find_credential(text)
    if hit:
        reasons.append(f"credential: {hit}")
    low, interval = find_salary(text)
    if low is not None and low < FLOOR:
        reasons.append(f"pays {low:,}/year ({interval}), under the {FLOOR:,} floor")
    return reasons, low, interval


def already_applied(url):
    """The tracker's status for this apply URL, if it holds one.

    Without this check a brief says `apply` for a role that went in days ago,
    which reads as "not yet applied" and invites a duplicate submission. That
    happened on 10 Sep 2026 with the WGU req."""
    path = ROOT / "tracker.xlsx"
    if not path.exists():
        return None
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True)["Applications"]
    for r in ws.iter_rows(min_row=2, values_only=True):
        if len(r) > 7 and r[4] and str(r[4]).split("?")[0] == url.split("?")[0]:
            return f"{r[7]} on {r[0]}"
    return None


def brief(url):
    status, title = live(url)
    out = {"url": url, "ats": ats.detect(url), "status": status, "page_title": title}
    seen = already_applied(url)
    if seen:
        out["tracker"] = seen
        if seen.startswith(("submitted", "rejected", "interview", "offer")):
            out["verdict"] = f"already {seen}"
            return out
    if out["status"] in (404, 410):
        out["verdict"] = f"dead ({out['status']})"
        return out
    if out["status"] != 200:
        out["verdict"] = f"check in browser (HTTP {out['status']})"
        return out
    if title and title_is_empty(title):
        out["verdict"] = f"likely dead, the page has no job in its title: {title!r}"
        return out
    if out["ats"] != "workday" and "linkedin.com/jobs/view/" not in url:
        out["verdict"] = ("park: account-gated " + out["ats"]
                          if ats.needs_account(url, profiles.accounts()) else "needs the browser")
        return out
    try:
        if out["ats"] == "workday":
            post = ats.workday_posting(url)
        else:
            post = ats.linkedin_posting(url)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as e:
        out["verdict"] = f"fetch failed: {e}"
        return out
    out.update({k: v for k, v in post.items() if k != "text"})
    reasons, low, interval = screen(post["text"])
    out["salary_low_annual"] = low
    out["salary_interval"] = interval
    out["skip_reasons"] = reasons
    if reasons:
        out["verdict"] = "skip: " + "; ".join(reasons)
    elif ats.needs_account(url, profiles.accounts()):
        # Checked after the filters so a role that fails them is still a plain
        # skip. Parked means: do not tailor, do not spawn an apply agent, put it
        # on the user's signup list (jobs.py parked).
        out["verdict"] = f"park: account-gated {out['ats']} on {ats.host(url)}"
    else:
        out["verdict"] = "apply"
    out["text"] = post["text"]
    return out


def slug(b):
    base = f"{b.get('title') or b['url'].rstrip('/').split('/')[-1]}_{b.get('req') or ''}"
    return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")[:80]


def run(urls):
    BRIEFS.mkdir(parents=True, exist_ok=True)
    for url in urls:
        b = brief(url)
        path = BRIEFS / (slug(b) + ".json")
        path.write_text(json.dumps(b, indent=2) + "\n")
        pay = f"{b['salary_low_annual']:,}" if b.get("salary_low_annual") else "-"
        print(f"{b['verdict']:<28} {b.get('title') or url[:40]:<42} "
              f"from {pay:>9}  closes {b.get('end_date') or '-'}  {path.name}")


def from_xlsx(path, sheet=None):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    col = hdr.index("Apply URL")
    return [r[col] for r in ws.iter_rows(min_row=2, values_only=True) if r[col]]


def selfcheck():
    assert annualize(42.50, "per hour") == 88400
    assert annualize(3440, "biweekly") == 89440
    assert annualize(6328, "semi-monthly") == 151872
    assert annualize(7500, "month") == 90000
    assert annualize(91000, "annually") == 91000

    assert find_salary("Pay Range: $91,000.00 - $136,400.00 annually")[0] == 91000
    assert find_salary("$3,440 to $6,328 biweekly")[0] == 89440
    # no unit next to the range, so the magnitude decides
    assert find_salary("Salary: $22.00 - $28.00")[0] == 45760
    assert find_salary("no numbers here") == (None, None)
    # ranges that are not money, which cost a Louisville req a false skip
    assert find_salary("two (2) to five (5) years of relevant experience") == (None, None)
    assert find_salary("Requires 3 to 5 years of experience.") == (None, None)
    assert find_salary("Compensation will be commensurate to candidate "
                       "experience.") == (None, None)
    assert find_salary("Supervises 10 - 15 staff.") == (None, None)
    # a real band later in a document that opens with an experience range
    assert find_salary("2 to 4 years required. Pay Range: $70,512 - $85,000 "
                       "annually.")[0] == 70512
    assert find_salary("Hourly rate 22.00 - 28.00 per hour")[0] == 45760
    assert find_salary("is between:: $128,000 USD - $192,000 USD")[0] == 128000

    # SilkRoad serves 200 for a job id that does not exist; only the title differs
    assert title_is_empty("-  - Boston University")
    assert not title_is_empty("Senior Research Computing Applications - Boston University")

    # the two false positives that a naive clearance search got wrong
    assert screen("This employer complies with the Employee Polygraph "
                  "Protection Act.")[0] == []
    assert screen("Background checks apply to work that engages in law "
                  "enforcement, requires security clearance, interacts with "
                  "WSU students.")[0] == []
    # and the real thing, including able-to-obtain
    assert screen("Must be able to obtain a Secret clearance.")[0]
    assert screen("Requires an active TS/SCI with polygraph.")[0]
    assert screen("Requires an active NJ RN licence.")[0]
    assert screen("Current registered nurse license in the state of NJ.")[0]
    assert screen("CPA certification required.")[0]
    assert screen("PhD in statistics required.")[0]
    # the ordinary English word that the first version skipped a good role on
    assert find_credential("Do you have experience with dbt? A license for "
                           "Tableau is provided.") is None
    assert find_credential("Valid driver's license required.") is None
    assert find_credential("PhD preferred but not required for this role.") is None
    assert screen("Hourly rate: $22.00 - $26.00 per hour")[0], "should fail the floor"
    assert screen("Pay Range: $91,000.00 - $136,400.00 per year")[0] == []
    print("ok")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "selfcheck":
        selfcheck()
        return 0
    if argv[0] == "--from-xlsx":
        urls = from_xlsx(argv[1], argv[2] if len(argv) > 2 else None)
    else:
        urls = argv
    run(urls)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
