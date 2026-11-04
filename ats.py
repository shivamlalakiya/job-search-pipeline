#!/usr/bin/env python3
"""Identify the ATS behind a job URL, and pull the posting without a browser.

    python3 ats.py <url> [<url> ...]   brief per URL
    python3 ats.py --text <url>        full posting text, for tailoring against
    python3 ats.py find "<company>" "<title>" [slug ...]
                                       search the company's public job board APIs
    python3 ats.py selfcheck           offline checks

Workday is the only one that gives up its posting over an API. For the rest
this prints the ATS name so Workflow A step 4 does not have to guess.
"""

import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36"

# host substring -> ATS name. First match wins, so keep the specific ones first.
ATS_HOSTS = [
    ("myworkdayjobs.com", "workday"),
    ("myworkdaysite.com", "workday"),
    ("job-boards.greenhouse.io", "greenhouse"),
    ("boards.greenhouse.io", "greenhouse"),
    ("greenhouse.io", "greenhouse"),
    ("gh_jid=", "greenhouse"),  # careers sites that embed a Greenhouse form
    ("jobs.lever.co", "lever"),
    ("jobs.ashbyhq.com", "ashby"),
    ("oraclecloud.com", "oracle cloud hcm"),
    ("icims.com", "icims"),
    ("taleo.net", "taleo"),
    ("smartrecruiters.com", "smartrecruiters"),
    ("successfactors.com", "successfactors"),
    ("successfactors.eu", "successfactors"),
    ("erecruit", "peoplesoft"),
    ("peoplesoft", "peoplesoft"),
    ("interfolio.com", "interfolio"),
    ("jobvite.com", "jobvite"),
    ("workforcenow.adp.com", "adp"),
    ("myjobs.adp.com", "adp"),
    ("pageuppeople.com", "pageup"),
    ("ultipro.com", "ultipro"),
    ("ukg.net", "ultipro"),
    ("saashr.com", "ultipro"),
    ("avature.net", "avature"),
    ("hr.cloud.sap", "successfactors"),
    ("peopleadmin.com", "peopleadmin"),
    ("dayforcehcm.com", "dayforce"),
    ("paylocity.com", "paylocity"),
    ("bamboohr.com", "bamboohr"),
    ("rippling.com", "rippling"),
    ("applytojob.com", "jazzhr"),
    ("workable.com", "workable"),
    ("higheredjobs.com", "higheredjobs aggregator"),
    ("linkedin.com", "linkedin aggregator"),
    ("indeed.com", "indeed aggregator"),
    ("tekjobs.net", "tekjobs aggregator"),
    ("fetchjobs.co", "fetchjobs aggregator"),
    ("sundayy.com", "sundayy aggregator"),
    ("torentify.com", "torentify aggregator"),
    ("adzuna.com", "adzuna aggregator"),
    ("jometer.com", "jometer aggregator"),
]

# ATSs that will not take an application without a candidate account and a
# new password, which an agent cannot create (see the memory note and
# docs/tooling.md). Measured on one profile's tracker 24 Sep 2026: Workday was 89
# account walls against 4 submissions, and every one of those walls was found
# only after the resume and cover letter had been tailored and a browser agent
# had spent its setup. Knowing it from the URL lets prep park the row for the
# user's batch signup instead. Dayforce and Paylocity are left out on purpose:
# both have gone through without an account on some tenants.
# Avature added 24 Sep 2026: every tenant in one profile's LOG (L'Oreal, CBRE, Intuit,
# Koch, Bain, Lenovo) was a login wall.
ACCOUNT_ATS = {"workday", "icims", "taleo", "successfactors", "oracle cloud hcm",
               "ultipro", "peopleadmin", "peoplesoft", "adp", "avature"}


def host(url):
    return (url.split("/")[2] if "://" in url else url).lower()


def needs_account(url, accounts=()):
    """True when the URL's ATS gates applying behind a new account and the
    user has not already made one on that host. `accounts` is the host list
    from <profile>/accounts.txt."""
    return detect(url) in ACCOUNT_ATS and host(url) not in accounts


# https://{tenant}.wd{N}.myworkdayjobs.com[/{lang}]/{site}/job/{location}/{slug}
WORKDAY_URL = re.compile(
    r"https?://(?P<tenant>[^.]+)\.wd\d+\.myworkdayjobs\.com/"
    r"(?:(?P<lang>[a-z]{2}-[A-Z]{2})/)?"
    r"(?P<site>[^/]+)/job/(?P<rest>.+?)/?$"
)


def detect(url):
    host = url.split("/")[2].lower() if "://" in url else url.lower()
    for needle, name in ATS_HOSTS:
        # an aggregator only by host: employer URLs carry utm_source=linkedin.com
        if needle in host or (needle in url.lower() and not name.endswith("aggregator")):
            return name
    return "unknown"


def workday_cxs_url(url):
    """Turn a Workday posting URL into its CxS API URL, or None."""
    m = WORKDAY_URL.match(url.split("?")[0])
    if not m:
        return None
    return "https://{t}.wd{n}.myworkdayjobs.com/wday/cxs/{t}/{s}/job/{r}".format(
        t=m.group("tenant"),
        n=re.search(r"\.wd(\d+)\.", url).group(1),
        s=m.group("site"),
        r=m.group("rest"),
    )


def strip_tags(markup):
    markup = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>", "\n", markup)
    markup = re.sub(r"(?i)<li[^>]*>", "- ", markup)
    text = html.unescape(re.sub(r"<[^>]+>", "", markup))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def workday_posting(url):
    data = fetch_json(workday_cxs_url(url))
    info = data.get("jobPostingInfo", {})
    return {
        "title": info.get("title"),
        "req": info.get("jobReqId"),
        "posted": info.get("startDate"),
        "type": info.get("timeType"),
        "location": info.get("location"),
        "remote": info.get("remoteType"),
        "end_date": info.get("endDate"),
        "text": strip_tags(info.get("jobDescription", "")),
    }


def linkedin_posting(url):
    """The guest job-posting endpoint, which serves the whole description unauthenticated.

    LinkedIn is not an ATS, so this is only a way to read the posting text for
    tailoring and for the prep.py filters. The employer's own apply URL is not
    in this payload, so the browser still has to resolve it before applying."""
    job_id = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", url)
    if not job_id:
        raise ValueError(f"no LinkedIn job id in {url}")
    guest = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id.group(1)}"
    req = urllib.request.Request(guest, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        markup = r.read().decode("utf-8", "replace")
    body = re.search(r'(?s)show-more-less-html__markup[^>]*>(.*?)</div>', markup)
    if not body:
        raise ValueError(f"no description in the guest payload for {url}")
    def one(pattern):
        m = re.search(pattern, markup, re.S)
        return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else None
    return {
        "title": one(r'(?s)<h2[^>]*top-card-layout__title[^>]*>(.*?)</h2>'),
        "req": job_id.group(1),
        "posted": one(r'(?s)posted-time-ago__text[^>]*>(.*?)</span>'),
        "company": one(r'(?s)topcard__org-name-link[^>]*>(.*?)</a>'),
        "location": one(r'(?s)topcard__flavor--bullet[^>]*>(.*?)</span>'),
        "text": strip_tags(body.group(1)),
    }


# Public, unauthenticated job-board APIs: {slug} is the company's board name.
# Written 24 Sep 2026 after 27 of one day's rows sat `blocked` because the
# employer URL was looked for with WebFetch, which cannot render the JS boards
# these ATSs serve. Their JSON APIs need no browser at all.
BOARDS = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
     lambda d: [(j["title"], j["absolute_url"]) for j in d.get("jobs", [])]),
    ("lever", "https://api.lever.co/v0/postings/{slug}?mode=json",
     lambda d: [(j["text"], j["hostedUrl"]) for j in d]),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}",
     lambda d: [(j["title"], j["jobUrl"]) for j in d.get("jobs", [])]),
    ("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
     lambda d: [(j["name"], f"https://jobs.smartrecruiters.com/{j['company']['identifier']}/{j['id']}")
                for j in d.get("content", [])]),
]


def slugs(company):
    """Board names worth trying for a company name, most likely first."""
    words = re.sub(r"(?i)\b(inc|llc|ltd|corp|corporation|co|company|the|group|holdings)\b\.?", " ",
                   company.split("|")[0].split("(")[0])
    words = re.findall(r"[a-z0-9]+", words.lower())
    # Ashby keeps the display name as the slug, spaces and all ("Blacksmith Agency")
    raw = urllib.parse.quote(company.split("|")[0].split("(")[0].strip())
    out = ["".join(words), "-".join(words), words[0] if words else "", raw]
    return [s for i, s in enumerate(out) if s and s not in out[:i]]


def title_score(want, got):
    a, b = set(re.findall(r"[a-z]+", want.lower())), set(re.findall(r"[a-z]+", got.lower()))
    return len(a & b) / max(len(a), 1)


def find(company, title, extra=()):
    """[(score, ats, title, url)] for postings on any public board whose
    title shares at least 60 percent of the wanted title's words."""
    hits = []
    for slug in list(extra) + slugs(company):
        for name, api, parse in BOARDS:
            try:
                jobs = parse(fetch_json(api.format(slug=slug), timeout=8))  # most slugs are misses
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError):
                continue
            for t, u in jobs:
                sc = title_score(title, t)
                if sc >= 0.6:
                    hits.append((round(sc, 2), name, t, u))
        if hits:
            break
    return sorted(hits, reverse=True)


def report(url, full_text=False):
    ats = detect(url)
    print(f"\n{url}\n  ats: {ats}")
    if ats != "workday":
        if ats.endswith("aggregator"):
            print("  the employer's own posting is behind this one, resolve it first")
        print("  no API, open it in the browser")
        return
    print(f"  cxs: {workday_cxs_url(url)}")
    try:
        post = workday_posting(url)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as e:
        print(f"  fetch failed: {e}")
        return
    for k in ("title", "req", "posted", "end_date", "type", "location", "remote"):
        if post.get(k):
            print(f"  {k}: {post[k]}")
    print(f"  description: {len(post['text'])} chars")
    if full_text:
        print("\n" + post["text"])


def selfcheck():
    cases = [
        ("https://wgu.wd5.myworkdayjobs.com/External/job/Salt-Lake-City-UT/IAR-Senior-Data-Analyst_JR-025802-1", "workday"),
        ("https://umsystem.wd1.myworkdayjobs.com/en-US/UMSystem/job/Rolla/Data-Analyst-II_JR12345", "workday"),
        ("https://job-boards.greenhouse.io/linksquares/jobs/4123456", "greenhouse"),
        ("https://jobs.lever.co/example/abc-123", "lever"),
        ("https://www.tekjobs.net/job/123", "tekjobs aggregator"),
        ("https://instacart.careers/job/?gh_jid=8115836", "greenhouse"),
        ("https://careers-example.icims.com/jobs/1234/data-analyst/job", "icims"),
        ("https://erecruit.umsystem.edu/psc/tamext/CAREERS/HRMS/c/HRS_HRAM.HRS_CE.GBL", "peoplesoft"),
        ("https://etsu.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/1282", "oracle cloud hcm"),
        ("https://www.higheredjobs.com/search/details.cfm?JobCode=179550511", "higheredjobs aggregator"),
        ("https://example.edu/careers/12345", "unknown"),
    ]
    for url, want in cases:
        got = detect(url)
        assert got == want, f"{url}: detected {got}, wanted {want}"

    assert workday_cxs_url(cases[0][0]) == (
        "https://wgu.wd5.myworkdayjobs.com/wday/cxs/wgu/External/job/"
        "Salt-Lake-City-UT/IAR-Senior-Data-Analyst_JR-025802-1"
    )
    # the language segment belongs to the page URL, never to the API URL
    assert workday_cxs_url(cases[1][0]) == (
        "https://umsystem.wd1.myworkdayjobs.com/wday/cxs/umsystem/UMSystem/job/"
        "Rolla/Data-Analyst-II_JR12345"
    )
    assert workday_cxs_url("https://jobs.lever.co/example/abc-123") is None

    assert needs_account(cases[0][0])
    assert not needs_account(cases[0][0], accounts={"wgu.wd5.myworkdayjobs.com"})
    assert not needs_account(cases[2][0]), "greenhouse takes a guest application"

    assert strip_tags("<p>One</p><ul><li>Two</li></ul>") == "One\n- Two"
    assert slugs("Shake Shack Inc.")[:3] == ["shakeshack", "shake-shack", "shake"]
    assert slugs("Blacksmith Agency")[-1] == "Blacksmith%20Agency"
    assert slugs("OLIVER | The Brandtech Group")[0] == "oliver"
    assert title_score("Senior Data Analyst", "Senior Data Analyst, Payments") == 1
    assert title_score("Senior Data Analyst", "Account Executive") == 0
    print("ok")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "selfcheck":
        selfcheck()
        return 0
    if argv[0] == "find":
        hits = find(argv[1], argv[2], argv[3:])
        for sc, name, t, u in hits[:5]:
            print(f"{sc:.2f}  {name:<15} {t}  {u}")
        if not hits:
            print(f"no match on greenhouse, lever, ashby or smartrecruiters under {slugs(argv[1]) + argv[3:]}")
        return 0 if hits else 1
    full_text = argv[0] == "--text"
    urls = argv[1:] if full_text else argv
    for url in urls:
        report(url, full_text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
