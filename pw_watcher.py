import asyncio
import re
import secrets
import string
import subprocess
from urllib.parse import urlparse
from playwright.async_api import async_playwright

def get_cdp_port() -> str:
    """Auto-detects the CDP remote debugging port from the running Chrome process."""
    res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    match = re.search(r"--remote-debugging-port=(\d+)", res.stdout)
    return match.group(1) if match else "9222"

def generate_password(length=16) -> str:
    specials = "!@#$%^&*"
    req = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(specials),
    ]
    pool = string.ascii_letters + string.digits + specials
    chars = req + [secrets.choice(pool) for _ in range(length - len(req))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)

def get_or_create_keychain_pw(host: str) -> str:
    """Uses the exact 'job-ats <host>' Keychain format from commit 29818bd."""
    service = f"job-ats {host}"
    find_cmd = ["security", "find-generic-password", "-s", service, "-w"]
    res = subprocess.run(find_cmd, capture_output=True, text=True)
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()

    pw = generate_password()
    add_cmd = [
        "security", "add-generic-password",
        "-U", "-s", service, "-a", "job-ats", "-w", pw
    ]
    subprocess.run(add_cmd, check=True)
    print(f"[+] Created & saved new Keychain password for: {service}")
    return pw

async def watch_passwords():
    port = get_cdp_port()
    cdp_url = f"http://127.0.0.1:{port}"
    print(f"[*] Connecting to jobs.py Chrome on {cdp_url}...")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        print("[*] Watching all tabs for sign-in / sign-up password fields...")
        gmail_opened = set()

        while True:
            try:
                for context in browser.contexts:
                    for page in context.pages:
                        if not page.url.startswith("http"):
                            continue
                        pw_fields = page.locator('input[type="password"]:visible')
                        count = await pw_fields.count()
                        if count == 0:
                            continue

                        # Check if the first visible password field is still empty
                        first_val = await pw_fields.nth(0).input_value()
                        if first_val:
                            continue

                        host = urlparse(page.url).hostname
                        # Never fill a generated password into Google's own sign-in (Gmail tab).
                        if not host or host == "google.com" or host.endswith(".google.com"):
                            continue

                        pw = get_or_create_keychain_pw(host)
                        for i in range(count):
                            field = pw_fields.nth(i)
                            await field.fill(pw)
                            await field.dispatch_event("input")
                            await field.dispatch_event("change")
                            await field.dispatch_event("blur")
                        print(f"[+] Auto-filled {count} password field(s) on {host}")
                        # Workday emails a verification link after Create Account. Open
                        # Gmail searched for it, once per host; the user clicks the link.
                        if "myworkday" in host and host not in gmail_opened:
                            gmail_opened.add(host)
                            mail = await context.new_page()
                            await mail.goto("https://mail.google.com/mail/u/0/#search/workday+verify")
                            print(f"[+] Opened Gmail search for the {host} verification email")
            except Exception:
                pass
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(watch_passwords())
