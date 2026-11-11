# Security

Tuxedo Finance runs on the computer or server of its owner. Security fixes
target the latest release.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/HenriqueMayer/TuxedoFinance/security/advisories/new).
If GitHub does not offer that form, contact the
[repository owner](https://github.com/HenriqueMayer) to arrange a private
report. Do not publish financial records, database files, keys or an exploit
against another installation in a public issue. A useful report has the
affected version, a minimal reproduction with fictional records, the expected
result and the observed impact.

## What the application does

- Sign-in uses the Django session cookie. Every operation that changes data
  checks a CSRF token.
- A user reads and changes only their own records. A record of another user
  answers as if it did not exist.
- Sign in and sign up are limited to 10 attempts per minute for each address
  (`TUXEDO_AUTH_THROTTLE`).
- The content security policy allows scripts from the installation only.
- The Docker port is published on `127.0.0.1` only.

## What the owner must do

- Keep `SECRET_KEY` private and stable. Never use a key that starts with
  `django-insecure`.
- Protect the data directory and its backups. Git ignore rules are not access
  control.
- Set `ALLOW_SIGNUPS=False` after creating the intended users.
- For access from another computer, put a TLS proxy in front, set
  `HTTPS=True` and set `ALLOWED_HOSTS` to the public name.

See [Operations](docs/operations.md) for settings, backup and restore.
