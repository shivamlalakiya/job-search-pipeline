// Advance one Workday page and report where you landed, in one call.
//
// Clicks the page's forward button through the invisible overlay, waits for the
// step or the field set to actually change rather than for a fixed number of
// seconds, and returns the new page's fields. Run with browser_run_code_unsafe's
// `filename`.
//
// It will not press Submit. Submitting is the one irreversible action on the
// form and it stays an explicit, deliberate call.
async (page) => {
  const FORWARD = ['Save and Continue', 'Continue', 'Next', 'Save and Next'];
  const snapshot = () => page.evaluate(() => {
    const vis = (e) => !!(e.offsetParent || e.getClientRects().length);
    const fields = Array.from(document.querySelectorAll('input, select, textarea, [role=combobox]'))
      .filter(vis).map((e) => e.id || e.getAttribute('data-automation-id') || e.name || '');
    const body = document.body.innerText;
    // Two tenants broke the naive read. tcsedsystem.wd1 renders it lower case,
    // so the original /Step \d+ of \d+/ matched nothing and the numbered-step
    // guard silently never ran. theclaremontcolleges.wd1 lists every step in a
    // progress rail, so a case-insensitive first match pinned it at "step 1 of
    // 7" forever, next.js never saw an advance, and it clicked forward twice and
    // skipped a whole page. The word "current" is what marks the live step, so
    // prefer it and fall back only when the tenant does not use it.
    const step = (body.match(/current step \d+ of \d+/i) || body.match(/step \d+ of \d+/i) || [''])[0];
    const alerts = Array.from(document.querySelectorAll('[role=alert], [data-automation-id*=errorMessage]'))
      .map((e) => e.innerText.replace(/\s+/g, ' ').trim()).filter(Boolean);
    return { step, alerts, keys: fields.join('|') };
  });

  const before = await snapshot();
  let clicked = null;
  for (const name of FORWARD) {
    // Workday puts an invisible overlay over its buttons, so the click has to
    // land on the click_filter div rather than on the button itself.
    const overlay = page.locator(`div[data-automation-id="click_filter"][aria-label="${name}"]`);
    const button = page.getByRole('button', { name, exact: true });
    if (await overlay.count()) { await overlay.first().click(); clicked = name; break; }
    if (await button.count()) { await button.first().click(); clicked = name; break; }
  }
  if (!clicked) return { ok: false, reason: 'no forward button on this page', before };

  // An alert is only a failure if it is new AND it reads like one. Workday
  // leaves the "successfully uploaded" confirmation in the DOM as [role=alert]
  // for the rest of the session, so treating any alert as a failure reported
  // ok:false on every advance of a tenant that had taken a resume upload.
  const BAD = /error|required|invalid|must |cannot|can't|failed|unable|not valid|please (enter|select|correct)/i;
  const isNew = (a) => !before.alerts.includes(a);

  const settle = async (via) => {
    for (let i = 0; i < 30; i++) {
      await page.waitForTimeout(300);
      const now = await snapshot();
      const fresh = now.alerts.filter(isNew);
      const errors = fresh.filter((a) => BAD.test(a));
      if (errors.length) return { ok: false, clicked, errors, step: now.step };
      // A changed field set is only proof of an advance when the page has no
      // step counter. Workday renders a validation failure such as "Invalid
      // LinkedIn URL" as a new field key before it renders it as an alert, so
      // a keys-only change on a numbered step is a failed save that looked like
      // a success to the agent that hit it on hhmi.wd1. The step counter is the
      // tell: if it has not moved, the page has not advanced.
      if (before.step ? now.step !== before.step : now.keys !== before.keys) {
        await page.waitForTimeout(300);
        const settled = await snapshot();
        const notes = settled.alerts.filter(isNew).filter((a) => !BAD.test(a));
        return { ok: true, clicked, step: settled.step, ...(via ? { via } : {}), ...(notes.length ? { notes } : {}) };
      }
    }
    return null;
  };

  const first = await settle();
  if (first) return first;

  // Not every tenant puts a click_filter overlay on the footer. Where it is
  // missing the overlay click lands on nothing and the page never moves, which
  // looked like a silent success to the agents that hit it on bentley.wd503 and
  // brown.wd5. Click the footer button itself once before giving up.
  const footer = page.locator('button[data-automation-id="pageFooterNextButton"]');
  if (await footer.count()) {
    await footer.first().click();
    const second = await settle('pageFooterNextButton');
    if (second) return second;
  }

  const stuck = (await snapshot()).alerts.filter(isNew);
  return {
    ok: false, clicked, step: before.step,
    reason: 'page did not change within 9s, footer button fallback included',
    ...(stuck.length ? { alerts: stuck } : {}),
  };
}
