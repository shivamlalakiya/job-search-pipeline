# Onboarding: from a fresh clone to the first submitted application

Written for the AI assistant a new user opens this repo with (Claude Code reads it through `/onboard`; any other agent reads `AGENTS.md`, which is `CLAUDE.md`). Run it when `PROFILE` is missing, names `Example`, or names a profile whose `profile.md` still holds sample values. Work through the steps in order and finish each before the next. The user signs every application this pipeline sends, so nothing in their profile or resume may come from anywhere but their own words or their own documents.

## 1. Check the machine

Run each and report what is missing in one list, with the install command:

    python3 --version                      # 3.13+
    python3 -c "import openpyxl"           # pip3 install -r requirements.txt
    node --version                         # 24+, needed for npx and the Playwright MCP server
    /Library/TeX/texbin/pdflatex --version # MacTeX (brew install --cask mactex-no-gui)
    claude --version                       # Claude Code, needed by run_bulk.py

macOS only today: outreach reads the Gmail app password from the macOS keychain and notifications use `osascript`.

## 2. Create the profile folder

Ask for the name to file things under (one word, e.g. `Priya`). Then:

    printf 'Example\n' > PROFILE           # scripts refuse to run with no PROFILE at all
    cp -R profiles/Example profiles/<Name>
    rm profiles/<Name>/LOG.md && touch profiles/<Name>/LOG.md
    : > profiles/<Name>/accounts.txt
    printf '%s\n' "$HOME/.cache/pw-<name>" > profiles/<Name>/browser.txt

## 3. Interview for the profile

Ask in a few grouped messages, not one question at a time and not forty at once. Write every answer into `profiles/<Name>/profile.md`, replacing the Example values and the "SAMPLE PROFILE" line, with today's date next to anything that was a judgment call. An answer the user does not give stays `TBD` and is a stop condition, never a guess.

1. **Identity**: full legal name, preferred name, email for applications, phone, street address, city, LinkedIn, GitHub or portfolio.
2. **Work authorization**: authorized to work in the target country, needs sponsorship now or later, visa type if relevant.
3. **Target**: job titles to search for (these become `profiles/<Name>/keywords.txt`, one per line, read by `campaign.sh`), locations, remote/hybrid/on-site, willing to relocate, salary floor (annual, used as the pay filter) and the number to type when a form demands one.
4. **Hard skips**: anything they will never apply to (clearance roles, a company, an industry), plus any licence or credential they hold.
5. **Standard screening answers**: earliest start date, previously worked for an employer, references, can the current employer be contacted, EEO (gender, race, veteran, disability): answer or decline.
6. **Stretch rule**: when a form asks about a tool, a domain or years of experience the record does not show, should the agent answer from the closest real experience, or stop? Write their exact words as a "Stretch rule" section; without one, the agent stops on those questions.
7. **Outreach**: may the pipeline email a recruiter after each application? If yes, the Gmail address to send from, and whether sends need their OK each time or are standing (an empty `profiles/<Name>/autosend` file means standing). Write `signature.txt` (`from:`, `keychain:`, `--`, signature block).

Then read `profile.md` back to them as a short summary and fix what they correct.

## 4. The base resume

Ask one question: **keep the sample format, or use a different style?** Show them `profiles/Example/base/resume_base.pdf` so they can see the sample.

- **Same format.** Ask for their current resume (a file path to a PDF, DOCX, TXT or TEX, or pasted text). Read it, then rewrite `profiles/<Name>/base/resume_base.tex` keeping the Example's preamble and macros and replacing every line of content with theirs. Move facts across, never improve them: no new metrics, tools, titles or dates. The base may run past one page; it is the full record that tailored copies are cut from.
- **Different style.** Ask for a sample of the style (their own `.tex`, a PDF they like, or a description). Build `resume_base.tex` in that style, still LaTeX, still compiled by `pdflatex` with no packages beyond MacTeX. Hard limits from `docs/resume.md`: never below 11pt or 0.4in margins, and every bullet a `\resumeItem` (or one consistent macro) so tailoring can cut bullets cleanly.

Compile it and show them the PDF:

    cd profiles/<Name>/base && /Library/TeX/texbin/pdflatex -interaction=nonstopmode resume_base.tex

Ask them to confirm every line is true and theirs. Anything they add in conversation goes into the `.tex` (and, for a tool, into "Stated skills" in `profile.md`), never only into chat.

## 5. Passwords stay with the user

Agents never see passwords. Tell the user to do these two themselves:

- `cp profiles/<Name>/ATS-CREDENTIALS.txt.example profiles/<Name>/ATS-CREDENTIALS.txt`, put the one password they use on employer ATS sites after `ALL_ATS_PASSWORD=`, then `chmod 600` it. The Playwright server types it server-side.
- For outreach, a Gmail app password in the keychain, under the item name they gave for `keychain:`: `security add-generic-password -s <keychain item> -a <gmail address> -w` (it prompts; nothing is echoed).

## 6. Activate and restart

    python3 jobs.py profile <Name>         # writes PROFILE and .mcp.json
    python3 jobs.py selfcheck && python3 prep.py selfcheck && python3 ats.py selfcheck && python3 scout.py selfcheck

Then the user must restart Claude Code (it reads `.mcp.json` only at startup) and approve the `playwright` MCP server. If the browser later fails with `CONNECTION_CLOSED`, check `~/.claude.json` for a project-scoped `playwright` server shadowing `.mcp.json`.

The scout's title gate (`TITLE_OK` / `TITLE_NO`) and tool list (`VOCAB`) in `scout.py` are tuned for analytics roles. If the target titles are in another field, say so and adjust those three constants with the user before the first search, or every result will be dropped as "title".

## 7. First search and a supervised first batch

    python3 scout.py "<first target title>" --days 3 --track
    python3 run_bulk.py --dry-run
    python3 run_bulk.py --limit 3

Show them each submitted row (`python3 jobs.py show "<company>"`), the tailored resume PDF under `profiles/<Name>/resumes/`, and the `LOG.md` entries, and ask whether anything was answered wrong. Fix `profile.md` from their corrections. Only then run the whole list from a terminal:

    ./campaign.sh 50                       # scout + apply until 50 new submissions

## 8. Account walls

Workday, iCIMS, Taleo, SuccessFactors, Oracle and similar ATS hosts need an account per employer, and agents never create accounts. Those roles are parked, not lost:

    python3 jobs.py parked --live          # writes profiles/<Name>/signup_list.md, grouped by host

The user signs up on the hosts worth it (most roles first), adds each host to `accounts.txt`, then `python3 jobs.py parked --reopen` and `python3 run_bulk.py` applies to them.
