// Pre-Save check. Answers "will this page reject me" in one call, instead of
// pressing Save, reading the error, fixing one field, and pressing Save again.
// Run with browser_run_code_unsafe's `filename`.
//
// Written after the ETSU form on 10 Sep 2026, where two of the run's errors
// were "The field County is required" and "The field How Did You Hear About
// Us? is required", both found only after a failed Save, and where Oracle's
// cx-select comboboxes silently clear on blur when the dropdown option was
// never clicked, so a field can look filled and be empty.
async (page) => {
  await page.waitForTimeout(300);
  return page.evaluate(() => {
    const vis = (e) => !!(e.offsetParent || e.getClientRects().length);
    const label = (e) => (
      e.labels?.[0]?.innerText
      || e.getAttribute('aria-label')
      || e.closest('[data-automation-id], .cx-form-field')?.querySelector('label')?.innerText
      || e.name || e.id || ''
    ).replace(/[\s*]+/g, ' ').trim();

    const els = Array.from(document.querySelectorAll(
      'input, select, textarea, [role=combobox], cx-select input'
    )).filter(vis).filter((e) => !['hidden', 'submit', 'button'].includes(e.type));

    const required = (e) => e.required
      || e.getAttribute('aria-required') === 'true'
      || /\*/.test(e.labels?.[0]?.innerText || '')
      || /\*/.test(e.closest('.cx-form-field')?.querySelector('label')?.innerText || '');

    const blank = (e) => (e.type === 'checkbox' || e.type === 'radio')
      ? !e.checked
      : !String(e.value || '').trim();

    return {
      empty_required: els.filter((e) => required(e) && blank(e)).map(label),
      // Everything filled, so a silent clear on blur is visible without a
      // second call. Short values only: this is a check, not a page dump.
      values: Object.fromEntries(els.filter((e) => !blank(e))
        .map((e) => [label(e) || e.id, String(e.value ?? e.checked).slice(0, 40)])),
      alerts: Array.from(document.querySelectorAll(
        '[role=alert], [data-automation-id*=errorMessage], .cx-error, .error-message'
      )).map((e) => e.innerText.replace(/\s+/g, ' ').trim()).filter(Boolean),
    };
  });
}
