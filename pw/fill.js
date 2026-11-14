async (page) => {
  // Fill every native field on a page in one call. Apply sessions wrote 2,119
  // one-off inline snippets between 29 Oct and 14 Nov 2026, most of them one
  // field each. A helper takes no arguments, so set the values first:
  //   browser_evaluate: () => { window.__want = {"#firstName": "Alex", "#state": "Illinois", "#agree": true} }
  // Keys are the `sel` values pw/fields.js returns. Values: text for an input
  // or textarea, the exact option label for a <select>, true or false for a
  // checkbox or radio, a file path for a file input.
  // Every value is read back after the field loses focus, because some ATSs
  // clear a field on blur (Oracle's cx-select, Paylocity's dates). Returns
  // {set: [...sel], bad: {sel: why}}; nothing is ever picked by a fuzzy match.
  // Custom widgets (react-select, antd, Workday prompts) are not native and
  // come back in `bad`: use their own recipe in docs/ats.md.
  const want = await page.evaluate(() => window.__want || {});
  const set = [], bad = {};
  for (const [sel, value] of Object.entries(want)) {
    // the --secrets substitution happens only in browser_type and
    // browser_fill_form, so a placeholder here would be typed literally
    if (typeof value === 'string' && /^[A-Z][A-Z0-9_]*_PASSWORD$/.test(value)) {
      bad[sel] = 'secret placeholder: type it with browser_type, never fill.js';
      continue;
    }
    const el = page.locator(sel).first();
    if (!(await el.count())) { bad[sel] = 'not found'; continue; }
    const kind = await el.evaluate((e) => ({
      tag: e.tagName.toLowerCase(), type: (e.type || '').toLowerCase(),
      options: e.tagName === 'SELECT' ? [...e.options].map((o) => o.label.trim()) : null,
    }));
    try {
      if (kind.type === 'password') { bad[sel] = 'password field: type it with browser_type'; continue; }
      if (kind.tag === 'select') {
        if (!kind.options.includes(String(value))) {
          const words = String(value).toLowerCase().split(/\W+/).filter(Boolean);
          bad[sel] = { miss: value, near: kind.options.filter((o) => words.some((w) => o.toLowerCase().includes(w))).slice(0, 15), total: kind.options.length };
          continue;
        }
        await el.selectOption({ label: String(value) });
      } else if (kind.type === 'checkbox' || kind.type === 'radio') {
        await el.setChecked(!!value);
        if ((await el.isChecked()) !== !!value) { bad[sel] = { want: !!value, got: !value }; continue; }
      } else if (kind.type === 'file') {
        await el.setInputFiles(String(value));
      } else {
        await el.click();
        await el.fill(String(value));
        await el.press('Tab');
        const got = await el.inputValue();
        if (got !== String(value)) { bad[sel] = { want: value, got }; continue; }
      }
      set.push(sel);
    } catch (e) {
      bad[sel] = String(e.message || e).split('\n')[0].slice(0, 200);
    }
  }
  return { set, bad };
}
