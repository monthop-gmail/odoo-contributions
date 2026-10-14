# SPH POC instructions

Maintainer: monthop-gmail
Reviewer: monthop-gmail

- Work on `sph/poc`; do not merge or open PRs into `main`.
- Scope: this folder and `.github/workflows/sph-poc.yml` only.
- MIT applies to original files here only. Do not copy Odoo core/OCA code.
- Odoo 19 Community only; synthetic data only; no production connections.
- B0-B3 is infrastructure and one install smoke test. G1-G4 are NOT RUN.
- No new credentials, secrets, permissions or non-harness deployment.
- Pin changes must update `version-pins.json` and runtime inventory, then pass
  static checks and the clean disposable harness test. Never skip a mismatch.
- Keep models/security placeholders empty until later scope is authorized.
