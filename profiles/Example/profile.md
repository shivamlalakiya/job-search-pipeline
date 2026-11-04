# Profile: every answer an application form asks, answered once

SAMPLE PROFILE. Alex Morgan is fictional. Copy this folder to `profiles/<YourName>/`, replace every value with your own, and run `python3 jobs.py profile <YourName>`.

This is the single source of truth for form answers. Nothing here is invented: every fact comes from the resume or from an answer the user gave on the date noted. Read this before filling any form. Per-application history lives in `LOG.md`, structured tracking in `tracker.xlsx`.

## Identity

| Field | Value |
|---|---|
| Full name | Alex Morgan |
| Email | alex.morgan@example.com |
| Phone | (555) 010-0100 |
| Street address | 100 Example St, Springfield, IL 62701 |
| Current location | Springfield, IL |
| LinkedIn | https://linkedin.com/in/example |
| GitHub | https://github.com/example |

## Screening questions

| Question as forms phrase it | Answer |
|---|---|
| Are you legally authorized to work in the United States? | **Yes** |
| Will you now or in the future require sponsorship for employment visa status? | **No** |
| Desired salary / compensation expectation | Prefer blank, or **"Negotiable"** in a free-text field. Where a number is required: **75000** (USD, annual base). |
| Earliest start date | **Two weeks after offer** |
| Willing to relocate? | Not supplied. If required, stop and ask. |
| Have you previously worked for this company? | No |
| Race / gender / veteran status | **Decline** each, choosing the "I do not wish to answer" option. |
| Disability self-identification | **Decline.** Choose "I do not want to answer". |
| References | "Available on request" where free text, otherwise stop and ask. |

## Stated skills

Tools the user has confirmed using that are not in `base/resume_base.tex`. Add a row only from the user's own answer, never from a posting and never by inference, and write the same skill into the base resume. See "Tailor hard" in `docs/resume.md`.

| Tool or skill | Depth, in the user's words | Confirmed on |
|---|---|---|

## Employment history

| Employer | Title | Dates | Location |
|---|---|---|---|
| Example State University | Data Analyst, Institutional Research | Jan 2024 – present | Springfield, IL |
| Northwind Health | Business Intelligence Analyst | Jun 2022 – Dec 2023 | Chicago, IL |
| Contoso Retail | Data Analytics Intern | May 2021 – Aug 2021 | Remote |

## Education

| School | Degree | Dates | GPA |
|---|---|---|---|
| Example State University, Springfield, IL | MS, Business Analytics | Aug 2020 – May 2022 | 3.7/4.0 |
| Lakeside College, Madison, WI | BS, Economics | Aug 2016 – May 2020 | 3.5/4.0 |

## Account creation

Create employer accounts under `alex.morgan@example.com`, with the password stored as `ALL_ATS_PASSWORD` in `ATS-CREDENTIALS.txt` (mode 600, never committed). Agents never create accounts: the user signs up, adds the host to `accounts.txt`, and the parked row is reopened with `python3 jobs.py parked --reopen`.

## Stop conditions

Do not guess. Stop and ask the user if a form requires:

- References with contact details.
- Permission to contact the current employer.
- Any question of fact that this file does not answer.
