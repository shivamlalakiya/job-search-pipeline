# job-search-pipeline

Finds data roles, tailors a one-page LaTeX resume to each posting, applies through the employer's own ATS with a real browser (Playwright MCP driven by Claude Code agents), and emails a named human afterwards. It applies only to roles that pass hard filters, never invents a claim (every line must already exist in your base resume or profile), and refuses to apply twice or to a company where you are interviewing.

## Requirements

- macOS, Python 3.13 with `openpyxl`, Node 24, `pdflatex` (MacTeX)
- [Claude Code](https://claude.com/claude-code) with the Playwright MCP server
- A Gmail app password in the macOS keychain for outreach email

## Quick start

Clone, `cd` in, start Claude Code (`claude`) and type `/onboard`. It checks your machine, interviews you for your profile, turns your current resume into the base resume (in the sample format, or a style you pick), activates your profile and runs a supervised first batch of three applications. Other AI coding agents: point them at `AGENTS.md` and `docs/onboarding.md`.

## Set up a profile by hand

`profiles/Example/` is a fictional sample. Copy it and make it yours:

```bash
cp -R profiles/Example profiles/YourName
cp profiles/YourName/ATS-CREDENTIALS.txt.example profiles/YourName/ATS-CREDENTIALS.txt
chmod 600 profiles/YourName/ATS-CREDENTIALS.txt
```

Then edit, in `profiles/YourName/`:

- `base/resume_base.tex`: your full record. It is the only source for any resume or form claim, so it can run longer than a page; tailored copies are cut to one.
- `profile.md`: your answers to form questions and your stop conditions.
- `signature.txt`: From address, keychain item name, email signature.
- `browser.txt`: a Chromium user-data-dir of your own, e.g. `~/.cache/pw-yourname`.
- `ATS-CREDENTIALS.txt`: the one password you use on ATS sites. The browser types it server-side; it never appears in a prompt.

Create a `.mcp.json` at the repo root with a `playwright` server whose args include `--user-data-dir <any path>` and `--secrets <any path>`, then point it at your profile and restart Claude Code:

```bash
python3 jobs.py profile YourName
```

Everything under `profiles/` except `Example/` is gitignored.

## Run

```bash
python3 jobs.py selfcheck
python3 scout.py "data analyst" --days 1 --track
python3 run_bulk.py --dry-run
python3 run_bulk.py --limit 5
```

`CLAUDE.md` is the runbook and `docs/` holds the detail: `workflows.md` (order of work, skip rules), `ats.md` (per-ATS quirks), `resume.md` (what tailoring may change), `outreach.md`, `tooling.md`.

## Contributing

`main` is protected: open a pull request, and CI (every selfcheck, the node helper tests, a LaTeX build of the sample resume) has to pass before it merges. Report security issues privately, see `SECURITY.md`.

## License

MIT, see `LICENSE`.

## Caveats

Automated access may breach a job board's or ATS's terms of service. Review what the agents submit in your name: you sign every application.
