// Report the current page: step, alerts, every visible field with its value,
// and the clickable things. Works on any ATS, not just Workday. Run with
// browser_run_code_unsafe's `filename`.
//
// Takes no arguments, because the tool passes nothing but `page`. Waits on the
// page settling rather than on a clock: a blind waitForTimeout either sleeps
// longer than needed or not long enough, and the 9 to 10 Sep run spent 511
// seconds of a two hour window inside them.
//
// Every field, button and link comes back with a `sel` you can pass straight
// to page.fill or page.click in the next call. That is what makes this a
// replacement for browser_snapshot rather than a supplement to it: a snapshot
// of one NSU page cost several thousand tokens on 10 Sep, mostly nav, footer
// and a related-jobs widget, and the only thing it was needed for was a
// handle to click.
async (page) => {
  const read = () => page.evaluate(() => {
    const vis = (e) => !!(e.offsetParent || e.getClientRects().length);
    const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
    // Last resort: the text of the widest ancestor that holds no other
    // control. Lever's custom questions put the question in a sibling div with
    // no <label for>, so all seven required textareas on tendo came back with
    // blank labels on 24 Sep 2026 and cost an extra page read.
    const own = (e) => {
      let t = '';
      for (let n = e.parentElement, i = 0; n && i < 5; n = n.parentElement, i++) {
        if (n.querySelectorAll('input, select, textarea, [role=combobox]').length > 1) break;
        t = n.innerText;
      }
      return t;
    };
    const label = (e) => clean(
      e.labels?.[0]?.innerText
      || e.getAttribute('aria-label')
      || e.closest('[data-automation-id]')?.querySelector('label')?.innerText
      || own(e)
      || '', 120);
    // A selector the caller can act on without a snapshot. #id first, then the
    // attributes that survive a re-render. Hyphens are legal in a CSS id, so
    // only the genuinely special characters are escaped.
    const sel = (e) => {
      const tag = e.tagName.toLowerCase();
      const attr = (a) => e.getAttribute(a);
      // A CSS id selector cannot start with a digit, and Workday hands out ids
      // like 6f2ca... on some tenants. '#6f2ca' throws when it reaches
      // page.check, so fall back to an attribute selector, which has no such
      // rule. Seen on wpi.wd5 11 Sep 2026.
      if (e.id) return /^[A-Za-z_-]/.test(e.id)
        ? '#' + e.id.replace(/([^\w-])/g, '\\$1')
        : `[id="${e.id.replace(/"/g, '\\"')}"]`;
      if (attr('name')) return `${tag}[name="${attr('name')}"]`;
      if (attr('data-automation-id')) return `[data-automation-id="${attr('data-automation-id')}"]`;
      if (attr('aria-label')) return `${tag}[aria-label="${attr('aria-label')}"]`;
      return '';
    };
    // cx-select is Oracle Cloud HCM's combobox. Its inner input holds the
    // value, and that value silently clears on blur when the dropdown option
    // was never clicked, so it has to be read like any other field.
    // A committed Workday prompt value does not stay in the input. It becomes a
    // pill rendered as [data-automation-id="selectedItem"] next to the field,
    // so the input reads back empty and keeps aria-required, and an agent that
    // believes that clicks in to fix a field that was already right. That cost
    // a 30 second timeout on hhmi.wd1 on 10 Sep 2026 and could have overwritten
    // a correct answer. Read the pill when the input itself is empty.
    const committed = (e) => {
      let n = e.parentElement;
      for (let i = 0; i < 4 && n; i++, n = n.parentElement) {
        // Once an ancestor holds more than one control it is a row, not this
        // field's own widget, and any pill inside it may belong to a sibling.
        // That is how a Country Phone Code pill was read as a Phone Extension.
        if (n.querySelectorAll('input, select, textarea, [role=combobox]').length > 1) return '';
        const picked = Array.from(n.querySelectorAll('[data-automation-id="selectedItem"]'))
          .map((p) => p.innerText.replace(/\s+/g, ' ').trim()).filter(Boolean);
        if (picked.length) return picked.join(', ');
      }
      return '';
    };
    const fields = Array.from(
      document.querySelectorAll('input, select, textarea, [role=combobox], cx-select input')
    ).filter(vis).map((e) => ({
      id: e.id || e.getAttribute('name') || e.getAttribute('data-automation-id') || '',
      sel: sel(e),
      type: e.type || e.tagName.toLowerCase(),
      label: label(e),
      value: e.type === 'checkbox' || e.type === 'radio' ? e.checked : (e.value || committed(e)),
      required: e.required || e.getAttribute('aria-required') === 'true',
    }));
    const clickable = (nodes, cap) => {
      const seen = new Set();
      const out = [];
      for (const e of Array.from(nodes).filter(vis)) {
        // The overlay div and the button underneath it share their text. Drop
        // the overlay here: next.js already knows to click through it, and
        // keeping it was the only reason to dedupe on text alone.
        if (e.getAttribute && e.getAttribute('data-automation-id') === 'click_filter') continue;
        const text = clean(e.innerText, 60);
        // Dedupe on text plus selector, not text alone. Three separate required
        // dropdowns on tcsedsystem.wd1 all read "Select One", and keying on the
        // text hid two of them from the caller entirely.
        const s = sel(e);
        const key = text + '\u0000' + s;
        if (!text || seen.has(key)) continue;
        seen.add(key);
        out.push({ text, sel: s });
        if (out.length >= cap) break;
      }
      return out;
    };
    const buttons = clickable(document.querySelectorAll('button, [role=button], input[type=submit]'), 30);
    const links = clickable(document.querySelectorAll('a[href]'), 25);
    const alerts = Array.from(document.querySelectorAll('[role=alert], .css-error, [data-automation-id*=errorMessage]'))
      .map((e) => clean(e.innerText, 200)).filter(Boolean);
    const body = document.body.innerText;
    // Two tenants broke the naive read. tcsedsystem.wd1 renders it lower case,
    // so the original /Step \d+ of \d+/ matched nothing and the numbered-step
    // guard silently never ran. theclaremontcolleges.wd1 lists every step in a
    // progress rail, so a case-insensitive first match pinned it at "step 1 of
    // 7" forever, next.js never saw an advance, and it clicked forward twice and
    // skipped a whole page. The word "current" is what marks the live step, so
    // prefer it and fall back only when the tenant does not use it.
    const step = (body.match(/current step \d+ of \d+/i) || body.match(/step \d+ of \d+/i) || [''])[0];
    return { title: document.title, step, alerts, fields, buttons, links };
  });

  // Settled means two identical reads 400ms apart, capped so a page that keeps
  // repainting still returns something rather than hanging.
  let last = JSON.stringify(await read());
  for (let i = 0; i < 12; i++) {
    await page.waitForTimeout(400);
    const now = JSON.stringify(await read());
    if (now === last) return JSON.parse(now);
    last = now;
  }
  return JSON.parse(last);
}
