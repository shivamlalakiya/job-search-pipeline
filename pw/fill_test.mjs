// Checks pw/fill.js without a browser, against a stub page whose locators
// behave like Playwright's for the calls the helper makes.
import fs from 'node:fs';
import assert from 'node:assert';

const src = fs.readFileSync(new URL('./fill.js', import.meta.url), 'utf8');
const fill = new Function('return (' + src + ')')();

function stub(els, want) {
  const calls = [];
  const locator = (sel) => {
    const e = els[sel];
    const loc = {
      first: () => loc,
      count: async () => (e ? 1 : 0),
      evaluate: async (fn) => fn({
        tagName: e.tag.toUpperCase(), type: e.type || '',
        options: (e.options || []).map((label) => ({ label })),
      }),
      selectOption: async ({ label }) => { calls.push(['select', sel, label]); e.value = label; },
      setChecked: async (v) => { calls.push(['check', sel, v]); if (!e.stuck) e.checked = v; },
      isChecked: async () => !!e.checked,
      setInputFiles: async (p) => { calls.push(['file', sel, p]); },
      click: async () => {},
      fill: async (v) => { calls.push(['fill', sel, v]); e.value = v; },
      press: async () => { if (e.clearsOnBlur) e.value = ''; },
      inputValue: async () => e.value,
    };
    return loc;
  };
  return { calls, page: { evaluate: async () => want, locator } };
}

const els = {
  '#first': { tag: 'input', type: 'text' },
  '#bio': { tag: 'textarea' },
  '#state': { tag: 'select', options: ['Illinois', 'Indiana', 'Iowa'] },
  '#vet': { tag: 'select', options: ['I am not a protected veteran', 'I identify as one or more of the classifications'] },
  '#agree': { tag: 'input', type: 'checkbox' },
  '#cv': { tag: 'input', type: 'file' },
  '#zip': { tag: 'input', type: 'text', clearsOnBlur: true },
  '#pw': { tag: 'input', type: 'password' },
  '#stuck': { tag: 'input', type: 'checkbox', stuck: true },
};

// 1. every native kind is set, and read back
let s = stub(els, { '#first': 'Alex', '#bio': 'Hello', '#state': 'Illinois', '#agree': true, '#cv': '/tmp/r.pdf' });
let r = await fill(s.page);
assert.deepEqual(r, { set: ['#first', '#bio', '#state', '#agree', '#cv'], bad: {} });
assert.deepEqual(s.calls.find((c) => c[0] === 'select'), ['select', '#state', 'Illinois']);

// 2. a select is never picked by a near match: "not a veteran" is not "not a protected veteran"
s = stub(els, { '#vet': 'I am not a veteran' });
r = await fill(s.page);
assert.equal(r.set.length, 0);
assert.equal(r.bad['#vet'].miss, 'I am not a veteran');
assert.equal(r.bad['#vet'].total, 2);
assert.ok(!s.calls.some((c) => c[0] === 'select'), 'nothing selected on a miss');

// 3. a field that clears on blur is reported, not counted as set
s = stub(els, { '#zip': '63119' });
r = await fill(s.page);
assert.deepEqual(r.bad['#zip'], { want: '63119', got: '' });

// 4. passwords and secret placeholders are refused: --secrets only substitutes in browser_type
s = stub(els, { '#first': 'ALL_ATS_PASSWORD', '#pw': 'x' });
r = await fill(s.page);
assert.match(r.bad['#first'], /secret placeholder/);
assert.match(r.bad['#pw'], /password field/);
assert.ok(!s.calls.length, 'nothing typed');

// 5. a missing element and a checkbox that will not take are both reported
s = stub(els, { '#nope': 'x', '#stuck': true });
r = await fill(s.page);
assert.equal(r.bad['#nope'], 'not found');
assert.deepEqual(r.bad['#stuck'], { want: true, got: false });

console.log('fill ok');
