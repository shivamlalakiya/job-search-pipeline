# Resume tailoring and the long-answer fields

_Split out of `CLAUDE.md` on 10 Sep 2026. A cross-reference to a section "below" or "above" that is not in this file means the sibling file under `docs/`._

## Resume

The instruction is a genuinely optimised one page, not a reformatted base file.

1. If the company already has a resume from a different role, move the old PDF to `profiles/archive/` with the old role and req in the filename first, and point that tracker row's `--resume` at the new path. Otherwise the build silently overwrites it.
2. Names carry the req id: resume `Resume_<Name>_<Company>_<req>.tex`, cover letter `<profile>/applications/<Company>_<req>.md` plus its `.docx`. `cp <profile>/base/resume_base.tex <profile>/resumes/Resume_<Name>_<Company>_<req>.tex`.
3. Rewrite the Professional Summary for this posting, using the posting's own vocabulary. Reorder skill lines so the tools the posting names appear first. Reorder or trim bullets so the most relevant work sits at the top of each role.
4. Every number, employer, date and claim must already exist in `<profile>/base/resume_base.tex`. Sharpening wording is fine. Adding a skill, a tool, a metric or a year is fabrication, and it goes on a document the user signs. Do not do it.
5. Cutting is how it stays one page. Extra-Curricular is the first section to drop, then the oldest role's weaker bullet. Never shrink the font below 11pt or the margins below 0.4in.
6. `python3 jobs.py resume <profile>/resumes/Resume_<Name>_<Company>_<req>.tex`. It compiles with pdflatex, writes the PDF beside the source under the same name, and exits non-zero unless the output is exactly one page. **`base/resume_base.tex` is exempt from that gate**, the same way it is exempt from the fabrication audit: it is the full record of what may be claimed, not a document that gets sent, and it is expected to hold more than one page of content. One profile's base needed about 20 lines removed to fit a page, measured 15 Sep 2026, and every spacing lever was already spent before that number was taken. The one-page rule belongs to the copy, which is cut per posting.

Rewording a skill to match the posting's vocabulary is fine when the underlying thing is on the resume: "ETL development" and "data integration" for the existing ETL and Airflow work, "data modeling" for the existing DBT bullet. Adding a tool the posting names but the resume does not have is not. On the RWJBarnabas Data Engineer II req that meant leaving out Epic, SSIS, Informatica and Talend, and saying so in the cover letter instead.

Keep the `.tex` next to the `.pdf`. The next tailoring for a similar role starts from it rather than from scratch.

## Tailor hard. The limit is truth, not effort.

Added 14 Sep 2026. A resume that is not visibly rewritten for the posting is a wasted send. Rewrite aggressively for every single application: the only thing that does not move is whether a claim is true.

**Do all of this, every time:**

1. **Mine the posting first.** `python3 ats.py --text <url>` prints the sentences to tailor against. Pull out its exact nouns: tool names, metric names, method names, the words it uses for the work. That vocabulary list is the target.
2. **Rewrite the summary from scratch** for this posting. Not a tweak. It should read as though it were written for that one job, because it was.
3. **Mirror the posting's own words** for work that is already on the record. Same underlying thing, their vocabulary: "lift analysis" becomes "incrementality testing" if that is their phrase, "campaign performance reporting" becomes "marketing measurement", "dashboarding" becomes whatever noun they use. This is the single highest-yield move and it is entirely honest.
4. **Reorder everything.** Skill lines so their named tools come first, and retitle the skill categories to match their categories. Bullets so the most relevant sits at the top of each role. Roles stay in date order, but their bullets do not.
5. **Rewrite bullets to lead with the outcome the posting cares about.** The same true fact can be framed around cost per acquisition, or around stakeholder adoption, or around pipeline reliability. Pick the framing their posting asks for.
6. **Mine the whole record, not just the bullets.** Coursework, project links, the GitHub repos, tools named anywhere in the `.tex`, anything in `<profile>/profile.md`. A skill that appears only in a project is still a real skill and belongs in the skills section when the posting asks for it.
7. **Cut without mercy** to make one page. The least relevant role loses bullets first.

**The line, and why it is where it is.** Every tool, number, employer, date and responsibility must already be true. Do not add a tool the posting names and the record does not support, do not invent a project, and do not stretch a date. Not because tailoring should be timid, but because the user signs this, tool claims get tested in a technical screen, and an offer withdrawn or a job lost at month three is a far worse outcome for someone already out of work than one interview not landed. Rewrite the presentation as hard as you like. Never move the facts.

**When the posting names a tool the record does not have, ask her.** The record is what has been written down so far, not the limit of what she has done, and a two-line question is cheaper than losing the role. Do it like this:

1. Collect the missing tools across the batch you are working on and ask in one message, not one per application: "This posting wants Looker, GA4 and dbt. Have you used any of them, and at what depth?"
2. Whatever she confirms, write it into `<profile>/base/resume_base.tex` in the skills section, and log it in the stated-skills table in `<profile>/profile.md` with the date and her own words. The base file is the source of truth that `jobs.py resume` audits against, so a skill that is not in it will be flagged on every tailored copy.
3. From that point it is an ordinary fact and needs no special handling.
4. What she does not confirm is a gap. Handle it below. Do not put it on the page and do not ask her twice.

Her answer is the authority here, not the current contents of the `.tex`. The agent never decides that she has a skill.

**What to do with a genuine gap, in order of preference:**

- **Close it for real.** If the missing tool is learnable in days and the user wants the role, say so and let them build something real with it. Once the project exists it goes on the resume as a project with its own bullet, and it is true. This is the only way a new skill ever appears on the resume.
- **Name the nearest true thing.** Missing Looker but has Tableau and Power BI, missing Snowflake but has BigQuery: put the real one forward and let the transferability be obvious. Do not claim the one they asked for.
- **Answer it in the cover letter.** This is what the cover letter is for. Name the gap in one clause, then the closest real experience, then the concrete intent to close it. "I have not used Adobe Target; I have run A/B and incrementality reads in [real tool] and would be productive in it quickly" is credible and costs nothing. A recruiter reading that trusts the rest of the page more, not less.

Willingness to learn belongs in the cover letter and the free-text fields, where it is a statement about the future. It never belongs in the skills section or a work bullet, which are statements about the past.

## Free-text fields and the cover letter

A resume is one page because paper is finite. An application form is not, and the long-answer fields are where an application is won or lost.

- Write a cover letter every time there is a field for one, even when it is marked optional. Address it to the recruiter or hiring manager by name when the posting or the careers page gives one. Use it for the substance that did not fit on the page: the project that got cut, the second half of a bullet, why this particular company.
- When a form asks you to describe a role, do not paste the resume bullet. Expand it. Say what the system was, what you built, what tool you used, what changed as a result. Three to six bullets per role is right where the resume has two or three.
- List every skill the posting names that the user actually has. The resume trims the skills section to fit; a form has no such limit.
- The hard boundary, and it is not negotiable: everything you write must trace back to `<profile>/base/resume_base.tex`, `<profile>/profile.md` or `<profile>/LOG.md`. Expanding a real bullet with real context is the job. Inventing a project, a tool, a metric, a responsibility or an interest is fabrication on a document the user signs. If a field invites something the user's record does not support, write less rather than filling it with something untrue or off-topic.


## The missing-skill loop, and what to do while the user is willing to learn

Added 14 Sep 2026 after the user asked that a skill named on a posting be added to the
resume on the strength of her willingness to learn it before an interview. The willingness
is real and it is worth a lot. Where it goes is the whole question, and the answer is: into
the record first, then onto the page.

**Run the loop on every batch, not at the end.** The reason a missing tool ends up feeling
like a choice between lying and losing the role is that nobody asked in time. Ask at step 1
of the batch, before a single resume is built:

1. While reading the briefs, collect every tool, method and platform the postings name that
   `<profile>/base/resume_base.tex` and `<profile>/profile.md` do not already support. Deduplicate
   across the whole batch.
2. Ask her once, in one message, naming the tools and the roles that want them, and asking
   at what depth she has used each. Not one question per application.
3. Anything she confirms goes straight into the skills section of
   `<profile>/base/resume_base.tex`, and into the stated-skills table in `<profile>/profile.md` with
   the date and her own words. From that point it is an ordinary fact on every later resume
   and needs no special handling. This is the fast path and it is usually wider than the
   `.tex` suggests, because the base file is what has been written down, not the limit of
   what she has done.
4. Anything she has not used is a gap, and the three moves below are how a gap gets
   answered. Do not ask twice and do not put it in the skills section.

**Willingness to learn is a statement about the future, so it goes where the future goes.**
The skills section and the work bullets are claims about the past that a technical screen
tests directly. The cover letter, the "anything else we should know" box and the interview
are where "I have not used X, I have done the same work in Y, and I will be productive in X
quickly" reads as confidence rather than as a claim. Put it there, in those words, every
time a posting names something she does not have. A recruiter who sees one named gap trusts
the rest of the page more, not less.

**Close the gap for real when the role is worth it.** If the missing tool is learnable in
days and she wants that job, say so and let her build something real with it. A weekend
project with a repo is a true project, it gets its own bullet, and it survives the screen.
This is the only route by which a new skill ever appears on her resume, and it is genuinely
fast: most of what these postings name is a week of work for someone who already has the
SQL, the Python and the Tableau.

**Name the nearest true thing, loudly.** Missing GA4 but has campaign performance reporting
on real customer behavioural data. Missing Looker but has Tableau and Power BI. Missing
Adobe Target but has run A/B and incrementality reads. Lead with the real one in the
posting's own vocabulary and the transferability argues itself.

**Everything above the line still applies and is where the yield actually is.** Rewrite her
summary from scratch per posting, mirror the posting's exact nouns for work already on the
record, retitle the skill categories to match theirs, reorder every bullet, and reframe each
one around the outcome that posting cares about. That is not a smaller lever than adding a
tool she does not have. It is a bigger one, and it costs nothing.
