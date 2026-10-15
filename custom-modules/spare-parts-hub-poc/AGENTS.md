# SPH POC instructions

Maintainer: monthop-gmail
Reviewer: monthop-gmail

- Work on `sph/poc`; do not merge or open PRs into `main`.
- Scope: this folder and `.github/workflows/sph-poc.yml` only.
- MIT applies to original files here only. Do not copy Odoo core/OCA code.
- Odoo 19 Community only; synthetic data only; no production connections.
- B0-B3 infrastructure and B4a models/seed and B4b G1 isolation/B4c reservations/B4d authority are authorized. Gate acceptance requires live CI evidence.
- No new credentials, secrets, permissions or non-harness deployment.
- Pin changes must update `version-pins.json` and runtime inventory, then pass
  static checks and the clean disposable harness test. Never skip a mismatch.
- G3 acceptance requires the real live authority suite; G4 remains pending.
