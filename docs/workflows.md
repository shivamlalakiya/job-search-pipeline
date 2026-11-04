# Workflows: how a job gets from a URL to a submitted application

_Split out of `CLAUDE.md` on 10 Sep 2026. A cross-reference to a section "below" or "above" that is not in this file means the sibling file under `docs/`._

## Workflow A: the user gives a job URL

1. Check the URL is still live before doing any work. `curl -sS -o /dev/null -w '%{http_code}' -L <url>`. A 404 or 410 means the posting is gone; record it and find the live equivalent rather than tailoring against a dead req. On 9 Sep 2026 the RWJBarnabas target from the day before returned 410.
2. Run `python3 ats.py <url>` first. It names the ATS, and on Workday it pulls the posting straight from the tenant's CxS API: title, req id, posted date, closing date, employment type, location, and the full description. `python3 ats.py --text <url>` prints the description, which is the exact sentences to tailor against. That covers step 4 as well and needs no browser. For everything else, open the URL with the Playwright MCP browser and read the full posting, then pull the raw text with `curl` and strip the tags, because a summarised version loses the sentences.
3. Read the qualifications properly and check for a hard disqualifier before spending effort. A licence, a certification or a clinical credential the user does not hold means skip the role and say so. One of the three live RWJBarnabas Data Analyst roles required an active NJ RN licence.
4. Confirm the ATS, which step 2 already named. Greenhouse, Lever, Ashby, Workday, iCIMS, Taleo, SmartRecruiters and SuccessFactors each behave differently. If a careers page renders the board in an iframe, drive the form inside the iframe. The LinkSquares entry in `<profile>/LOG.md` is a worked example.
5. Add the row: `python3 jobs.py add-app --company X --role Y --location Z --apply-url URL --ats ATS --status tailoring`.
6. Tailor the resume as described under "Resume" below, then set `--status ready --resume <profile>/resumes/Resume_<Name>_<Company>.pdf`.
7. Fill the form from `<profile>/profile.md`, expanding the free-text fields as described under "Free-text fields" below. Check `<profile>/answers.json` for the exact option label on each screening question, and record the label you used. Never invent an answer. If the form asks something `<profile>/profile.md` does not answer, stop and ask the user.
8. Submit. The user authorised unattended submission on 9 Sep 2026, so do not wait for approval on a form whose answers all came from `<profile>/profile.md`. Approval is still required if any answer had to be decided rather than looked up.
9. Record the submission: `python3 jobs.py add-app --company X --role Y --status submitted --salary-answered N --notes "..."`. Do not save a confirmation screenshot; note any confirmation id or reference number in `--notes` instead.
10. Append the outcome to `<profile>/LOG.md`, including anything the autofill got wrong and anything you had to decide. The `outreach` agent never writes `<profile>/LOG.md`, so fold its report into this entry when it arrives.
11. Spawn the `outreach` agent for this company and role, per "Outreach" below. Do not write the email on the main thread and do not wait for the agent.

## Workflow B: find postings, then apply

**Start with `python3 scout.py "<keyword>" ... --days 1`** (added 24 Sep 2026). It runs the LinkedIn guest search below, drops rows already on the tracker, gates titles to analytics work at her level, runs `prep.brief` on each survivor (liveness, clearance, credential, pay floor) and keeps only postings whose named tools the base resume mostly holds (`--min-fit`, default 60, and at least 3 matched) and that ask for no more than `--max-years` (default 5). Fit is decided here and nowhere later. The Shortlist sheet goes to the user; `--track` adds it to the tracker as `found` for `jobs.py resolve`. Contacts are not researched here: the outreach agent ranks up to five per role after submission. Since 3 Oct 2026 (user preference) each shortlisted role is also looked up on the company's public Greenhouse, Lever, Ashby and SmartRecruiters boards, and an exact title match becomes the Apply URL, with the LinkedIn URL kept in its own column and in the tracker note; only rows without one go to RESOLVE.

Search first, apply second, and never apply to anything the user has not picked.

The method that worked on 8 Sep 2026, recorded in `profiles/archive/Data_Analyst_Jobs_2026-09-08.xlsx`: LinkedIn's public `jobs-guest` search API with `keywords`, `location=United States` and `f_TPR=r86400` for the last 24 hours. 37 US roles matched, 10 direct employers survived filtering. Playwright on the employer's own careers page is the fallback when an API is not available.

Filters, all set by the user on 9 Sep 2026:

- Exclude staffing agencies and aggregators. An application there goes to a vendor rather than the employer.
- Exclude contract roles.
- **Exclude anything requiring a security clearance.** Secret, top secret, TS/SCI, polygraph or a government suitability determination, including postings that only require being *able to obtain* one. Set by the user 9 Sep 2026. The requirement usually sits in the description rather than the title, so check the body text, and do not be fooled by boilerplate such as the Employee Polygraph Protection Act notice or a list of role categories that need a background check.
- Skip anything paying under **60,000 per year** total. Above that floor there is no salary filter at all, so do not drop a role for paying less than the current 100,000 base.
- No title filter. Analyst, engineer, scientist or anything else is in scope. What gates a role is the qualification check in Workflow A step 3, not its title.
- Where the user has not named locations or a window, default to the United States including remote, posted in the last 24 hours.

Before hand-rolling the guest API call, check whether the `agent-reach` skill has a live LinkedIn backend with `agent-reach doctor --json`, and use it if so.

Log every match as `--status found`, present the list to the user, and move only the ones they choose to Workflow A. Mark the rest `skipped`.

## Workflow C: a bulk application run

When the user says to apply to a list and keep going, this is the mode. It was written on 10 Sep 2026 after a run where far too much of the night went into search and contact research and only three applications got submitted. The lesson is at the top because it is the whole point.

**Front-load nothing that is not an application.** Search, contact research and spreadsheets are a separate job. In a bulk run, the only work that counts is a submitted application. Do the prep for all of them in one parallel burst, then grind the forms without stopping to research.

**Do not stop between applications.** No status report, no asking whether to continue, no waiting for approval on an answer that `<profile>/profile.md` already covers. Submit, record, move to the next one in the same turn. Report only when the list is done, when something genuinely needs a human, or when the user asks.

**What can and cannot run in parallel.** There is one Playwright browser and one profile directory, and Chromium locks it, so form filling and submission are strictly serial. Do not pretend otherwise. One browser agent at a time is fine and is now the default, see "One application per agent" below; two at once is not, and the main thread should not be driving the browser itself while one is running. Everything else parallelises and should:

- Resolving the real apply URL behind an aggregator redirect, and classifying the ATS.
- Reading the posting and extracting the screening questions, the salary band, the deadline and any hard disqualifier.
- Tailoring the resume, which is scripted and needs no browser.
- Writing the cover letter.
- Contact research.

Run those as a batch of subagents over the whole list first. The browser phase is then pure clicking, which is where the time actually goes.

### Rewritten 24 Sep 2026: why runs stopped, skipped and crawled

Measured on one profile's tracker (851 rows: 162 submitted, 662 skipped). Three causes, each with its fix:

- **Runs stopped after a few** because nothing enforced Priority 1. The old step 4 said "spawn it and end the turn", and the Stop hook that was meant to keep a run going lived in a session scratchpad and died with it. Now: `python3 jobs.py bulk` at the start of every bulk run. `.claude/hooks/bulk_continue.py` (a Stop hook in `.claude/settings.json`) then refuses to let the main thread end its turn while `python3 jobs.py queue` is non-empty, names the next role, and deletes `.bulk-run` itself when the queue is empty. It lets go after three stops in a row with no progress, so a stuck run cannot loop.
- **The majority was skipped** for two reasons. 195 rows hit an account wall (89 of them Workday, against 4 Workday submissions), each found only after tailoring and a browser visit. `prep.py` now says `park: account-gated <ats>` from the URL alone, and `jobs.py parked` lists every walled role grouped by host so the user creates each account once; she adds the host to `<profile>/accounts.txt` and `jobs.py parked --reopen` puts those roles back in the queue. Another 117+ were skipped on fit (years, seniority, domain, a missing tool), which `<profile>/profile.md` never allowed: see "Skip only on these" below.
- **It crawled** because each apply agent loaded ~250KB before touching the form (`answers.json` whole, all of `docs/`), and left its tab open, so later agents worked in a browser with dozens of tabs. `.claude/agents/apply.md` now reads only its ATS's section and bank, and closes its own tab when done.

### Resolving employer URLs

Before any WebFetch or browser search, run `python3 ats.py find "<company>" "<title>"`. It queries the public Greenhouse, Lever, Ashby and SmartRecruiters board APIs under a few slug guesses (pass extra slugs after the title) and prints matching postings with their apply URLs, no browser needed. Added 24 Sep 2026 after 27 rows from one day's list sat `blocked` because WebFetch cannot render those JS boards; it resolved two of them (Okta, OLIVER) on the first try. A row whose URL cannot be resolved stays `found` with the note, never `blocked`, so the queue still counts it.

### Skip only on these

A role is skipped for exactly: a required security clearance, a licence or credential the person does not hold, residency in a place they are not in or current-student status, pay under the floor, a staffing agency or aggregator rather than the employer, a dead posting, a duplicate, or a different profession altogether (software engineering, design, content writing) rather than analytics work. Years of experience, seniority, an unfamiliar domain and a tool the posting wants but the record lacks are **not** skip reasons: apply and let the employer decide. An account wall is not a skip either, it is a park.

### Stages, added 24 Sep 2026 (supersedes the order below where they differ)

A run on 24 Sep 2026 stopped at 161 pending with 148 rows still on LinkedIn URLs and no resume. The hook kept saying "spawn the apply agent" for rows no agent could apply to, and counted only the pending total as progress, so resolving and tailoring looked like a stall and it let go. Now `python3 jobs.py queue` puts every pending row in one stage and the hook names what each stage needs:

- **RESOLVE** (LinkedIn or no URL): `python3 jobs.py resolve` writes `.li_resolve.js` for the next 40 LinkedIn ids. In a tab you opened, `browser_run_code_unsafe` with `filename: ".li_resolve.js"`, save the returned JSON to the scratchpad, `python3 jobs.py resolve --ingest <file>`. A guest LinkedIn page in the browser carries the employer link (`a[href*="safety/go"]`), which curl and WebFetch never see; about 1.5s a row including pacing, 142 rows in four calls. Ingest writes the employer URL and ATS, skips closed postings, tags Easy-Apply-only and errored rows `CAREERS` (they stay in RESOLVE and are found on the company's own careers site, then applied there; user preference 3 Oct 2026, never park them for a LinkedIn login), and parks every account-gated row. Do this before any WebSearch for a URL. LinkedIn answered 429 after ~45 unpaced pages, so the helper paces and stops on a 429; rerun later for the rest.
- **TAILOR** (employer URL, no resume PDF): `tailor` agents, background, up to four at once, one row each. No browser, so they overlap with the apply agent.
- **APPLY**: `apply` agent, foreground, one at a time, as in step 4 below.
- **PARK**: `python3 jobs.py park`. Resolve already does it; this catches rows whose URL was set by hand.

Main-thread loop: while an apply agent runs in the foreground, the tailor agents started in the same block keep the APPLY stage full. Resolve runs when the browser is between apply agents. The hook also starts `outreach/bounces.py --retry` (with `--send` when `<profile>/autosend` exists) itself every five submissions, logging to `<profile>/outreach/bounces.log`, and reports submitted rows with no outreach so an outreach agent goes out for each.

### The order to work in

1. `python3 prep.py <url> ...`, or `--from-xlsx <sweep>.xlsx "Shortlist and contacts"`, over the whole list at once. Per role it checks the posting is still live, names the ATS, pulls the entire Workday posting from the CxS API, runs the clearance, credential and 60,000 filters, and writes `<profile>/applications/briefs/<role>_<req>.json` holding all of it including the full description. Read the verdict column and drop the skips before spending a minute on them.
2. Add a tracker row for every role that survived step 1, `--status tailoring`, before building anything. Then build every resume in one pass, tailoring against the `text` field of each brief rather than re-fetching the posting. Skipping the row is how a tailored resume and cover letter end up on disk with nothing in `<profile>/tracker.xlsx` to say whether the application was ever started, which on 10 Sep 2026 cost a session a round trip to ask another one whether it held a half-finished University of Michigan account.
3. Write every cover letter from those briefs, then make its upload copy in the same step: `sed '/^#/d' <letter>.md | textutil -stdin -format txt -convert docx -output <letter>.docx` (the `sed` drops a markdown heading line, which would otherwise print as the letter's first line). Greenhouse rejects `.md` and `.txt`, and until 24 Sep 2026 every apply agent was converting the letter itself mid-form. Add to each brief, by hand, whatever needs the browser: the screening questions with the answer each takes from `<profile>/profile.md`, and anything `<profile>/profile.md` cannot answer.
4. `python3 jobs.py bulk`, then work down `python3 jobs.py queue`, which puts applyable rows first and marks account-gated ones `PARK`. A `PARK` row gets one `add-app --status skipped --notes "PARKED <date>: account-gated <ats> on <host>"` and nothing else: no tailoring, no browser. For the rest, one application per `apply` agent, one agent at a time, **spawned in the foreground** (`run_in_background: false`) so the main turn stays alive while it works. Do not touch the browser yourself while it is running.
   Spawn it with `subagent_type: "apply"` (never `general-purpose`, which can itself spawn and return early) and a short prompt; the agent file already says what to read, and a prompt that adds "read docs/workflows.md, docs/tooling.md" puts back the setup cost the agent file removed:

       Profile: <name>. Apply to <Company> | <Role> (tracker row exact strings).
       URL: <apply url>  ATS: <ats>
       Brief: <profile>/applications/briefs/<file>.json
       Resume: <profile>/resumes/<file>.pdf  Cover letter: <profile>/applications/<file>
       Open tabs to leave alone: <list, or none>

5. When it returns, spawn in one block: the `outreach` agent for the role it finished (background) and the `apply` agent for the next role (foreground). Anything the apply agent flagged for a human goes in your notes for the end of the batch, not into a mid-run interruption. No screenshots.
6. Every five applications, and at the end of the batch, run `python3 outreach/bounces.py --retry --send` (only on a profile whose `profile.md` authorises derived addresses; otherwise run it without `--send` and ask). It reads the inbox for bounce reports, marks the rows `bounced`, and resends to the next address shape for the same person, up to five addresses per row. See `docs/outreach.md`.
7. When the queue is empty, `python3 jobs.py parked` is the signup list for the user, in one message.
8. **Release the browser when the stretch ends.** The session's Playwright server keeps Chrome alive after every agent returns, and agents may not call `browser_close`, so the profile stays locked to this session until its main thread closes it. On 24 Sep 2026 a finished session held the browser profile for hours and blocked the next session's apply agent. Once no tab holds a filled form a human still needs, the main thread calls `browser_close`, then `python3 jobs.py browser` must print `free` before the other session is told it can go.

### One application per agent

Written 10 Sep 2026, after a run compacted at five submitted applications. The browser is what costs context: page state, field enumeration, retries, and above all `browser_snapshot`. None of that is worth keeping once an application is submitted, but a single long session keeps all of it and re-reads it on every later turn, and then compacts and loses the parts that were worth keeping.

So the browser work goes in `.claude/agents/apply.md`, one agent per application. It reads `CLAUDE.md`, `<profile>/profile.md`, the brief and `<profile>/answers.json` itself, drives the form, submits, records the tracker row, appends its own `<profile>/LOG.md` entry, and returns four lines. The main thread grows by those four lines instead of by a whole application. This is the automated version of "restart the session every five", and it happens without anyone remembering to do it.

The constraint that has not changed: Chromium locks one profile directory, so exactly one browser agent runs at a time. Never two. The `outreach` agent has no browser tools precisely so it can overlap with one.

**Two `apply` agents at once corrupts silently, and the failure mode is worse than a crash.** On 11 Sep 2026 the main thread spawned a second `apply` agent while the first was still running, on the theory that one was only pressing Submit on a finished draft. Both were driving the single profile. `browser_run_code_unsafe`'s `page` handle resolved to the *other* agent's tab four times, and the first occurrence nearly fired a click into a half-filled Workday form belonging to a different application. Nothing was corrupted only because each agent had independently started guarding its calls, one with a `window.__mine` tag and the other with `if (!page.url().includes('<expected host>')) return 'WRONGPAGE'`. That guard is worth adding to any long run as a seatbelt, but it is not a licence to spawn two: the rule is one browser agent at a time, including when the second one "only has to click Submit".

**And the rule has to cover the human, not only the agents.** On 10 Sep 2026 the user browsed and applied in the same headed Chrome while an `apply` agent was mid-form on the same tenant. High Point R0008822 flipped to submitted between the agent's step 4 save and its step 5 save, the agent's next click was refused with "You already applied to this job", and both of the agent's tabs were closed under it with Playwright's active page reassigned to a page it never opened. Nothing wrong reached the application that time, because the steps the user's session submitted were the same lookups the agent had already saved. It was luck, not design: a collision one step earlier would have submitted a half-filled form. Before a bulk run, agree who has the browser. If the user wants to click through one themselves, the run pauses first.

Both of the things that were unverified when this was written held, checked on the first spawned application on 10 Sep 2026 (Western Governors University, `wgu.wd5`). A spawned agent's `mcp__playwright__*` calls reach the session's own server and the same `~/.cache/pw-jobapps` profile: Chromium launched, and a tab opened straight into the signed-in Gmail inbox, so persistent logins and the verification-code path both survive inside an agent. The `--secrets` substitution also works inside an agent, length 9 rather than 16, with `pw/fields.js` reporting the field as `<secret>ALL_ATS_PASSWORD</secret>`. What does not survive is a per-tenant Workday session cookie, which expires on the tenant's own schedule and is not a profile problem.

A stale `SingletonLock` symlink pointing at a dead pid can sit in the profile after a session dies. It did not stop Chromium launching. Idle `playwright-mcp` server processes are not the same thing as a running browser: `pgrep -f pw-jobapps` counts servers, and only `python3 jobs.py browser` (which reads the profile's `SingletonLock`) tells you whether the profile is actually in use; a `ps` grep for "Chrome for Testing" misses a server running system Google Chrome. Several idle servers coexisting is normal and harmless.

The target, so this is checkable rather than a nice idea: five applications with the main thread under 100,000 tokens and no compaction. Measure it on the first batch that uses this and write the number down.

### One session per batch

Start a session with `python3 jobs.py gaps`. It prints the two things that need a human and that neither sheet shows on its own: applications recorded `submitted` with no outreach sent, and outreach held at `draft` on an application that did go in. A held draft is a derived address waiting for a yes, so ask the user and then send or drop it. A draft against an application that was never submitted is deliberately not reported, because that is a role the user passed on rather than a pending decision. Run it again at the end of a batch.

Start a fresh session every five applications or so, and keep the state on disk where it already lives, `<profile>/tracker.xlsx` and `<profile>/LOG.md`. The 9 to 10 Sep 2026 run was a single session that reached 624,000 tokens of context, and every turn after that re-reads all of it before doing anything, which is most of why the night felt slow. Nothing about the browser was the bottleneck: that session's 160 `browser_run_code_unsafe` calls returned 323KB in total, and Playwright MCP already writes page snapshots to `.playwright-mcp/*.yml` and returns only a link to them.

### Skip fast

A blocked application costs the same as a submitted one if you fight it. The user's rule of 9 Sep 2026 is to skip and come back. Give any single blocker about two attempts, then record it `skipped` (CLAUDE.md Priority 1) with a precise note on what a human needs to do, and move on. Existing accounts with unknown passwords, bot walls and captchas are all skips. Do not run a password reset on an account the user may already hold without asking.

### Session length

A session that keeps applying for hours accumulates context faster than it accumulates applications. One measured stretch: 158 browser code calls, 176 deliberate `waitForTimeout` sleeps summing to over 500 seconds, and about 18 minutes of real tool execution inside an 82 minute window, the rest spent on enumerating page state fresh at every step. A second run on 10 Sep 2026 compacted after five submitted and six blocked applications, and a compaction is worse than a restart because it silently drops the tenant knowledge the session just paid to learn.

The fix is "One application per agent" above. Restarting the session every five applications is the fallback for when that is not available. Either way, keep every fact that matters in `<profile>/tracker.xlsx` and `<profile>/LOG.md`, never only in conversation memory, so the next context picks up cleanly. Wait for the element or the page state you need rather than a fixed timeout.


## Layout, as it was written before the split

| Path | What it is |
|---|---|
| `<profile>/profile.md` | Identity, work history, education, screening answers, salary rules, stop conditions. Source of truth for form filling. |
| `<profile>/tracker.xlsx` | Two sheets, `Applications` and `Outreach`. Maintained only through `jobs.py`, never edited by hand in a session. `Date` is the last status change unless you pass `--date`. |
| `<profile>/LOG.md` | What happened on each application, including the decisions taken and why. Append a subsection per application. |
| `PROFILE` | The active person's folder name. `python3 jobs.py profile` prints it, `python3 jobs.py profile <name>` switches it and rewrites `.mcp.json`, which needs a restart. |
| `<profile>/base/resume_base.tex` | The base resume. Never tailored in place. Copy it, then edit the copy. |
| `<profile>/resumes/` | One `.tex` and one `.pdf` per application. |
| `<profile>/applications/` | One markdown file per application: the cover letter, the expanded free-text answers, and the screening answers actually used. |
| `<profile>/outreach/` | Email bodies as `.txt` and drafts as `.eml`. The script that builds and sends them, `outreach/mkemail.py`, is shared and stays at the root. |
| `profiles/archive/` | Superseded artifacts, kept for provenance. |
| `<profile>/ATS-CREDENTIALS.txt` | ATS account passwords, mode 600. See the rule below. |


## Why one browser session

Set by the user 15 Sep 2026 after two sessions applying for the same profile lost 8 filled applications in one day: a live tab with an unsaved fill was closed by the other session's agent working the same shared profile, even though every agent had been told to leave the other's tabs alone. A "starting"/"done" message only catches two simultaneous Chromium launches (which fail cleanly on the OS-level profile lock); it does not stop an already-open tab from being closed once both sessions have live browser state. On 24 Sep 2026 `ps | grep "Chrome for Testing|chromium"` returned nothing while system Google Chrome held the profile, which is why `jobs.py browser` reads the `SingletonLock` instead.
