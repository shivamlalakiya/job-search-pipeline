# Outreach: the recruiter email

_Split out of `CLAUDE.md` on 10 Sep 2026. A cross-reference to a section "below" or "above" that is not in this file means the sibling file under `docs/`._

## Current rules, read this first (24 Sep 2026)

The sections below are history and several are superseded. What holds now:

1. A named human who owns or sits near the role, never a shared mailbox.
2. Permission is per person, in `<profile>/profile.md` "Outreach permission". Some profiles allow published addresses only and hold the rest as drafts; others also allow example-derived and aggregator-pattern addresses.
3. Hold a common name at a large company rather than risk the wrong real person.
4. Subject is `<Role>, req <id>` with the employer's own ATS id (Greenhouse job id, Workday JR number), not the LinkedIn job id in the brief.
5. **At most 2 emails per role, ever** (set by the user 4 Nov 2026: "keep only max 2 email not more than that"). That counts the first email, any bounce retry and the follow-up. So a bounce gets one retry and no follow-up; a delivered email gets one follow-up (`python3 outreach/bounces.py followup --send`, 7 or more days later, no reply) and no retry if the follow-up bounces. Bounces are handled by `python3 outreach/bounces.py --retry --send`, which enforces the cap (`--max 2`). Do not hand-queue a retry.
6. State years of experience exactly as `<profile>/profile.md` words them.

## Outreach

Email is a supplement to the ATS application, never a replacement. Write the body to `<profile>/outreach/<slug>.txt`, then `python3 outreach/mkemail.py --to ... --subject ... --body ... --attach ...` to build the `.eml`. Add `--send` when the address is `found`, which the user authorised on 9 Sep 2026. A `derived` address is built and held until the user says yes, unless that person's `profile.md` already authorises derived addresses.

The whole of this section is the `outreach` agent's job, defined in `.claude/agents/outreach.md`. Spawn one per application, in the background, the moment the application is recorded as submitted, and carry on to the next form. It gets the company, the role, the apply URL, the tailored resume path and the brief path, and it has no browser tools, so it cannot take the Playwright profile from the main thread. A new agent file is not spawnable until the session restarts; until then use `general-purpose` with the same file as the prompt.

- **Permission to send is per person**, recorded under "Outreach permission" in `<profile>/profile.md`. The profile is the authority, this file is not, so check it before assuming either way. A profile whose standing permission covers derived addresses also has an empty `<profile>/autosend` file, which makes the bulk run's bounce retry send instead of only drafting.
- Sender is the `from:` line of `<profile>/signature.txt`, and the Gmail app password comes from the macOS keychain item named on its `keychain:` line. Never print, echo or commit the credential.
- `outreach/mkemail.py` builds and sends. It replaced `send_emails.py`, whose imports (`contacts.py`, `jd.json`, `resume_build.json`) were left in a Downloads folder that no longer exists; that version is in `profiles/archive/` for reference only.
- Email whenever a contact can be found, per the user's decision of 9 Sep 2026. Two kinds of contact, two kinds of email:
  - The recruiter, hiring manager or anyone who owns the role: the direct pitch. Why this role, what in the user's record maps onto it, resume attached.
  - Anyone else at the company: a shorter note showing interest in the role, and asking whether they would be willing to pass it on to the hiring manager or connect. Resume attached.
- Always attach the tailored resume, on both kinds.
- The signature is the block below the `--` line in `<profile>/signature.txt`, read by `outreach/mkemail.py` at startup, and carries the phone, the email, LinkedIn, GitHub and a portfolio link. It is appended to every message, so never hand-write a signature into a body file. Change it in that one file if it ever needs changing, and never sign a message with the other profile's details.
- **A named human, or nothing.** Never use `recruiting@`, `careers@`, `jobs@`, `hr@` or any other generic or shared mailbox as the contact for a role. They route into the ATS the application already went through, so the email adds nothing. If no individual can be evidenced, leave the contact blank rather than filling it with a mailbox. Set by the user 9 Sep 2026.
- Mark the address `found` when the company published it verbatim and `derived` when it was built from the company's observed address format. A derived address can bounce, so watch for a non-delivery report before trusting it, and get a quick yes from the user before sending to one unless their `profile.md` already gave a standing yes.
- **`derived` means you saw a real address at that same domain and copied its shape. Nothing else qualifies.** Added 15 Sep 2026 after the user reported in chat that almost all of that day's 21 sends were wrong. A same-session audit then checked all 21 against Gmail bounce reports and each company's own published pages, and confirmed the report: 8 of 21 had bounced. Only three of the 21 cited an actual example address: one from a company media kit, one from a press release, one from a BusinessWire release. The other eighteen were built from a RocketReach, ZoomInfo, LeadIQ or ContactOut **pattern percentage**, and one of those was recorded in its own note as "only about 49 percent coverage", which is a coin flip sent to a named stranger.
- **SUPERSEDED IN PART, 18 Sep 2026: the user relaxed this after seeing what it cost.** Shown that the strict bar below was yielding about one send per ten roles, because most companies publish only shared mailboxes and no named example, she explicitly authorised sending to **aggregator-pattern-derived addresses**, accepting that roughly a third may bounce. Her reasoning is the obvious one: a bounce costs nothing, and a backlog of sixty researched contacts with no email sent is worth less than forty delivered messages and twenty non-delivery reports. So an aggregator majority pattern is now a legitimate basis for sending, recorded `--address-verified unverified` with the pattern and its percentage in the row note.
- **What did NOT change, and should not:** an email that lands on a real but wrong person is still worse than a bounce. Where a name is common at a large company, that single row is still held rather than guessed at, which is why Instacart's Laura Jones was held on 18 Sep while fourteen siblings went out. The rule is now "guess the pattern, do not guess the person."
- The strict standard below remains the right default for a fresh run. It was relaxed here because sixty applications were already submitted and sitting uncontacted, which is a specific situation, not a general licence.
- **An aggregator percentage is not evidence and never makes an address `derived`.** RocketReach saying "86.4 percent first-initial-last" is a claim about a scraped sample, not about this person, and it is wrong often enough that `instacart.com` holds both `caiman.howe@` and `tom.maguire@`. A masked address such as `t***@creditgenie.com` confirms only the domain and the first letter, so it cannot distinguish `tkassoff@` from `tamar.kassoff@`. Where the only support is an aggregator, the address is **unverified**: record the name and the title, leave the email blank, and do not send.
- **Where two patterns are close, that is a stop, not a tiebreak.** The Mindgruve send picked `first_initial+last` on 49.2 percent against 45.2 percent for `first.last`. Those numbers mean the pattern is unknown.
- **One named human, one attempt.** Do not queue a "retry on bounce" second guess at the same person. A second message to someone who never received the first reads as a stranger guessing at their address twice. If the first address is unverified, the answer is not to send it and plan a retry, it is not to send.
- When no address can be evidenced, the outreach still has somewhere to go: a LinkedIn message to the named human, or the recruiter contact the ATS itself exposes on the application. Both reach a person without guessing at a mailbox.
- Then `python3 jobs.py add-outreach --company X --role Y --contact-name N --email E --email-confidence found --status sent`.
- Record replies and bounces on the same row by re-running `add-outreach` with the same company and role. It updates in place rather than appending.


## Measured on 19 Sep 2026: what the bounce set proved

Nineteen of roughly sixty sends bounced, almost exactly the third the user accepted when she loosened the rule. Reviewing all nineteen gave the first evidence-based ranking of address shapes, so prefer them in this order:

1. **A verbatim named example at that exact domain**, seen on a press release, a published contact page or a posting. Every address of this class is still outstanding rather than bounced. This is the only tier that has never failed.
2. **An alternate or successor domain with its own evidence.** Realtor.com's mail lives at `avail.co`, not `avail.com`; NetBrain's at `netbraintech.com`. A company's marketing domain is not automatically its mail domain, and checking this cost nothing and saved a send.
3. **A shorter shape.** `first.last@` guesses bounced far more often than `flast@` or `first@`. Where an aggregator gives two close percentages and one is shorter, the shorter one is now the better bet, though two close percentages still mean the pattern is unknown.
4. **An aggregator percentage alone**, which stays the weakest tier and is recorded `unverified`.

Three diagnostics worth keeping, because they tell you what a bounce actually means:

- **A clean bounce on a shape you have verbatim evidence for means the person, not the pattern.** One company proved it: a colleague's `first.last` address delivered, so the shape was right and the bounced contact had left. That makes the bounce a signal to retarget to a different current human, not to guess again.
- **A gateway "message blocked" is not an address-not-found.** Bass Pro Shops rejected the message rather than the mailbox, so the address probably exists and a different one at the same domain hits the same filter. Email is closed at that company; do not burn another guess.
- **A common surname at a large company is a collision risk regardless of pattern confidence.** Two `<initial><surname>` addresses at large companies were both held on this ground even though the shape was well supported, because the message would reach *a* real person, just possibly the wrong one. That failure is worse than a bounce, since nothing tells you it happened.

**The rule on bounces themselves:** a bounce means nothing was delivered, so a corrected address is the first delivery and not a second email. This does not reopen "one named human, one attempt", which still forbids firing a different guess at the same person. A resend requires the new address to be *better evidenced* than the one that failed. If you cannot do better, leave the row bounced and record what you ruled out.


## Set 24 Sep 2026: bounces are monitored and retried (cap cut to 2 emails per role on 4 Nov 2026, see "Current rules")

The user asked for every sent email to be checked for a bounce and retried until it is delivered, up to a limit. This replaces "one named human, one attempt" above for the bounce case. `python3 outreach/bounces.py` reads the profile's Gmail over IMAP (same keychain app password as sending), finds mailer-daemon reports whose failed recipient is still a `sent` row, and marks the row `bounced`. With `--retry` it builds the next untried shape for the same named person, shortest shapes first per the 19 Sep ranking, from the same body file; with `--send` it sends it, sets the row back to `sent` on the new address and adds it to the `Tried` column. It stops a row at `--max` addresses (5), on a 5.7.x policy block or a note saying the gateway blocked it (Bass Pro), and when the row has no contact name.

The first run, 24 Sep 2026, found 29 bounce reports; 11 rows the tracker still called `sent` had in fact bounced.

What still holds: where a note says the person has left (a clean bounce on a shape already proven at that domain, the Hinge Health case), another shape at the same person is wasted. Retarget to a different current human instead and reset `Tried` for the new contact.
