async (page) => {
  // Template: jobs.py resolve writes .li_resolve.js with the id list filled in by the
  // LinkedIn job ids still on the queue. Returns [[id, employerUrl, flag]],
  // flag one of "", closed, easy, none, err. A guest page renders the
  // employer link as a[href*="safety/go"]; plain curl never sees it.
  // Click trackers (appcast is DataDome-walled to curl, doubleclick, grnh.se)
  // are followed here in the browser. LinkedIn answered 429 after ~45 pages
  // at full speed on 24 Sep 2026, so pages are paced and a 429 ends the call;
  // the ids not returned stay on the queue for the next run.
  const ids = __IDS__;
  const out = [];
  for (const id of ids) {
    try {
      const resp = await page.goto(`https://www.linkedin.com/jobs/view/${id}/`, { waitUntil: 'domcontentloaded', timeout: 20000 });
      if (resp && resp.status() === 429) break;
      await page.waitForFunction(() => document.querySelector('a[href*="safety/go"]') ||
        /accepting applications|easy apply/i.test(document.body.innerText), null, { timeout: 6000 }).catch(() => {});
      const row = await page.evaluate((id) => {
        const a = document.querySelector('a[href*="safety/go"]');
        const t = document.body.innerText;
        const flag = /no longer accepting|not currently accepting/i.test(t) ? 'closed'
          : a ? '' : /easy apply/i.test(t) ? 'easy' : 'none';
        return [id, a ? new URL(a.href).searchParams.get('url') : '', flag];
      }, id);
      if (/appcast|doubleclick|recruitics|grnh\.se|click\.|redirect|track/i.test(row[1])) {
        await page.goto(row[1], { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {});
        if (!/^chrome-error/.test(page.url())) row[1] = page.url();
      }
      out.push(row);
      await page.waitForTimeout(1200);
    } catch (e) { out.push([id, '', 'err']); }
  }
  return JSON.stringify(out);
}
