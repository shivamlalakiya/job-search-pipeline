async (page) => {
  // Waits up to 55s for a human to solve the captcha on this page. Returns
  // {state, url}: "solved" (a response token is filled or the challenge is
  // gone), "waiting" (still unsolved; call again), "none" (no captcha here).
  // Added 24 Sep 2026: the user asked to be pinged at a captcha and to solve
  // it if at the desk, instead of the row being skipped. The apply agent
  // pings, then calls this up to 5 times (about 5 minutes) before moving on.
  const probe = () => page.evaluate(() => {
    const frames = Array.from(document.querySelectorAll('iframe'))
      .filter((f) => /hcaptcha|recaptcha|turnstile|challenges\.cloudflare/i.test(f.src || '')
        && (f.offsetParent || f.getClientRects().length));
    const tokens = Array.from(document.querySelectorAll(
      'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"], input[name="cf-turnstile-response"]'));
    if (tokens.some((t) => t.value)) return 'solved';
    if (!frames.length) return tokens.length ? 'solved' : 'none';
    return 'waiting';
  });
  const first = await probe();
  if (first !== 'waiting') return { state: first, url: page.url() };
  const start = page.url();
  for (let i = 0; i < 55; i++) {
    await page.waitForTimeout(1000);
    if (page.url() !== start) return { state: 'solved', url: page.url() };
    if ((await probe()) !== 'waiting') return { state: 'solved', url: page.url() };
  }
  return { state: 'waiting', url: page.url() };
}
