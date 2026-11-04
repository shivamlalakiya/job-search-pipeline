# ATS behaviour: Workday, Oracle, the answer bank, the traps

_Split out of `CLAUDE.md` on 10 Sep 2026. A cross-reference to a section "below" or "above" that is not in this file means the sibling file under `docs/`._

### Workday, which is most of higher education

Worked out over three tenants on 10 Sep 2026. This is the difference between forty tool calls and fifteen.

**What an application actually costs.** Measured from the 9 to 10 Sep 2026 session, counting only active time, meaning gaps under five minutes:

| | active | tool calls | browser calls |
|---|---|---|---|
| WGU, the first one, carrying all the setup | 89 min | 308 | 153 |
| Akron | 24 min | 67 | 60 |
| RIT | 12 min | 28 | 26 |
| SNHU | 26 min | 75 | 66 |

RIT is the floor and the target: a second Workday tenant, the pattern already known, an account that already existed. SNHU cost more than twice that, and the difference is almost entirely registration and waiting on a verification email. So the fixed cost of a new tenant is the account, not the form. Registration is three calls and no more: `pw/fields.js` for the ids, then one `browser_fill_form` carrying the email, both password fields as the text `ALL_ATS_PASSWORD`, and the consent checkbox, then the Create Account click. Do not type the password field by field, and do not go near the clipboard.

**One call per page, and never sleep on a clock.** Two helpers do the repeated parts, both run with `browser_run_code_unsafe`'s `filename` and no `code`, both take no arguments because the tool passes nothing but `page`:

- `pw/fields.js` returns the current page as JSON: title, step, alerts, every visible field with its id, label, current value and whether it is required, and the buttons and links. It waits for two identical reads 400ms apart, so it returns when the page has settled rather than after a guessed delay. Nothing in it is Workday-specific, so use it on every ATS. `node pw/fields_test.mjs` checks the selector logic against a stub DOM, no browser needed.

  Every field, button and link comes back with a `sel` that goes straight into `page.fill` or `page.click` on the next call, which is the whole reason to prefer it over `browser_snapshot`. **Do not call `browser_snapshot` to find something to click.** Measured on 10 Sep 2026, a snapshot of one Nova Southeastern page cost several thousand tokens, most of it nav, footer and a related-jobs widget, and the only thing it was wanted for was a handle. It is the single biggest context consumer in a bulk run. Reach for it only when `fields.js` genuinely comes back without the element, and say so in `<profile>/LOG.md` when that happens so the helper can be fixed.
- `pw/next.js` clicks the forward button through the overlay, waits for the step or the field set to actually change, and returns the new page. It refuses to press Submit, which stays a deliberate separate call. An alert only counts as a failure if it appeared after the click and reads like an error, because Workday leaves the "successfully uploaded" confirmation in the DOM as `[role=alert]` for the rest of the session, and the first version therefore reported a failure on every advance of any tenant that had taken a resume upload. A new harmless alert comes back as `notes`. `node pw/next_test.mjs` checks those five cases against a stub page, no browser needed.

The measurement behind this, taken from a live session on 10 Sep 2026: 158 `browser_run_code_unsafe` calls in two hours, of which only 8 came back with an error, so the Playwright code was fine. What cost the time was 176 `waitForTimeout` calls totalling **511 seconds of deliberate sleeping**, median 1.5s and one of 14s, plus a round trip per page-step with the field enumeration hand-written each time. A blind sleep is either longer than the page needs or too short to help, and it hides a real failure as a slow success. Wait on the thing you are about to touch, or on the page changing, never on a number.

- Registration needs the consent checkbox ticked before Create Account will do anything. Without it the page silently returns to sign-in with no error, which reads exactly like bot detection and is not.
- If Create Account bounces with no error and no verification email arrives, the account already exists. Check the inbox to tell the two apart. Some tenants bounce back to the chooser with no error even when the account was created successfully, because they require the emailed verification link first. On `brown.wd5` a second sign-in attempt names the real cause, so do not read that bounce as account-exists until you have tried once more.
- Not every tenant has the `click_filter` overlay on the wizard footer. Where it is absent, `pw/next.js` returns `ok: true` without the page advancing, because the overlay click lands on nothing. Fall back to clicking `[data-automation-id="pageFooterNextButton"]` directly. Seen on `bentley.wd503` 10 Sep 2026; check for it whenever a step reports success twice on the same step number.
- Tenants vary on two fields that look standard. School or University is a prompt widget on some tenants and free text on others, and where it is free text the full institution name goes in rather than the nearest option. The Degree list is sometimes full names and sometimes abbreviations only, where BTech maps to `BT` and a Master of Science to `MS`. Read the options before typing, and never let a picklist silently downgrade a degree the resume states differently.
- Buttons sit under an invisible overlay. Click `div[data-automation-id="click_filter"][aria-label="..."]`, not the button.
- The identifiers that look like `data-automation-id` on inputs are usually the element `id`. Escape the hyphens.
- **Prompt widgets only search after Enter.** Type, press Enter, wait, then click the option. Typing alone returns the unfiltered list, which is how a wrong value gets picked.
- Options render either as `p[data-automation-id="promptOption"]` in a virtualised list, or as `li[role=option]`. Handle both. For the virtualised one, scroll `[data-automation-id="activeListContainer"]` to load the rest.
- Some prompts are two level. `Job Sites` then `Higher Ed Jobs`. `Other` then `Other Advertisement or Job Board`.
- The resume parser gets things wrong in the same ways every time: it truncates the employer to `Washington University`, it ticks `I currently work here` on roles that have an end date, it pastes a single resume bullet as the whole role description, and it sometimes leaves an empty extra work row that blocks Continue. Fix all four.
- School picklists are restricted and do not contain Indian institutions. SVNIT Surat is not findable at Akron or RIT and there is no free text. Delete that education row rather than assert a wrong school, and note it. The attached resume still carries the degree.
- Country phone code opens on focus with the option already rendered. Click the option directly; clicking the input again times out against the open list.

### Verify the clipboard before every paste

The clipboard is shared with everything else on the machine. Mid-session on 10 Sep 2026 the ATS password clipboard was silently overwritten (something else copied a much longer value over it), and a sign-in was attempted with the wrong value before anyone noticed. Before pasting a password into any field, reload it with `pwclip.sh` and confirm with `pbpaste | wc -c` that the length matches, every single time, not just the first time in a session.

Better, once the session has restarted since 10 Sep 2026: do not use the clipboard at all. The server now runs with `--secrets <profile>/ATS-CREDENTIALS.txt`, so `browser_type` with the text `ALL_ATS_PASSWORD` types the real value straight into the field. See the password rule under Rules. The clipboard route is the fallback for a session whose server started without the flag. Confirmed working in this session: `browser_type` with the literal text `ALL_ATS_PASSWORD` now generates `process.env['ALL_ATS_PASSWORD']` rather than typing that string, and the field receives the real value. Verified once against a `data:text/html,<input>` page and the length matched. `pwclip.sh` now lives at the project root as a fallback for any session whose server has not picked up the `--secrets` flag.

### Platform hiccups mid-form

A tool-safety classifier can stall for a stretch, which can also cost you an active Workday session (page reload, logged out, step counter resets from N of 7 to N of 8 because the flow now starts at Create Account/Sign In). When this happens: reload from the job posting URL fresh rather than clicking around a half-loaded page with two overlapping dialogs, sign in cleanly, then re-enter the apply flow and pick "Use My Last Application" if offered. Every field already filled (identity, address, experience, education) is preserved. Only the transient dropdown selections (source, phone country code, field of study) reset and need re-answering. Do not repeat the resume upload or the free-text role descriptions, they hold.

### An exact question match is not always the same question

The bank keys on the question's exact wording, which is right, and it is still not sufficient. On `ecsr.fa.us2.oraclecloud.com` on 12 Sep 2026 the question "How many years of experience do you have in a similar role?" appeared on two requisitions with byte-identical text and byte-identical option labels. It was banked as **4+ years** while applying to a Senior Research Data Analyst post, which is true of the user's data-analysis record, and reused hours later on a **Business Analyst** post, where "similar role" reads as business analyst specifically and the record holds no titled BA work. It is submitted and cannot be recalled.

So: when a banked answer's meaning depends on the requisition rather than on the user, re-read it against this posting before reusing it. The tell is a question containing a relative word, "similar", "this type of", "related", "comparable", whose referent is the job being applied to rather than a fact about the user. Facts about the user (veteran status, date of birth, eligibility to work) travel safely between requisitions. Judgements relative to the role do not.

### The answer bank

`<profile>/answers.json` remembers the exact option label that was clicked for one exact question on one ATS, so the same Workday EEO page is not re-derived on every tenant. It is a cache of labels, never of judgment: the answer itself still comes from `<profile>/profile.md`.

    python3 jobs.py answer --ats workday --question "Are you a protected veteran?"
    python3 jobs.py answer --ats workday --question "..." --set "I am not a veteran" \
        --source "profile.md screening answers" --host rit.wd5.myworkdayjobs.com
    python3 jobs.py answers

Check it before answering a screening question, record after. A miss is normal and just means reading `<profile>/profile.md`.

The lookup is exact, on purpose. Only case and whitespace are normalised, because a form wraps its own text. Nothing else, because `Are you a veteran?` and `Are you a protected veteran?` score 0.80 on the word-overlap matcher that `amgenene/workday_auto` uses at a 0.70 threshold, and `Are you legally authorized to work in the United States?` against `Are you authorized to work in the United States without sponsorship?` scores 0.715. Both pairs have different correct answers. A fuzzy bank would answer one question with the other's answer and sign it. Measured 10 Sep 2026.

Recording a different answer for a question already in the bank fails unless you pass `--force`, which is the signal that either the old entry was wrong or two ATSs word an option differently and the key needs the ATS split.

### Oracle Cloud HCM

**Tenants differ on when they authenticate, and it decides whether an agent can do anything at all.** On Caesars (`edmn.fa.us2.oraclecloud.com`, 15 Sep 2026) Apply Now goes straight to `/apply/email`, which offers only an email field, a required checkbox accepting the terms, the privacy notice and consent to receive messages, and NEXT. Nothing else is reachable: no profile, resume, screening or EEO field exists before authentication, which is the opposite of the ETSU pattern below. An agent can type the email and must stop there, because accepting terms and typing the six-digit code are both the user's actions. Hand over, let her tick the box, press NEXT and enter the code, then re-spawn an agent on that same tab without reloading it. That screen also carries a hidden honeypot input named `honey-pot-0`, so never blind-fill every input on an Oracle page.

Worked out on the East Tennessee State University req, 10 Sep 2026. A different animal from Workday: usually one continuous page rather than a wizard, no account needed, identity confirmed by a six digit email code rather than a password.

- Every structured field, not just address, is a `cx-select` combobox: State, County, Country, Month, Year, Degree. Typing without a dropdown click silently clears on blur. Always re-check `.value` after the field loses focus, not right after typing.
- ZIP Code and City can be bound together so that changing either clears the other. Fill whichever you fill last, right before checking the form, and do not touch its sibling again.
- The Save button for a work or education entry is not always labelled "SAVE." Its visible text is bound to context ("Add Experience" when adding). Target it by class, `button.save-btn`, never by visible text.
- While one timeline entry's edit panel is open, every other already-saved entry disappears from the DOM, not just from view. This looks exactly like data loss and is not. It reappears once the open panel is saved or cancelled.
- ZIP-to-city lookups can have no plain match for a colloquial city name (63119 has no "St. Louis," only three real neighbouring municipalities). Pick a genuine option from the list rather than typing an unvalidated value, and note which one in the tracker.
- Identity verification needs no account: an email-only entry point gates final submission behind a six digit code mailed to that address, entered into six single-digit boxes. Retrieve it the same way as a Workday signup email, a second tab on the already-signed-in Gmail account.

**Check the whole page in one call, before pressing Save.** `pw/verify.js` returns the fields that are required and still empty, every field that does hold a value, and any visible error, all at once. `pw/fields.js` also reads `cx-select input` now, so it sees Oracle's comboboxes.

That exists because of what ETSU cost. Measured end to end: 50 minutes wall, 39 active, 162 tool calls of which 127 were browser calls, against 12 active minutes and 28 calls for RIT on a second Workday tenant. 121 of those 127 calls were re-reading page state one field at a time, and two of the run's errors were a required County and a required How Did You Hear About Us, both discovered only after a failed Save. The session that drove it reconstructed the split as roughly 5 minutes learning the comboboxes, 15 chasing a false data-loss alarm, 5 on the diversity and veteran fields, 5 on the email round trip, and the rest entering the four employers and two schools. Every one of those except the email round trip is a page-state question that one `verify.js` call answers.

### Attrax fronting SmartRecruiters, which is Harvard

`careers.harvard.edu` is an Attrax career site whose apply flow is SmartRecruiters (`jobs.smartrecruiters.com/oneclick-ui`, company `HarvardUniversity`). First mapped 11 Sep 2026. There is no account, no password and no sign-in anywhere in the flow, which makes it the cheapest platform met so far.

**`pw/fields.js` returns zero fields here, and that is not a broken page.** The UI is open shadow DOM: Playwright locators pierce shadow roots, the helper's in-page `evaluate` does not. Drive it with Playwright locators directly and skip the helper. Fixing `fields.js` to walk `shadowRoot` would remove the limitation, and is worth doing if more web-component ATSs turn up; it was left alone during a live bulk run rather than editing a helper every agent depends on.

Go straight to the `/Workflow?workflowId=...&vacancyId=...` href on the posting instead of clicking through the career-site shell. Harvard postings print a salary grade rather than a number, so a banded picklist takes `<profile>/profile.md`'s 100000 as `$91,000 - $100,000`. The mandatory Application Verification checkbox carries employer-contact authorisation and is the only path to Submit. The optional Supplementary Attachments field explicitly invites a cover letter, so build a one-page PDF rather than attaching a `.md`.

### Platforms that cannot be finished unattended

Two of these turned up on 11 and 12 Sep 2026, and both end in a captcha an agent may not complete. Route them to the user rather than spending an agent on a submit that cannot happen.

- **JazzHR** (`<tenant>.applytojob.com`), met on Eastern Connecticut State. Single page, no account, no login, **no draft save**, and the form ends in a required "Human Check" that is a Google reCAPTCHA v2. An agent can fill everything and cannot press the last button, and because there is no draft the filled state lives only in that browser tab. Fill it if the user is at the keyboard, otherwise do not start it.
- **Zoho Recruit** (`<tenant>.zohorecruit.com`), met on Main Digital 15 Sep 2026. Same shape as JazzHR: single page, no account needed (its "Please sign in to apply" line is optional), no draft save, and a required `CAPTCHA` field at the foot of the form. It is Zoho's own image captcha served from `/recruit/GenerateCAPTCHA`, not reCAPTCHA and not in an iframe, so none of the usual frame tricks apply and it is equally out of bounds. Do not start one unless the user is at the keyboard. Not yet known whether the captcha is tenant configuration or a Zoho default, so check the next Zoho tenant before writing it off. That tenant also had no cover letter slot at all.
- **Lever** (`jobs.lever.co/<tenant>`), met on Xsolla 15 Sep 2026. Usually the friendliest board there is: no account, inline one page form, resume parsed on upload. This tenant still carried **hCaptcha** on submit, fired by `#btn-submit` as a `getcaptcha` call with an image challenge, and nothing POSTs until it is solved. No draft save, so the filled tab must not be navigated. Treat Lever as fillable unattended but not submittable, the same as JazzHR and Zoho Recruit, and check whether the captcha is tenant configuration on the next Lever tenant.

- **Greenhouse embedded on a company site**, met on Current 15 Sep 2026. The embed is the awkward part: `pw/fields.js` reads nothing on the company page and the canonical board URL redirects back to it. Pull the iframe `src` and navigate straight to `job-boards.greenhouse.io/embed/job_app?for=<token>&validityToken=...&token=<job id>`, which is a plain page the helpers can read. Submit then POSTs `boards.greenhouse.io/embed/<token>/jobs/<job id>` and this tenant answered **HTTP 428** demanding a reCAPTCHA Enterprise token, with the checkbox challenge appearing above the button only at that point.

**Employer AI policies are now a thing to check before spending a resume, and they come in four kinds.** Seen on 15 Sep 2026. A **prohibition** on AI in application materials, which Air Apps carried with disqualification stated: this folder cannot honestly work such a role, so drop it and tell the user, which is what she chose. A **permission with disclosure**, which ID.me publishes at `insider.id.me/candidate-ai-use-in-interviewing/`: AI proofreading and refining a resume or letter is explicitly acceptable provided the ideas are the candidate's own, but the application must say that AI assisted it, so the disclosure goes in the letter and in any free-text field. An **interview-scoped request**, which Wolters Kluwer makes: no bearing on an agent-prepared application, but the user needs to know before an interview. And AI named as a **desired skill**, which HP, Ingenio, Bamboo Health, Amazon, Autodesk, PagerDuty, Williams-Sonoma and Mozilla all do, which is a positive rather than a restriction. Grep every brief for AI, artificial intelligence, ChatGPT, automated and assistance before tailoring.

- **Ashby** (`jobs.ashbyhq.com/<tenant>`), met on Credit Genie 15 Sep 2026, and the **best platform found so far**: no login, no password, no account step, and **submittable unattended**. reCAPTCHA v3 loads with its badge and a hidden `g-recaptcha-response`, and across two Submit clicks no challenge ever rendered. Three traps, all learned the hard way. A **validation failure also returns HTTP 200**, as `__typename: "FormRender"` carrying `errorMessages` and the server's stored value for every field, so read the response body and never trust the status code. A **draft does persist server side** (`ApiSetFormValue` fires per field), so a refused submit costs nothing and a lost tab is not fatal, unlike every other platform here. And `page.fill` **does not reliably reach Ashby's state**: two fields submitted as null while the DOM looked correct, so use `click`, then `fill`, then `press('Tab')`. A required **Current Location** combobox is also invisible to `pw/fields.js`.
- **Greenhouse react-select fields**: never `page.fill` one. It is unrecoverable in place, and the Country field on one form read back empty after a fill that appeared to work.

**Correction, same day, and it matters more than the rule it qualifies.** The Current `current81` tenant demanded reCAPTCHA Enterprise with an HTTP 428 on one attempt and then, hours later, accepted a single Submit click straight through to the confirmation page with no challenge at all. A Rippling Turnstile fired invisibly and passed. An isolved gateway advanced with zero reCAPTCHA frames. So a captcha wall is **not a stable property of a tenant**: it is risk-scored per attempt. **Always press Submit and see.** Never record a role blocked on a captcha you have only inferred, and never hand a form to the user without having tried the click first.

The pattern behind those four, learned in one day: **account-free does not mean finishable.** A captcha that only renders after the first Submit click is invisible to any reconnaissance pass, including a page fetch and a `pw/fields.js` read of the loaded form. The only reliable division of labour is that the agent fills and the human presses the last button, so fill the form, leave it in its own tab, and hand over the click rather than recording a dead end.
- **PageUp reached through a Clinch campus front end**, met on Kansas State. The front end's Apply Now widget POSTs to `/call_to_actions/<id>/form_submissions` and returns HTTP 422 "Invalid reCAPTCHA" every time, because the automated browser scores low. **Check for a direct PageUp URL first**: CSUN's `careers.pageuppeople.com/873/...` had no captcha at all and ran clean, and Tarrant County's `secure.dc4.pageuppeople.com/apply/994/gateway/default.aspx?...` skipped the Clinch widget entirely. The captcha belongs to the wrapper, not to PageUp.

Never attempt to solve, bypass or automate around a captcha. Record the application `blocked` with the exact response and say precisely what a human has to click.

### Interview Exchange (Hirezon)

Small ATS used by a number of campuses, first met on `albany.interviewexchange.com` 11 Sep 2026. Posting lives at `jobofferdetails.jsp?JOBID=<id>` and the form at `candapply.jsp?JOBID=<id>`.

The host returns HTTP 403 to `curl` but reads fine in a browser, so a 403 from `prep.py` on this platform is a bot block and not a dead requisition. The brief will have an empty `text` field, which means the posting has to be read in the browser and the hard filters checked there before any work starts.

One page, six numbered steps: account by email, resume upload, electronic forms, references, voluntary demographics, additional questions. Steps 2 to 6 stay hidden behind "Please complete Step 1 to view" until the account exists. **There is no Candidate Home and no draft.** Unlike Workday you cannot park a half-finished application and come back, and the resume upload itself begins the submission, so probing a later step to see whether it is enforced can file a resume-only application with no cover letter. Read the posting's Application Instructions for what the campus demands, and treat anything it lists as required, whether or not the form marks it with an asterisk.

### Answer traps that produce a false statement

These are worth more care than anything else on the form, because a wrong one is a lie on a signed document.

**The most dangerous field is not a picklist, it is a required free-text essay.** A picklist forces a wrong answer visibly; an essay invites one. On `careers.dallascollege.edu` on 11 Sep 2026 a required essay answered the posting's KSAs back at it and asserted requirements gathering, functional specifications, test plans and versioning discipline. None of those four appears anywhere in `<profile>/base/resume_base.tex` or `<profile>/profile.md`, and the application was submitted and cannot be recalled. Write an essay only out of what the record actually contains, name the gap where the posting asks for something absent, and never let the posting's own wording become the answer. A grep of `<profile>/base/resume_base.tex` for the nouns you are about to use costs one call and is the check that would have caught this.

- **Veteran status.** A loose match on `not a veteran` hits `I identify as a veteran, just not a protected veteran`, which asserts the opposite of the truth. Match `I am not a veteran` exactly. This went wrong twice in one session.
- **Race.** The user is from India, so the answer is Asian. `American Indian or Alaska Native` is the Native American category and is never right.
- **Years of experience banded as 1-4 or 5-9.** 57 months rounds to 5. Pick 5-9 and say so, or ask.
- **Why did you leave your last position.** The user is employed. `Still Employed` where offered.
- **How did you hear about us.** For anything found through the HigherEdJobs sweep the honest answer is HigherEdJobs, or the nearest job board option, never the university's own website. Some tenants offer neither HigherEdJobs nor Other while still making the field required, so every remaining option is an attribution the user did not make. `highpoint.wd503` offers only Career Builder, Connection in the company, HPU Website, Indeed and LinkedIn. Pick nothing, record the application `ready` with the full option list in the notes, and leave it for the user. Whatever gets typed to clear the field never goes in `<profile>/answers.json`, because the bank caches confirmed labels and this is a guess.
- **Are you related to anyone employed here.** Asked on three of the first seven tenants of the 10 Sep 2026 bulk run, always required, and `<profile>/profile.md` says nothing about the user's relatives. It is a decision, not a lookup, so it stops Submit. It was the single largest cost of that run. If the user ever answers it, that answer belongs in `<profile>/profile.md` rather than in the bank, because the bank keys on exact question wording and every tenant words this one differently.


## Found 19 Sep 2026: pw/fields.js misreads a committed Greenhouse react-select as empty

After clicking an option, the react-select's own `<select>` or hidden input still reports `value: ""` to `pw/fields.js`, because the selected label actually lives in a sibling `div[class*=singleValue]`, not in the control `pw/fields.js` reads. This means a page reload of `pw/fields.js` after filling ten pickers can show all ten as empty even when every one was set correctly. Do not treat that as a fill failure and re-click; check the sibling `singleValue` text (or `pw/verify.js`) before redoing work on a Greenhouse react-select.

Also worth noting: a bare Greenhouse embed board token does not always match the company name (Compass's is `urbancompass`, not `compass`). Read the token off the actual embed URL rather than guessing it from the company.

## Found 19 Sep 2026: Greenhouse rejects a .md or .txt cover letter upload

Engine's Greenhouse form returned "Invalid file format selected" for both a `.md` and a same-content `.txt` cover letter. Greenhouse's optional cover-letter field wants a document format (PDF or DOCX), not a plain-text file. Convert the letter before attaching, or paste it into a free-text cover-letter box if one exists, rather than uploading the raw `.md`.

## Found 19 Sep 2026: SmartRecruiters is shadow-DOM, pw/fields.js cannot read it

SmartRecruiters' apply flow (`jobs.smartrecruiters.com/.../oneclick` UI) is built entirely from `spl-*` web components inside shadow DOM. Both `pw/fields.js` and a plain `document.body.innerText` read return nothing useful there. Drive it with raw Playwright locators, which pierce shadow DOM, and use a scoped screenshot to verify rather than a text read. The resume-upload `<input>`'s `files` property also reads back empty by design even after a successful upload; verify success from the network response (`POST .../attachment/resume` returning 200) instead of the input's own state.

## Found 19 Sep 2026: a mislabeled Greenhouse "Country" field can silently block Submit

On AlphaSense's Greenhouse form, a field labelled plainly "Country" was actually the phone country-code selector, and leaving it unset blocked two Submit attempts with no visible error text. This is the same trap already noted above (a field labelled `Country*` is usually the phone-country select), but here it failed silently instead of showing `#race`-style gating or an obvious error. If Submit does nothing and no error appears, check every "Country" field on the page and confirm it has a value, even if it looks already filled.

## Set 24 Sep 2026: a Greenhouse form in about eight calls

Timed on OLIVER (submitted, 7.3 minutes, 98 tool calls): each react-select took three calls (open, list options, click), twelve of them came to 36 calls, and the location autocomplete took four attempts. The order that avoids all of it:

1. `pw/fields.js` once, for every field id and label.
2. One `browser_fill_form` for every plain text field and textarea.
3. One `browser_evaluate` setting `window.__ghWant = {"<id>": "<exact label>", ...}` for every react-select plus `"candidate-location": "Chicago"`, then `browser_run_code_unsafe` with `filename: pw/gh_select.js`. It returns what it set, and `{miss, near, total}` for any label with no exact match, which you then resolve from `<profile>/profile.md` and run again for those ids only.
4. One `browser_run_code_unsafe` calling `setInputFiles` on `#resume` and `#cover_letter` (PDF, never `.md`).
5. `pw/verify.js` or one alert/error read, then Submit, then one read of the confirmation.

Found on the first live run (Okta, 24 Sep 2026, 2 minutes, 12 browser calls): the phone-country option reads exactly `United States +1`, not `United States`; and a company that embeds its board (Okta) redirects `job-boards.greenhouse.io/<token>/jobs/<id>` back to its own site, while `job-boards.greenhouse.io/embed/job_app?for=<token>&token=<id>` loads the form directly.
