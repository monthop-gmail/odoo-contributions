# B3b live-harness infrastructure verification

Maintainer/reviewer: monthop-gmail. Synthetic-only infrastructure; no gate PASS.

Verified workflow commit: `f8fbf1b5d517af67bf69d4a26a9c6fdb2488bb04`
(runner introduced by `5ce994dd1f770f5b92e7bfb34c17e53cfb34289b`).

- [CI run 38540916230](https://github.com/monthop-gmail/odoo-contributions/actions/runs/38540916230): success.
- The run executes static pins/negative controls, Odoo install/smoke, `up`,
  **Live-harness suite (G1 HTTP / G2 race)**, then unconditional `down` and upload.
- Downloaded JUnit `live-suite.xml`: 2 stages, 0 failures, 0 errors, 1 skipped.
  `g1_http` = readiness PASS only; `g2_race` = SKIP,
  `UNRUNNABLE: not implemented`. G1-G3 acceptance remains NOT RUN.
- [Evidence artifact 11882541724](https://github.com/monthop-gmail/odoo-contributions/actions/runs/38540916230/artifacts/11882541724)
  archive SHA-256: `65897879420e5bfd6cf7324584a936dc4909c70e3adfd0bd3703cadccc8469ad`.
- JUnit SHA-256: `d90a34a188f297fb78a7f4c5ca4d87659152eac89316667f67e9556d661bd3c5`.

Artifact retention is seven days; this records the observed run, not a promise
that its download persists forever. Reproduce on a Docker-capable machine:

```sh
python3 scripts/test_live_suite.py
python3 scripts/harness.py up
python3 scripts/live_suite.py
python3 scripts/harness.py down
```

Always tear down even if the live command fails (CI uses `if: always()`). The
runner unit tests use mocks to check failure/JUnit/skip behavior and do not count
as live gate tests. Actual races and deny-row assertions must later run here,
against the committed disposable database, outside TransactionCase/HttpCase.

No merge, PR to main, deployment outside the harness, credentials or permissions
were added. Runtime pins are unchanged from the B0-B3a base `368ad81`.
