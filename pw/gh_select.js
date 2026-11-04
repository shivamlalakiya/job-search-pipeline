async (page) => {
  // Fill every Greenhouse react-select in one call instead of three per field
  // (open, list options, click). Measured 24 Sep 2026 on OLIVER: 12 selects
  // cost 36 tool calls and about 3 of the 7 minutes. A helper cannot take
  // arguments, so set the wanted labels first, then run this file:
  //   browser_evaluate: () => { window.__ghWant = {"gender": "Female", "question_123": "No"} }
  // Keys are the input ids fields.js reports; values are exact option labels.
  // "candidate-location" is typed and the first suggestion taken.
  // Returns {id: label} for each set field, or {id: {miss, near, total}} when no
  // option matched exactly, so nothing is ever picked by a fuzzy guess.
  const want = await page.evaluate(() => window.__ghWant || {});
  // An id attribute selector, not a hash selector: Greenhouse demographic
  // fields have numeric ids (75902), invalid after a '#'. Waymo, 24 Sep 2026.
  const byId = (id) => page.locator(`[id="${id}"]`);
  const out = {};
  for (const [id, label] of Object.entries(want)) {
    const opts = page.locator(`[id^="react-select-${id}-option"]`);
    if (id === 'candidate-location') {
      await byId(id).fill('');
      await byId(id).pressSequentially(label, { delay: 40 });
      await opts.first().waitFor({ timeout: 5000 }).catch(() => {});
      if (await opts.count()) {
        await opts.first().click();
        // the option list is gone after the click, so read what was committed
        out[id] = await byId(id).locator('xpath=ancestor::div[contains(@class,"container")][1]')
          .locator('[class*="singleValue"]').first().innerText({ timeout: 1000 }).catch(() => ({ unverified: label }));
      } else out[id] = { miss: label, options: [] };
      continue;
    }
    await byId(id).click();
    await opts.first().waitFor({ timeout: 3000 }).catch(() => {});
    const texts = (await opts.allInnerTexts()).map(t => t.trim());
    const i = texts.indexOf(label);
    if (i < 0) {
      // a phone-country list is ~240 options; return near ones, not all of them
      const words = label.toLowerCase().split(/\W+/).filter(Boolean);
      const near = texts.filter(t => words.some(w => t.toLowerCase().includes(w))).slice(0, 15);
      out[id] = { miss: label, near, total: texts.length };
      await page.keyboard.press('Escape');
      continue;
    }
    await opts.nth(i).click();
    out[id] = label;
  }
  return out;
}
