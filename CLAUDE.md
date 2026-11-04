# Job board

## First run: a fresh clone

If `PROFILE` is missing, names `Example`, or names a profile whose `profile.md` still holds sample values, nobody is set up yet: run `/onboard` (Claude Code) or follow `docs/onboarding.md` (any other agent) before anything below. It interviews the user for their profile, builds their base resume in the sample format or a style they choose, activates the profile and runs a supervised first batch. Everything after that is this runbook.

## Priority 1: do not stop until every job is applied to

Set by the user 15 Sep 2026. A bulk run ends when the list is finished, not when a batch is tidy or a report reads well, so do not end a turn with the browser idle while unapplied roles remain on the list. This applies to every bulk run, for either profile:

- When an agent finishes, spawn the next piece of work in the same turn. When an agent dies or stalls, check the real page state read-only, record it, and relaunch rather than reporting and waiting.
- When a role hits any stop condition that needs the user (account wall, emailed or security code, captcha, unanswerable question, ambiguous form), record the row `skipped` with a note saying exactly what stopped it and what a human would need to do, then start the next role in the same turn. Nothing mid-run waits on a reply. Revisit skipped rows only after every other row on the current list has been attempted once, and review them as one batch then.
- Ask the user a question alongside continuing work, not instead of it. Only a genuinely unsafe or unrecoverable action justifies stopping.
- Prep is never the bottleneck: if no role is ready to apply to, resolve employer URLs or tailor the next artifacts so one always is.
- Report at the end of a batch or when something needs a human, in a few lines.
- **Default mechanics (29 Sep 2026): run `python3 run_bulk.py` from a terminal, not from inside a Claude session.** It works the same stages below, but each apply, tailor, outreach and resolve step is its own headless `claude -p` session that starts small and exits (which also frees the browser), so no thread carries the whole run. Measured 14-29 Sep 2026, the in-session run's main thread spent 73% of its tokens on calls over 400K of context. `--dry-run` shows the next step, `--limit N` stops after N applies, results go to `<profile>/bulk_runs.log`.
- **In-session mechanics (24 Sep 2026), only when the user wants to watch the run in chat:** `python3 jobs.py bulk` first; the Stop hook then holds the turn open while `jobs.py queue` is non-empty. Stages (RESOLVE, TAILOR, APPLY, PARK) are in `docs/workflows.md` "Stages". Skip only on the hard list in "Skip only on these"; fit is never a skip.

A working folder for finding data roles (mostly US higher education), tailoring a one-page resume to each posting, applying through the employer's own ATS with a real browser, and emailing a named human. This is a git repository, but `.gitignore` tracks only the shared code and docs: everything under `profiles/` (including the shared `profiles/archive/`) and `.mcp.json` stays local. So for personal files `profiles/archive/` is still the only undo: copy anything you are about to overwrite into it, dated, first. Durable state lives in `<profile>/tracker.xlsx` and `<profile>/LOG.md`, never in conversation memory. Start a session with `python3 jobs.py profile` to see whose folder you are in, then `python3 jobs.py gaps`.

## Profiles

Several people can share this folder, one profile each. The scripts, `docs/`, `pw/` and `profiles/archive/` are shared. Everything personal lives under `profiles/<Name>/`: `profile.md`, `base/`, `resumes/`, `applications/`, `outreach/`, `confirmations/`, `tracker.xlsx`, `answers.json`, `LOG.md`, `signature.txt`, `browser.txt` and `ATS-CREDENTIALS.txt`. Wherever this runbook writes `<profile>/`, read `profiles/<active name>/`. Tracker paths written before 4 Nov 2026 omit the `profiles/` prefix; `profiles.path()` resolves both.

The file `PROFILE` at the repo root names the active one, and there is no default: with it missing every script exits rather than guess. Switch with `python3 jobs.py profile <Name>`, never by editing the file, because the switch also rewrites the `--user-data-dir` and `--secrets` paths in `.mcp.json` so the browser session and the ATS password belong to the same person. **`.mcp.json` is read at startup, so a switch needs a Claude Code restart before the browser is actually theirs.** One profile active at a time, the same rule as one browser agent at a time.

Never carry a fact across the boundary. An answer in one person's `profile.md` or `answers.json` says nothing about another, and a resume claim from one person's `base/resume_base.tex` is fabrication on anyone else's document. If the active `profile.md` still reads `TBD`, that is a stop condition, not an invitation to look next door.

## Where to look

| File | Open it when you are asking |
|---|---|
| `<profile>/profile.md` | What does the user answer to this field, and what am I forbidden to answer? |
| `docs/workflows.md` | I have a URL, a list, or a search: in what order do I work, and when do I skip? |
| `docs/ats.md` | Why did Continue not advance, why did that field clear, which option label do I click? |
| `docs/tooling.md` | Which script does this, why is my command being re-approved, how does the ATS password get typed? |
| `docs/outreach.md` | May I send to this address without asking, and what goes in the body? |
| `docs/resume.md` | What may I change on the resume, and where does tailoring become fabrication? |
| `<profile>/LOG.md` | Has this company or this ATS been done before, and what went wrong? It runs to hundreds of KB: grep it, do not read it. |
| `<profile>/answers.json` | Which label was clicked for this exact question? Read it with `jobs.py answer`, not by hand. |
| `PROFILE` | Whose folder am I about to write into? `python3 jobs.py profile` prints it. |
| `profiles/archive/CLAUDE_2026-09-10_pre-index.md` | Provenance for the pre-split runbook. Do not load it; `docs/` is the same text. |

## Layout

- `jobs.py` is the only writer of `<profile>/tracker.xlsx` and `<profile>/answers.json` (`prep.py` opens the workbook read-only), and builds resumes. `prep.py` does liveness, ATS naming, the hard filters, and writes a brief. `ats.py` classifies a URL and pulls whole Workday postings from the CxS API. `outreach/mkemail.py` builds and sends the `.eml`.
- `pw/` holds page helpers run by `browser_run_code_unsafe` with `filename`: `fields.js` reads a settled page in one call, `next.js` advances a wizard step, `verify.js` checks a whole Oracle page before Save, `gh_select.js` fills every Greenhouse react-select in one call from `window.__ghWant`, `frames.js` reads every frame on a page and is the one that works on PeopleSoft, whose sign-in and attachment dialogs live inside iframes that `fields.js` cannot see.
- `<profile>/base/resume_base.tex` is the sole source of truth for any claim. `<profile>/resumes/` keeps one `.tex` and one `.pdf` per application; `<profile>/applications/` holds cover letters plus `briefs/` (one JSON per role, each carrying the full posting text).
- Tests: `pw/fields_test.mjs`, `pw/next_test.mjs`, `pw/frames_test.mjs`, and a `selfcheck` subcommand in `jobs.py`, `prep.py` and `ats.py`. No framework, no fixtures.
- `<profile>/accounts.txt` lists hosts where the user has created an ATS account, one per line. `ats.needs_account()` treats every other Workday, iCIMS, Taleo, SuccessFactors, Oracle, UltiPro, PeopleAdmin, PeopleSoft and ADP host as a wall.
- `profiles.py` reads `PROFILE` and hands every script the active folder; `jobs.py profile <name>` is the only thing that writes it. `<profile>/signature.txt` carries the From address, the keychain item and the email signature that `outreach/mkemail.py` uses, so the wrong person never signs a message.
- `.playwright-mcp/` is thousands of snapshot dumps (hundreds of MB). Ignore it.

## Commands

    python3 jobs.py selfcheck                          # tracker upsert, answer bank, base resume compiles (needs pdflatex)
    python3 prep.py selfcheck                          # annualiser, clearance false positives, credential matcher
    python3 ats.py selfcheck                           # URL to ATS classification, offline
    node pw/fields_test.mjs && node pw/next_test.mjs && node pw/frames_test.mjs   # helper selectors against a stub DOM, no browser
    python3 jobs.py resume <profile>/resumes/<name>.tex          # pdflatex; exits non-zero unless exactly one page
    python3 jobs.py gaps                               # submitted with no outreach sent, and held drafts
    python3 jobs.py queue                              # pending rows by stage: APPLY, TAILOR, RESOLVE, PARK
    python3 run_bulk.py [--dry-run] [--limit N] [--retry-ready]  # bulk run, one headless session per step; held `ready` rows only with --retry-ready
    python3 jobs.py resolve [--ingest f.json]          # LinkedIn rows -> employer URL via one browser call (.li_resolve.js)
    python3 jobs.py park                               # record account-gated pending rows skipped PARKED
    python3 jobs.py parked [--reopen]                  # account walls by host; --reopen after accounts.txt gains a host
    python3 jobs.py answers <ats>                      # one ATS's answer bank, instead of reading answers.json
    python3 outreach/bounces.py [--retry [--send]]     # IMAP bounce check, mark bounced, resend next address (max 2 emails per role, follow-up included)
    python3 outreach/bounces.py selfcheck              # offline
    python3 prep.py <url>...                           # network; also --from-xlsx <sweep>.xlsx "<sheet>"
    python3 scout.py "<keyword>"... [--days 1] [--track]  # build a strict-fit job list: search, filter, brief, score -> <profile>/scout/<Profile>_Jobs_<date>.xlsx
    python3 scout.py selfcheck                         # offline
    python3 jobs.py parked --live                      # live account-walled roles only -> <profile>/signup_list.md
    python3 ats.py --text <url>                        # network; prints the sentences to tailor against

All five checks exited 0 on 24 Sep 2026. Everything that touches a posting, an inbox or SMTP hits the network. Nothing needs Docker.

## Conventions

`python3` is 3.13.11, node v24.14.0. Stdlib plus `openpyxl`, no package manager and no lockfile. `pdflatex` is at `/Library/TeX/texbin/pdflatex`; there is no latexmk. No formatter or linter is configured, so match the file you are editing. Resume never below 11pt or 0.4in margins.

## Landmines

- **Never apply twice, and never to a company where the user is interviewing (hard rule, user 30 Oct 2026).** `<profile>/tracker.xlsx` is the master record of every application from every session. `jobs.py` (`already_applied`) drops a pending row from `queue`/`pending()` and `add-app` turns it `skipped` with a `DUPLICATE:` note when it shares a posting id (any URL in Apply URL or Notes) or a normalised company + role with a submitted/rejected/interview/offer row, or when its company has an `interview` or `offer` row. So record interviews: `jobs.py add-app --company X --role Y --status interview`. On 30 Oct 2026 a Data Analyst role was applied to at a company where the user was already interviewing for a Senior Data Analyst role, because that interview was never on the tracker.
- **`<profile>/tracker.xlsx` only through `jobs.py`.** It upserts on company plus role and takes an `fcntl.flock` on `.tracker.lock` (`LOCK` in `jobs.py`) so a parallel agent cannot lose a row. Editing the workbook by hand defeats both.
- **`<profile>/answers.json` caches option labels, never judgment.** The lookup is exact on purpose: "Are you a veteran?" and "Are you a protected veteran?" have different correct answers. Changing an entry needs `--force`.
- **Never `cat`, `head` or `grep` `<profile>/ATS-CREDENTIALS.txt`** (mode 600). The Playwright server runs with `--secrets` pointed at it, so pass the literal text `ALL_ATS_PASSWORD` and the real value is typed server-side. Verify that substitution once per session, because a failed lookup types the name itself into the field.
- **One Playwright user-data-dir per person, named in `<profile>/browser.txt`, so exactly one browser agent at a time.** It is a file, not a constant, so a directory that already holds logged-in ATS sessions never has to be renamed. Chromium locks the directory and the lock survives a dead session.
- **One session owns the browser for a whole stretch of work** (set by the user 15 Sep 2026 after two sessions lost 8 filled applications; the story is in `docs/workflows.md` "Why one browser session"). A message handshake is not enough. The other session does only non-browser prep until the owner's Chrome is actually closed, confirmed with `python3 jobs.py browser` (reads the profile's `SingletonLock`), never with `ps | grep`. Greenhouse, Lever and SmartRecruiters save no draft, so a lost fill is redone from the apply button.
- **The main thread never fills forms.** Its only `mcp__playwright__*` calls are the resolve step and the final `browser_close`; every form, snapshot and click belongs to an `apply` agent or an `apply` session from `run_bulk.py`. Browser output left in the main thread is paid again on every later turn.
- **A running Playwright server still points at whatever `.mcp.json` said when the session started.** After `jobs.py profile`, restart Claude Code before driving a form, or the browser types the previous person's password.
- **Do not call `browser_snapshot` to find something to click.** `pw/fields.js` returns a ready selector per element; a snapshot is the largest single context cost in a run.
- **A `pw/*.js` helper must be one bare expression**: no trailing semicolon, no `require`, no arguments. Check it with `node -e "new Function('return ('+require('fs').readFileSync('pw/next.js','utf8')+')')()"`.
- **`prep.py` is not pre-approved** in `.claude/settings.local.json`, though `jobs.py`, `ats.py`, `mkemail.py`, `pgrep` and the liveness `curl` are. A prefix rule stops matching the moment anything is appended, so keep pre-approved calls bare.
- **Everything written on a resume or into a form must already exist** in `<profile>/base/resume_base.tex`, `<profile>/profile.md` or `<profile>/LOG.md`. The user signs these documents.
- **Never an em dash**, in any file, form field, cover letter or email in this folder.
