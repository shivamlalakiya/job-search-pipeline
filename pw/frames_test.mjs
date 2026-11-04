// Checks pw/frames.js without a browser. The page is a stub that serves one
// scripted result per frame, so what is under test is the part the caller
// depends on: which frames survive into the output, and what happens to a frame
// that throws. Written 11 Sep 2026, after the helper was added mid-run for
// PeopleSoft, whose sign-in and Add Attachment dialogs live inside iframes and
// are invisible to pw/fields.js.
import fs from 'node:fs';
import assert from 'node:assert';

const src = fs.readFileSync(new URL('./frames.js', import.meta.url), 'utf8');
const frames = new Function('return (' + src + ')')();

// Each stub frame answers evaluate() with whatever it was handed, or throws.
function frame(name, url, result) {
  return {
    name: () => name,
    url: () => url,
    evaluate: async () => {
      if (result instanceof Error) throw result;
      return result;
    },
  };
}
const page = (...fs) => ({ frames: () => fs });
const filled = { title: 'Sign In', fields: [{ id: 'user', label: 'Username' }], buttons: [], text: 'Sign In' };
const empty = { title: 'spacer', fields: [], buttons: [], text: '' };

// 1. a frame with fields is reported, with its name and url alongside
let out = JSON.parse(await frames(page(frame('ptModFrame_0', 'https://x/signin', filled))));
assert.equal(out.length, 1, JSON.stringify(out));
assert.equal(out[0].name, 'ptModFrame_0');
assert.equal(out[0].url, 'https://x/signin');
assert.equal(out[0].fields[0].id, 'user');

// 2. a frame with neither fields nor buttons is dropped, so the caller is not
// handed the tracking pixels and spacer iframes every PeopleSoft page carries
out = JSON.parse(await frames(page(frame('spacer', 'https://x/blank', empty))));
assert.deepEqual(out, []);

// 3. the interesting frame is usually not the first one, and the main frame is
// usually the empty one. Both must be handled in the same pass.
out = JSON.parse(await frames(page(
  frame('', 'https://x/outer', empty),
  frame('ptModFrame_1', 'https://x/modal', filled),
)));
assert.equal(out.length, 1);
assert.equal(out[0].name, 'ptModFrame_1');

// 4. a cross-origin frame throws on evaluate. It must be reported as an error
// rather than taking the whole read down, because one unreadable frame on a
// page is normal and the readable ones are the point.
out = JSON.parse(await frames(page(
  frame('hostile', 'https://other/x', new Error('SecurityError: cross-origin')),
  frame('ptModFrame_2', 'https://x/modal', filled),
)));
assert.equal(out.length, 2, JSON.stringify(out));
assert.match(out[0].err, /cross-origin/);
assert.equal(out[0].fields, undefined, 'an errored frame reports no fields');
assert.equal(out[1].fields[0].id, 'user');

console.log('ok');
