# SPH POC instructions

Maintainer: monthop-gmail
Reviewer: monthop-gmail

- Work on `sph/poc`; do not merge or open PRs into `main`.
- Scope: this folder and `.github/workflows/sph-poc.yml` only.
- MIT applies to original files here only. Do not copy Odoo core/OCA code.
- Odoo 19 Community only; synthetic data only; no production connections.
- B0-B3 infrastructure and B4a models/synthetic seed are authorized. G1-G4 are NOT RUN.
- No new credentials, secrets, permissions or non-harness deployment.
- Pin changes must update `version-pins.json` and runtime inventory, then pass
  static checks and the clean disposable harness test. Never skip a mismatch.
- Center isolation, band pages, reservations and purchasing guards belong to
  separately sequenced B4b-B4d tasks; do not infer their acceptance from seed tests.
