# SPH synthetic POC infrastructure (B0-B3)

Maintainer and reviewer: **monthop-gmail**. Branch: `sph/poc`.

The MIT [LICENSE](LICENSE) applies **only to this folder's original code and
documentation**, unlike the repository-level “All rights reserved” statement.
It does not relicense the collection, Odoo, PostgreSQL or third-party packages.
No Odoo core or OCA code is copied into this folder; the addon imports Odoo APIs.

Synthetic data only: no real parts, prices, centers, people, orders or external
connections. This is a disposable local/CI harness, not a production deployment.
Only a skeleton registry/install smoke test exists. Center security, reservations,
purchasing authority and Flow A+B are later work; **G1-G4 remain NOT RUN**.

## Run

Prerequisites: Linux/amd64 (or working Docker amd64 emulation), Python 3.10+,
Docker Engine and Docker Compose v2 supporting `up --wait`. No pip dependencies,
other repositories, secrets, registry login or environment file are required.

From this folder:

```sh
python3 scripts/check_pins.py
python3 scripts/test_pin_guard.py
python3 scripts/harness.py test   # clean DB, runtime pin check, install + smoke, cleanup
python3 scripts/harness.py up     # initialize and run the local disposable UI
python3 scripts/harness.py down   # remove this checkout's containers, DB and filestore
```

`up` exposes Odoo at http://127.0.0.1:18069 only. PostgreSQL has no host port.
The DB is a tmpfs, lost when its container stops; `down` also removes the
filestore volume. The compose project name is derived from this folder's absolute
path, so cleanup targets only this checkout's harness. Do not run tests against
a UI instance you want to retain: `test` deliberately resets this project's DB.

PostgreSQL is attached only to the internal backend network and uses trust auth
there (no password or credential is provisioned). Odoo also has a frontend bridge
for its loopback-only published port; that bridge is not an outbound firewall.
Odoo's stock synthetic initialization is not a credential-management system;
do not expose the service or attach real data. No mail/provider integration is
configured, cron is disabled, and database listing is disabled. No enterprise
addon is installed. Core dependency tables may exist, but no business seed,
invoice, payment or live inventory action is implemented.

## Pins and drift checks

`compose.yaml` is JSON syntax, which is valid YAML, to allow stdlib-only static
checking. `version-pins.json` records the exact Linux/amd64 manifest digests,
Odoo dated Debian build, upstream Docker build reference and package checksum,
PostgreSQL full version, Python version and lock-file hashes. The Docker build
reference identifies image recipe provenance, not a claim about Odoo core's Git
SHA. Digest selection was verified from Docker Hub's registry manifests.

`requirements.lock` declares no extra addon packages. `runtime-python.lock` is
the sorted complete distribution inventory observed inside the immutable Odoo
image, including distro-provided packages. It is a verification lock, **not** a
pip installation recipe. The harness never resolves/installs packages at startup.

The static check rejects unpinned images, mismatched image/digest/platform,
baseline/module/license/dependency drift and changed lock-file bytes. Runtime
verification rejects a changed Odoo package/build, Python version, distribution
inventory or PostgreSQL version. It fails rather than refreshing pins. The
negative controls alter an image and lock in a temporary copy to verify rejection.

For an explicitly reviewed future pin update: resolve the new architecture-specific
digest, run `python3 scripts/harness.py inventory`, inspect `evidence/runtime.json`,
update the recorded versions/inventory and hashes together, and rerun the clean
test. No automatic pin refresh is performed; never weaken the checks for a green run.

## CI and evidence

`.github/workflows/sph-poc.yml` runs on pushes to `sph/poc` and PRs **into
`sph/poc`**, filtered to this folder and that workflow file. It has only
`contents: read`, does not persist checkout credentials and uses SHA-pinned
actions. It runs static pin checks, negative controls and the same clean
module-install/smoke harness. Other collection folders do not trigger this CI.
There is no PR to `main`, deployment job or secret dependency.

After `harness.py up`, CI runs `python3 scripts/live_suite.py` outside Odoo's
test process, before the unconditional `down`. It writes `evidence/live-suite.xml`:
`g1_http` checks only the loopback login's HTTP 200; `g2_race` is explicitly
**SKIP — UNRUNNABLE: not implemented**. A readiness failure exits nonzero and
still writes JUnit. Green infrastructure CI with this skip is not G1-G3 acceptance.
Later real HTTP isolation, deny-row assertions and reservation races belong in
this out-of-process suite, not TransactionCase/HttpCase. See the
[B3b verification record](docs/b3b-verification.md).

Ignored `evidence/` contains package-version metadata, PostgreSQL version and
synthetic Odoo logs. CI preserves it for seven days even on failure. Do not add
tokens, passwords, personal data or private document content to evidence or hub
reports. A green B0-B3 run is infrastructure evidence only, not G1-G4 acceptance.
