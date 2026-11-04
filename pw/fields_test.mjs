// Checks pw/fields.js without a browser. The DOM is a hand-built stub, so what
// is under test is the part that has to be right for the caller to act without
// a browser_snapshot: the selector it hands back for each field and button.
import fs from 'node:fs';
import assert from 'node:assert';

const src = fs.readFileSync(new URL('./fields.js', import.meta.url), 'utf8');
const fields = new Function('return (' + src + ')')();

function el(tag, attrs = {}, extra = {}) {
  const { innerText = '', ...rest } = attrs;
  return {
    tagName: tag.toUpperCase(),
    innerText,
    getClientRects: () => [1],
    getAttribute: (a) => (a in rest ? String(rest[a]) : null),
    closest: () => null,
    id: rest.id || '',
    type: rest.type || '',
    value: rest.value || '',
    required: !!rest.required,
    ...extra,
  };
}

function stub(nodes, bodyText = 'Step 2 of 5') {
  const pick = (q) => {
    if (q.startsWith('input,')) return nodes.filter((n) => ['INPUT', 'SELECT', 'TEXTAREA'].includes(n.tagName));
    if (q.startsWith('button,')) return nodes.filter((n) => n.tagName === 'BUTTON');
    if (q.startsWith('a[href]')) return nodes.filter((n) => n.tagName === 'A');
    return [];
  };
  const document = {
    title: 'Apply',
    body: { innerText: bodyText },
    querySelectorAll: pick,
  };
  return {
    waitForTimeout: async () => {},
    evaluate: async (cb) => {
      globalThis.document = document;
      try { return cb(); } finally { delete globalThis.document; }
    },
  };
}

// 1. an id wins, and a plain id is not mangled
let r = await fields(stub([el('input', { id: 'firstName', type: 'text', value: 'Alex' })]));
assert.equal(r.fields[0].sel, '#firstName', JSON.stringify(r.fields[0]));
assert.equal(r.fields[0].value, 'Alex');
assert.equal(r.step, 'Step 2 of 5');

// 2. a Workday id keeps its hyphens, which are legal in a CSS id, and escapes
//    the characters that are not
r = await fields(stub([el('input', { id: 'input-5--dash.dot', type: 'text' })]));
assert.equal(r.fields[0].sel, '#input-5--dash\\.dot', r.fields[0].sel);

// 3. no id falls back to name, which is what most non-Workday ATSs give you
r = await fields(stub([el('input', { name: 'applicant_email', type: 'email' })]));
assert.equal(r.fields[0].sel, 'input[name="applicant_email"]');
assert.equal(r.fields[0].id, 'applicant_email', 'id falls back too, so the row is still identifiable');

// 4. neither, so data-automation-id, then aria-label
r = await fields(stub([el('input', { 'data-automation-id': 'legalNameSection_firstName' })]));
assert.equal(r.fields[0].sel, '[data-automation-id="legalNameSection_firstName"]');
r = await fields(stub([el('input', { 'aria-label': 'Postal Code', 'aria-required': 'true' })]));
assert.equal(r.fields[0].sel, 'input[aria-label="Postal Code"]');
assert.equal(r.fields[0].required, true, 'aria-required counts as required');

// 5. nothing to key on at all returns an empty selector rather than a wrong one
r = await fields(stub([el('input', { type: 'text' })]));
assert.equal(r.fields[0].sel, '');

// 6. buttons and links come back with a selector to click. Deduping was on
// visible text alone until 10 Sep 2026, when three separate required dropdowns
// on tcsedsystem.wd1 all reading "Select One" collapsed into one entry and two
// required fields became invisible to the caller. Two controls that differ only
// by selector are now both reported: a few extra tokens beats a hidden required
// field. The duplicate that dedupe existed for, Workday's click_filter overlay
// sharing its text with the button underneath, is dropped by name instead.
r = await fields(stub([
  el('button', { innerText: 'Save and Continue', id: 'next' }),
  el('button', { innerText: 'Save and Continue', id: 'next2' }),
  el('a', { innerText: 'Apply Now', 'aria-label': 'Apply Now' }),
]));
assert.deepEqual(r.buttons, [
  { text: 'Save and Continue', sel: '#next' },
  { text: 'Save and Continue', sel: '#next2' },
]);
assert.deepEqual(r.links, [{ text: 'Apply Now', sel: 'a[aria-label="Apply Now"]' }]);

// 6b. the overlay is dropped, so the button underneath is what comes back
r = await fields(stub([
  el('div', { innerText: 'Save and Continue', 'data-automation-id': 'click_filter' }),
  el('button', { innerText: 'Save and Continue', id: 'next' }),
]));
assert.deepEqual(r.buttons, [{ text: 'Save and Continue', sel: '#next' }]);

// 6c. an identical repeated element is still only reported once
r = await fields(stub([
  el('button', { innerText: 'Select One', 'aria-label': 'Select One' }),
  el('button', { innerText: 'Select One', 'aria-label': 'Select One' }),
]));
assert.equal(r.buttons.length, 1, JSON.stringify(r.buttons));

// 7. long labels are capped, because a consent paragraph is not worth the tokens
r = await fields(stub([el('input', { 'aria-label': 'x'.repeat(400) })]));
assert.equal(r.fields[0].label.length, 120);

// A committed Workday prompt value lives in a selectedItem pill, not in the
// input, so an empty-looking required field that has a pill beside it must
// report the pill's text rather than ''
{
  const pill = { innerText: 'Massachusetts' };
  const input = el('input', { id: 'state', 'aria-required': 'true' }, {
    parentElement: { querySelectorAll: () => [pill], parentElement: null },
  });
  const out = await fields(stub([input]));
  const f = out.fields.find((x) => x.id === 'state');
  assert.equal(f.value, 'Massachusetts', JSON.stringify(f));
}

// 8. a progress rail that lists every step must not pin the step counter at the
// first one it finds. "current step" is the live step, and reading the rail's
// first entry instead made next.js click forward twice and skip a page
r = await fields(stub([], 'step 1 of 7 step 2 of 7 current step 4 of 7 step 5 of 7'));
assert.equal(r.step, 'current step 4 of 7', r.step);

// 9. a tenant with no "current" wording still reports its step, any case
r = await fields(stub([], 'Step 3 of 7'));
assert.equal(r.step, 'Step 3 of 7', r.step);
r = await fields(stub([], 'current step 4 of 8'));
assert.equal(r.step, 'current step 4 of 8', r.step);

// 10. an id that starts with a digit is not a legal CSS id selector, so it has
// to come back as an attribute selector or it throws at page.check
r = await fields(stub([el('input', { id: '6f2ca4b1', type: 'checkbox' })]));
assert.equal(r.fields[0].sel, '[id="6f2ca4b1"]', r.fields[0].sel);

// 11. an ordinary id still comes back as a plain id selector
r = await fields(stub([el('input', { id: 'firstName', type: 'text' })]));
assert.equal(r.fields[0].sel, '#firstName', r.fields[0].sel);

// 12. a Lever custom question: no <label for>, the question sits in the
//     widest ancestor holding only this control
const ta = el('textarea', { name: 'cards[x][field0]' });
const li = { innerText: 'Years of SQL?*', querySelectorAll: () => [ta], parentElement: null };
li.parentElement = { innerText: 'Years of SQL?* Other q', querySelectorAll: () => [ta, {}], parentElement: null };
ta.parentElement = { innerText: '', querySelectorAll: () => [ta], parentElement: li };
r = await fields(stub([ta]));
assert.equal(r.fields[0].label, 'Years of SQL?*', r.fields[0].label);

console.log('ok');
