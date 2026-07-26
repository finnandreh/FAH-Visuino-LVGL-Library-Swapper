# Security Policy

## Supported version

Security fixes currently target the latest source on `main`. The retained
version 1.0.1 portable package predates the integrated Project Vault feature.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose credentials,
customer projects, local filesystem data, or unsafe library-switch behavior.

Use GitHub's private vulnerability reporting feature when it is available for
this repository. Include:

- the affected commit or release;
- a minimal reproduction;
- the exact Windows, Python, Visuino, Arduino, and board context when relevant;
- the expected and observed safety boundary;
- whether data was written, linked, moved, or exposed.

Do not include real customer data, access tokens, passwords, or private project
archives. Acknowledgement and remediation timing depend on severity and the
ability to reproduce the issue safely.

## Security boundaries

- Profile and Project Vault writes require explicit preview and confirmation.
- Project targets are immutable and must never be deleted through junction
  removal.
- Active configuration changes require backup, verification, audit, and
  rollback.
- Imported source is inspected and copied; it is not executed by the desktop
  application.
- Environment files, runtime state, caches, logs, and credentials are excluded
  from version control.
