// Checks pw/next.js decides correctly without a browser: the page is a stub
// that serves scripted snapshots, so only the alert logic is under test.
import fs from 'node:fs';
import assert from 'node:assert';

const src = fs.readFileSync(new URL('./next.js', import.meta.url), 'utf8');
const next = new Function('return (' + src + ')')();

function stub(snapshots, { hasOverlay = true } = {}) {
  let i = 0;
  const locator = () => ({ count: async () => (hasOverlay ? 1 : 0), first: () => ({ click: async () => {} }) });
  return {
    waitForTimeout: async () => {},
    evaluate: async () => snapshots[Math.min(i++, snapshots.length - 1)],
    locator,
    getByRole: locator,
  };
}

const upload = 'Resume successfully uploaded';
const before = { step: 'Step 3 of 7', alerts: [upload], keys: 'a|b' };

// 1. the reported bug: a stale success alert must not fail an advance
let r = await next(stub([before, { step: 'Step 4 of 7', alerts: [upload], keys: 'c|d' }]));
assert.equal(r.ok, true, JSON.stringify(r));
assert.equal(r.notes, undefined, 'a pre-existing alert is not a note');

// 2. a genuine validation error still fails
r = await next(stub([before, { step: 'Step 3 of 7', alerts: [upload, 'The field County is required'], keys: 'a|b' }]));
assert.equal(r.ok, false);
assert.deepEqual(r.errors, ['The field County is required']);

// 3. a new, harmless alert rides along as a note rather than a failure
r = await next(stub([before, { step: 'Step 4 of 7', alerts: [upload, 'Draft saved'], keys: 'c|d' }]));
assert.equal(r.ok, true);
assert.deepEqual(r.notes, ['Draft saved']);

// 4. nothing changes at all
r = await next(stub([before]));
assert.equal(r.ok, false);
assert.match(r.reason, /did not change/);

// 5. no forward button on the page
r = await next(stub([before], { hasOverlay: false }));
assert.equal(r.ok, false);
assert.match(r.reason, /no forward button/);

// 6. a tenant with no click_filter overlay on the footer: the overlay click
// lands on nothing and only the footer button actually advances the page
{
  let advanced = false;
  const page = {
    waitForTimeout: async () => {},
    evaluate: async () => (advanced ? { step: 'Step 4 of 7', alerts: [upload], keys: 'c|d' } : before),
    locator: (sel = '') => ({
      count: async () => 1,
      first: () => ({ click: async () => { if (sel.includes('pageFooterNextButton')) advanced = true; } }),
    }),
    getByRole: () => ({ count: async () => 1, first: () => ({ click: async () => {} }) }),
  };
  r = await next(page);
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.equal(r.via, 'pageFooterNextButton', 'the footer fallback has to say it was used');
}

// 7. a keys-only change on a numbered step is a failed save, not an advance:
// Workday paints "Invalid LinkedIn URL" as a new field before it paints it as
// an alert, and the step counter staying put is what gives it away
r = await next(stub([before, { step: 'Step 3 of 7', alerts: [upload], keys: 'a|b|linkedinError' }]));
assert.equal(r.ok, false, JSON.stringify(r));
assert.match(r.reason, /did not change/);

// 8. a page with no step counter at all still advances on a keys change
{
  const noStep = { step: '', alerts: [], keys: 'a|b' };
  r = await next(stub([noStep, { step: '', alerts: [], keys: 'c|d' }]));
  assert.equal(r.ok, true, JSON.stringify(r));
}

console.log('ok');
