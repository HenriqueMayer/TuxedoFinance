# Security

Tuxedo Finance is a local-first application. Security fixes target the latest
stable release; use its explicit versioned image and review the release notes.
Code under `Unreleased` is not delivered to an installation until its owner
selects and installs a new release.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/HenriqueMayer/TuxedoFinance/security/advisories/new)
when available. If GitHub does not offer that form, contact the
[repository owner](https://github.com/HenriqueMayer) to arrange a private report.
Do not publish financial records, database files, signing keys, credentials or
an exploit against another installation in a public issue. A useful report
includes the affected version, a minimal reproduction using synthetic records,
the expected result and the observed impact.

## Supported access and data protection

- Default Docker access is bound to loopback; use Docker Engine 28+ or current
  Docker Desktop. Older Engines can expose localhost-published ports on the LAN.
- SQLite and the signing key belong to the installation owner. Git ignore rules
  are not access control. Protect the data directory and backup copies; native
  setup creates the key once and new native runtime files are owner-only.
- Keep `SECRET_KEY`, the data volume and Compose project identity across updates.
  Close registration with `ALLOW_SIGNUPS=False` after creating intended users.
- Remote access requires explicit access controls and a trusted TLS proxy.
  Authentication is native Django; application login throttling and public
  hosting infrastructure are not supplied by the local package.
- Dependencies are audited in CI. A clean audit only means no known advisory
  was found in that run; it does not certify an installation or its host.

## CSV exports

Default CSV is a faithful interchange format: text is unchanged, including
formula-looking values. Do not open untrusted raw exports as spreadsheets.
The explicit **Spreadsheet CSV** variant prefixes text beginning with formula
operators (including after whitespace) or control characters with an apostrophe.
Numeric amount cells and ISO dates remain unchanged. This reduces formula
interpretation in common spreadsheet software; behavior differs between
applications and later edits, so it is not a universal safety guarantee.
Imports never remove these prefixes. Use raw CSV for faithful category
export/import round-trips and preserve the original export.

See [Docker operations](docs/docker.md) and [native operations](docs/operations.md)
for backup, upgrade and restore procedures.
