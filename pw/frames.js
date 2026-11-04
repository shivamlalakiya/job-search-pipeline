async (page) => {
  const out = [];
  for (const f of page.frames()) {
    const data = await f.evaluate(() => {
      const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 };
      const lab = (e) => {
        if (e.id) { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return l.innerText.trim().slice(0, 80) }
        return (e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.name || '').slice(0, 80)
      };
      const fields = [...document.querySelectorAll('input,select,textarea')].filter(vis).map((e) => ({
        tag: e.tagName.toLowerCase(), type: e.type, id: e.id, label: lab(e),
        value: e.type === 'password' ? (e.value ? '***' : '') : String(e.value || '').slice(0, 60),
        required: e.required || e.getAttribute('aria-required') === 'true',
        options: e.tagName === 'SELECT' ? [...e.options].map((o) => o.text).slice(0, 30) : undefined
      }));
      const buttons = [...document.querySelectorAll('button,a[role=button],input[type=submit],input[type=button]')].filter(vis)
        .map((e) => ({ id: e.id, text: (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 60) }))
        .filter((b) => b.text || b.id);
      return { title: document.title, fields, buttons, text: document.body.innerText.replace(/\n{2,}/g, '\n').slice(0, 1500) }
    }).catch((e) => ({ err: String(e).slice(0, 120) }));
    if (data.err) { out.push({ name: f.name(), url: f.url().slice(0, 100), err: data.err }); continue }
    if (!data.fields.length && !data.buttons.length) continue;
    out.push({ name: f.name(), url: f.url().slice(0, 100), ...data })
  }
  return JSON.stringify(out, null, 1)
}
