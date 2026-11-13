#!/usr/bin/env python3
"""Build a job list of roles the active profile fits closely, before anyone
tailors or applies. Workflow B's search step, scripted.

    python3 scout.py "marketing analyst" "data analyst" [--days 1] [--pages 3]
                     [--min-fit 60] [--max-years 5] [--location "United States"]
    python3 scout.py selfcheck

Per keyword it reads LinkedIn's public jobs-guest search (no login), drops
anything already on the tracker, gates the title (analytics work at her level:
no staff, principal, director or head roles, no engineering, design or writing),
then runs prep.brief on each survivor: liveness, ATS, the clearance, credential
and pay-floor filters, and a brief with the full posting text. On that text it
scores fit as the share of the tools the posting names that the base resume
already holds, and drops a posting asking for more years than --max-years.

Strict on purpose. Written 24 Sep 2026 when the user asked for a list of only
closely suitable roles: the apply stage never skips on fit (docs/workflows.md
"Skip only on these"), so fit is decided here, once, and not again.

Writes profiles/<Profile>/scout/<Profile>_Jobs_<date>.xlsx, sheet "Shortlist", with an Apply URL column
that `prep.py --from-xlsx` and `jobs.py add-app` rows work from. With --track,
also adds each shortlisted role to the tracker as `found`, so `jobs.py resolve`
picks it up. Contacts are found per role after submission by the outreach
agent, which ranks up to five addresses (docs/outreach.md).
"""
import argparse, html, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import ats, jobs, prep, profiles

SEARCH = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
          "?keywords={kw}&location={loc}&f_TPR=r{secs}&start={start}")
# Tools a posting may name. Her tools are the ones her base resume mentions.
VOCAB = ["sql", "python", "tableau", "power bi", "looker", "excel", "ga4", "google analytics",
         "adobe analytics", "google tag manager", "gtm", "bigquery", "snowflake", "redshift",
         "databricks", "dbt", "airflow", "spark", "sas", "alteryx", "hubspot", "marketo",
         "salesforce", "amplitude", "mixpanel", "optimizely", "adobe target", "segment",
         "google ads", "meta ads", "seo", "sem", "a/b test", "attribution", "marketing mix",
         "mmm", "incrementality", "etl", "statistics", "regression", "machine learning", "aws",
         "azure", "gcp", "jira", "power query", "dax", "vba", "sheets", "data studio",
         "looker studio", "qualtrics", "sprinklr", "braze", "iterable", "klaviyo"]
TITLE_OK = re.compile(r"(?i)analy|insight|data|measurement|business intelligence|\bbi\b|reporting"
                      r"|growth|crm|seo|sem|ppc|performance marketing|marketing operations")
TITLE_NO = re.compile(r"(?i)\b(staff|principal|director|head|vp|vice president|chief|intern"
                      r"|engineer|developer|architect|designer|writer|nurse"
                      r"|account executive|sales rep|recruiter|manager|content|copywriter|editor)\b")
STAFFING = re.compile(r"(?i)staffing|recruit|talent (solutions|partners)|consultancy services|"
                      r"\bour client\b|on behalf of (our|a) client|harnham|robert half|insight global|"
                      r"teksystems|randstad|kforce|aerotek|adecco|jobot|dice\b|cybercoders|apex systems|"
                      r"motion recruitment|beacon hill|lhh\b|hays\b|michael page|korn ferry|jobgether|"
                      r"swooped|talentlinc|dexian|abilitylinks|workgenius|lensa|jooble|hirebus|sundayy|jobright|niyam|brooksource|revops report|magenta search|joveo|secondwind|yochana|\bkelly\b|haystack|blacksmith agency")
YEARS = re.compile(r"(?i)(\d{1,2})\s*\+?\s*(?:-\s*\d+\s*)?years?[^.]{0,60}experience")
# "With over 15 years of industry experience, Acme serves..." is the company's
# age, not the ask, and read as 15 it dropped a 2-years role. A bare number only
# counts in a sentence that asks for something; "3+" and "5-7" always do.
YEARS_ASK = re.compile(r"(?i)requir|minimum|must|need|prefer|qualif|you have|you bring")


def cards(markup):
    """[(job id, title, company, location)] from one search page."""
    out = []
    for c in markup.split("<li>")[1:]:
        jid = re.search(r"jobPosting:(\d+)", c)
        t = re.search(r'base-search-card__title">\s*(.*?)\s*</h3>', c, re.S)
        co = re.search(r'base-search-card__subtitle">.*?>\s*(.*?)\s*</a>', c, re.S)
        loc = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', c, re.S)
        if jid and t:
            # Titles and companies reach agent prompts and quoted shell arguments
            # (`add-app --role "..."`), so drop the characters that can end a
            # quote or start a substitution, and cap the length.
            clean = lambda m: re.sub(r'[`"$\\\x00-\x1f]', "", html.unescape(
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))))).strip()[:150] if m else ""
            out.append((jid.group(1), clean(t), clean(co), clean(loc)))
    return out


def search(kw, loc, days, pages):
    found = []
    for p in range(pages):
        url = SEARCH.format(kw=urllib.parse.quote(kw), loc=urllib.parse.quote(loc),
                            secs=days * 86400, start=len(found))  # pages hold 10 cards, not 25
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ats.UA}),
                                        timeout=20) as r:
                page = cards(r.read().decode("utf-8", "replace"))
        except Exception as e:  # 429 once LinkedIn has had enough; keep what we have
            print(f"  {kw!r} page {p}: {e}", file=sys.stderr)
            break
        if p == 0 and not page:
            # cards() reads LinkedIn's class names; a markup change looks exactly
            # like "no jobs" and campaign.sh would loop on it without a word
            print(f"  {kw!r}: page 0 parsed to zero cards; LinkedIn's markup may have changed", file=sys.stderr)
        found += page
        if len(page) < 10:
            break
        time.sleep(1.5)
    return found


def fit(text, mine):
    """(score 0-100, matched, missing) over the VOCAB tools the posting names."""
    low = text.lower()
    named = [v for v in VOCAB if re.search(rf"(?<![a-z]){re.escape(v)}(?![a-z])", low)]
    have = [v for v in named if v in mine]
    return (round(100 * len(have) / len(named)) if named else 0), have, [v for v in named if v not in mine]


def years_asked(text):
    sentence = lambda m: re.split(r"[.\n]", text[:m.start()])[-1] + re.split(r"[.\n]", text[m.start():])[0]
    asked = (m for m in YEARS.finditer(text)
             if re.search(r"[+-]", m.group(0)[:m.group(0).lower().index("year")])
             or YEARS_ASK.search(sentence(m)))
    return max((int(m.group(1)) for m in asked if int(m.group(1)) < 20), default=0)


def careers_url(company, title):
    """The same role on the company's own public job board, or None. User
    preference 3 Oct 2026: a careers link beats the LinkedIn one wherever it
    exists. Only an identical set of title words counts, so "Data Analyst II"
    never lands on "Data Analyst III"; anything else stays on LinkedIn for
    `jobs.py resolve`."""
    words = lambda t: set(re.findall(r"[a-z0-9]+", t.lower()))
    return next((u for _, _, t, u in ats.find(company, title) if words(t) == words(title)), None)


def main(argv):
    sys.stdout.reconfigure(line_buffering=True)  # campaign.log showed nothing until each keyword ended
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("keywords", nargs="+")
    a.add_argument("--location", default="United States")
    a.add_argument("--days", type=int, default=1)
    a.add_argument("--pages", type=int, default=3)
    a.add_argument("--min-fit", type=int, default=60)
    a.add_argument("--max-years", type=int, default=5)
    a.add_argument("--track", action="store_true", help="add the shortlist to the tracker as found")
    a = a.parse_args(argv)

    base = (profiles.DIR / "base" / "resume_base.tex").read_text().lower()
    mine = {v for v in VOCAB if re.search(rf"(?<![a-z]){re.escape(v)}(?![a-z])", base)}
    seen = " ".join(f"{r['Apply URL']} {r['Notes']}" for r in jobs.app_rows())
    have = {(r["Company"].lower(), r["Role"].lower()) for r in jobs.app_rows()}

    hits, dropped = {}, {"on tracker": 0, "title": 0, "staffing": 0}
    for kw in a.keywords:
        for jid, title, co, loc in search(kw, a.location, a.days, a.pages):
            if jid in hits or any((title, co) == h[:2] for h in hits.values()):
                continue  # one req listed per city is one application
            if jid in seen or (co.lower(), title.lower()) in have:
                dropped["on tracker"] += 1
            elif not TITLE_OK.search(title) or TITLE_NO.search(title):
                dropped["title"] += 1
            elif STAFFING.search(co):
                dropped["staffing"] += 1
            else:
                hits[jid] = (title, co, loc)
    print(f"{len(hits)} candidates after title and tracker gates; dropped {dropped}")

    def judge(item):
        jid, (title, co, loc) = item
        for wait in (0, 15, 45):  # LinkedIn's guest endpoint 429s in bursts
            time.sleep(wait)
            b = prep.brief(f"https://www.linkedin.com/jobs/view/{jid}/")
            if "429" not in b["verdict"]:
                break
        if not b.get("text"):
            return dict(jid=jid, title=title, company=co, location=loc, fit=0, have=[], miss=[],
                        years=0, pay=None, why=b["verdict"])
        (prep.BRIEFS / (prep.slug(b) + ".json")).write_text(__import__("json").dumps(b, indent=2) + "\n")
        score, got, miss = fit(b["text"], mine)
        yrs = years_asked(b["text"])
        why = (b["verdict"] if b["verdict"].startswith("skip") else
               "staffing agency" if STAFFING.search(b["text"][:600]) else
               f"asks {yrs} years" if yrs > a.max_years else
               f"fit {score}" if score < a.min_fit or len(got) < 3 else None)
        return dict(jid=jid, title=title, company=co, location=loc, fit=score, have=got,
                    miss=miss, years=yrs, pay=b.get("salary_low_annual"), why=why)

    prep.BRIEFS.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(2) as pool:  # 4 drew LinkedIn 429s on 24 Sep 2026
        judged = [j for j in pool.map(judge, hits.items()) if j]
    keep = sorted((j for j in judged if not j["why"]), key=lambda j: -j["fit"])
    with ThreadPoolExecutor(8) as pool:
        for j, u in zip(keep, pool.map(lambda j: careers_url(j["company"], j["title"]), keep)):
            j["li"] = f"https://www.linkedin.com/jobs/view/{j['jid']}/"
            j["url"] = u or j["li"]
    print(f"{len(keep)} shortlisted of {len(judged)} read, "
          f"{sum(j['url'] != j['li'] for j in keep)} on a company careers board")
    for j in keep:
        print(f"  {j['fit']:>3}  {j['company']} | {j['title']} | {j['location']}")

    import openpyxl
    out = profiles.DIR / "scout" / f"{profiles.DIR.name}_Jobs_{date.today()}.xlsx"
    out.parent.mkdir(exist_ok=True)
    if out.exists():  # campaign.sh scouts one keyword at a time; keep the day's earlier ones
        wb = openpyxl.load_workbook(out)
        ws, rej = wb["Shortlist"], wb["Rejected"]
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Shortlist"
        ws.append(["Company", "Role", "Location", "Apply URL", "LinkedIn", "Fit", "Tools matched", "Tools missing",
                   "Years asked", "Pay from"])
        rej = wb.create_sheet("Rejected")
        rej.append(["Company", "Role", "Reason", "Apply URL"])
    for j in keep:
        ws.append([j["company"], j["title"], j["location"], j["url"], j["li"],
                   j["fit"], ", ".join(j["have"]), ", ".join(j["miss"]), j["years"], j["pay"]])
    for j in judged:
        if j["why"]:
            rej.append([j["company"], j["title"], j["why"], f"https://www.linkedin.com/jobs/view/{j['jid']}/"])
    wb.save(out)
    print(f"-> {out.name}")
    if a.track and keep:
        jobs.add(jobs.APPS, [{"Company": j["company"], "Role": j["title"], "Location": j["location"],
                              "Apply URL": j["url"], "ATS": ats.detect(j["url"]),
                              "Status": "found", "Notes": f"scout {date.today()}: {j['li']} fit {j['fit']}, "
                              f"missing {', '.join(j['miss']) or 'none'}"} for j in keep])


def selfcheck():
    card = ('<li><div data-entity-urn="urn:li:jobPosting:123"><h3 class="base-search-card__title"> Marketing '
            'Analyst </h3><h4 class="base-search-card__subtitle"><a href="x"> Acme </a></h4>'
            '<span class="job-search-card__location"> Chicago, IL </span></div></li>')
    assert cards(card) == [("123", "Marketing Analyst", "Acme", "Chicago, IL")], cards(card)
    evil = card.replace("Marketing Analyst", 'Analyst" $(curl x) `id` \\')
    assert cards(evil)[0][1] == "Analyst (curl x) id", cards(evil)
    assert fit("Must know SQL, Tableau and Looker.", {"sql", "tableau"})[:2] == (67, ["sql", "tableau"])
    assert fit("Excellent communicator.", {"sql"})[0] == 0
    assert years_asked("Requires 3+ years of experience in analytics. 10 years of history.") == 3
    assert years_asked("5-7 years of relevant experience") == 5
    assert years_asked("With over 15 years of industry experience, Acme serves 400 clients. "
                       "Requires 2+ years of experience in SQL.") == 2
    assert years_asked("Bachelor's and 4 years of professional experience required.") == 4
    assert TITLE_NO.search("Senior Strategist, SEO Content")
    assert TITLE_NO.search("Senior Manager, Analytics") and not TITLE_NO.search("Senior Marketing Analyst")
    assert TITLE_OK.search("CRM Analyst") and not TITLE_OK.search("Office Coordinator")
    assert STAFFING.search("Insight Global Staffing") and STAFFING.search("Harnham")
    assert not STAFFING.search("Acme Corp")
    print("ok")


if __name__ == "__main__":
    selfcheck() if sys.argv[1:] == ["selfcheck"] else main(sys.argv[1:])
