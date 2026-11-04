# Security

Please report a vulnerability privately through GitHub: the repository's **Security** tab, then **Report a vulnerability**. Do not open a public issue for it.

This tool handles ATS passwords, a Gmail app password and personal data. If you find a way for any of them to leak (into a prompt, a log, a tool argument, a committed file or an email), that is in scope.

Never commit anything under `profiles/` other than `profiles/Example/`. The `.gitignore` is an allowlist for that reason.
