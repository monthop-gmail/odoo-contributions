# SPH synthetic POC infrastructure (B0-B3)

Maintainer and reviewer: **monthop-gmail**. Branch: `sph/poc`.

The MIT [LICENSE](LICENSE) applies **only to this folder's original code and
documentation**, unlike the repository-level “All rights reserved” statement.
It does not relicense the collection, Odoo, PostgreSQL or third-party packages.
No Odoo core or OCA code is copied into this folder; the addon imports Odoo APIs.

Synthetic data only: no real parts, prices, centers, people, orders or external
connections. This is a disposable local/CI harness, not a production deployment.
The registry/install smoke test and B4a model/fixture tests exist. Center security,
reservations, purchasing authority and Flow A+B are later work;
**G1-G4 remain NOT RUN**.

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
After local `up`, always run `python3 scripts/harness.py down` yourself, even
if a later command fails; only CI guarantees teardown with `if: always()`.

PostgreSQL is attached only to the internal backend network and uses trust auth
there (no password or credential is provisioned). Odoo also has a frontend bridge
for its loopback-only published port; that bridge is not an outbound firewall.
The `up` database includes Odoo's default admin account: loopback and synthetic
data only. Never expose that port or attach real data. The `odoo` container on
the non-internal `ui` network has outbound egress.
Odoo's stock synthetic initialization is not a credential-management system;
do not expose the service or attach real data. No mail/provider integration is
configured, cron is disabled, and database listing is disabled. No enterprise
addon is installed. The B4a seed below creates synthetic records and starting
quants only; no invoice, payment or live inventory action is implemented.

## B4a synthetic fixtures

All seed names, identifiers, numbers, tags and quantities are **SYNTHETIC
ASSUMPTION / FIXTURE**, not business policies or real commercial data. The
initializer refuses databases other than `sph_poc` and refuses multiple companies.
It uses stable `sph_core.fixture_*` XML IDs, is covered by a reseed-idempotency
test, and refuses reseeding stock that already has reservations.

- One renamed FIXTURE company; existing central warehouse plus one owned-center
  warehouse. This is the provisional D4 model, not a legal-ownership assertion.
- One owned center, two independent centers and two additional independent
  centers under the same commercial partner. Center, company, warehouse, partner
  and explicit user memberships remain separate records/relations.
- Thirty untracked inventory parts with FIXTURE OEM/alternate identifiers and
  illustrative fitment tags. Template and variant display-name searches include
  OEM and alternate numbers. Alternate identifiers are a searchable text field,
  not a validated external catalog or substitution engine.
- Two FIXTURE suppliers. Central stock cycles through 8, 3, 0 and 1 units;
  `fixture_part_04` is a last-unit case. These provide In stock/Low/Out inputs,
  not an implemented portal band page or reservation mechanism.
- One FIXTURE user per mentor role (`sph_hub_operator`, `sph_warehouse_picker`,
  `sph_purchasing_approver`, `sph_center_requester`, `sph_center_receiver`,
  `sph_bot`). The two center users are portal users with explicit center links.
  No passwords or API keys are seeded and no invitation/reset mail is requested.
- Role groups are fixture memberships only. The purchasing approver does not yet
  receive purchase-manager authority; the bot has neither Settings nor purchase
  manager rights. Custom center/tag ACLs are administrator-only until B4b.
- Purchase settings are `two_step` with amount `0`, asserted in the seed tests.
  This configuration alone does not implement maker/checker or the G3 guards.

New model/seed tests are listed in `expected-tests.json`; the strict harness must
observe every listed test. Isolation HTTP checks, race and deny-row assertions
remain in the live-suite workstream, not these TransactionCase fixture tests.

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

`expected-tests.json` is the binding list of Odoo tests that must execute. Add
new tests there as they land. The harness parses every summary and rejects any
nonzero failure/error count, any ERROR/FAIL line, missing summaries or missing
listed tests. Runner controls include the former false-pass case `10 failed`.

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

## B4b isolation verification

Global SPH rules intersect native portal/group rules on orders, lines, pricelists,
items and pickings. Scoped users cannot read raw quants/moves or product stock/cost
aggregates, including with deliberately broader native groups. Membership changes
invalidate rule caches. Native portal export remains denied.

The band endpoint `/sph/band/<product-id>` authorizes the current user before a
fixed-location elevated read. JSON contains only `band`; HTML only the band span.
Client center/partner/pricelist/location selectors do not grant authority. Protected
SPH sale documents and linked binary downloads require normal read authorization
even when a share token is supplied.

Eight `TestCenterIsolation` methods are bound in `expected-tests.json`. The live
suite creates same-commercial-parent fixtures and ephemeral sessions inside the
disposable harness, without passwords/API keys. Session/share tokens remain in
memory-only IPC and the disposable filestore; they are never evidence outputs.
It checks every role's band projection, bidirectional ORM-over-HTTP denials, native
portal URLs/reports, attachment tokens, anonymous access and next-request revocation.
Sanitized G1 access matrix, rule inventory and JUnit files go into `evidence/`.
G1 acceptance requires the real live matrix to pass on the exact commit. G2 race
remains explicitly UNRUNNABLE/SKIP; G2-G4 have not passed.

## B4c reservation contract (synthetic fixture scope)

The human hub operator or picker invokes one `sale.order.sph_reserve(request_key,
allow_partial=False)` RPC. Bot membership always denies this method, even with
additional native groups. The server checks read authority and uses the order's
center and the fixed fixture central warehouse. Products are untracked fixtures;
no substitution or alternate location is selected. Central outgoing operations
use manual reservation in the seed.

The method locks the order for request replay, takes transaction-held product
advisory locks (including absent quant rows), then locks every matching quant row
in ID order before availability checks and native move assignment. Native quant
updates participate in the same advisory/row lock protocol. No reserve method
commits; Odoo's HTTP transaction owns atomic commit/whole-request retries. FCFS
means serialized confirmation at the stock lock; simultaneous arrivals have no
invented center priority.

All-or-nothing is the default. Explicit partial allocation retains outstanding
demand, records a backorder amount and uses native delivery backorders. Reservations
expire after 48 hours (FIXTURE policy), with a directly callable private cron
method because harness cron is off. Expired requests cannot replay into a fresh
reservation. Native quant constraints reject negative/over-reserved fixture stock;
SPH delivery validation rejects quantities above the recorded reservation limit.
Unavailable stock errors expose no quantities.

The bound TransactionCase tests cover human/bot scope, readback, rollback, replay,
reserve beyond free stock, over-delivery, partial delivery/backorder, frozen-time
expiry and native negative-quant refusal. They never race or commit.

`g2_race` runs a standalone Odoo-shell script against the running committed DB,
using two independent HTTP clients, a third PostgreSQL gate/observer, and alternating
launch order. The last round also competes with native `action_assign`. Default
`SPH_RACE_ROUNDS=4` is a synthetic test parameter, not a business SLA. PostgreSQL
lock waiters plus server `SPH_LOCK_WAIT` lines are required; missing contention is
UNRUNNABLE/SKIP with a nonzero job result. Fresh committed observations reconcile
quants, winning moves/ledger, loser rollback and replay. `manifest.json` records
round count, actual transaction isolation, commit and pinned runtime; G2 request
statistics and lock witness logs stay in the synthetic evidence bundle.
G2 acceptance requires the real race on the exact commit. G3 and G4 remain pending.

## B4d human authority and audit

Purchase approval requires the dedicated non-bot approver, a different maker,
`two_step`/amount zero, and that approver's review digest matching the current
synthetic PO. Client actor/force/context values do not grant authority. Bot
`button_approve` is a silent refusal with unchanged state; confirm, direct purchase
state writes and RFQ-send paths deny. The bot can prepare/read/edit its own draft
through bounded methods, without new native ACL/group grants. Protected identity
fields cannot be forged by RPC. Harness superuser initialization stays trusted.

SO/PO price changes, scrap validation, inventory apply and direct quant writes
each have distinct bot-deny/approver-allow tests. Native stock operations use a
private Python ContextVar capability, never a client context flag, so G2 human
reservation/assignment remains possible without opening direct bot writes.

`sph.authority.audit` stores `res_model`, `res_id` and actor as plain values;
resource identifiers have no foreign keys. Denials commit via an independent
cursor so a failed HTTP request cannot roll them back. The server's test-enable
configuration suppresses that independent write only in the in-process test
harness; client context cannot change it. Unit tests use their result/log as deny
evidence. ONLY the committed out-of-process G3 suite asserts deny rows. Allow
rows share the action transaction, with a rollback test. Audit read access is
admin-only; no audit create/write permission is granted to bot/approver roles.

The live suite runs G1, G2, then G3; G3 emits sanitized
`G3-authority-results.json` and `G3-assertions.xml`. No session/share tokens enter
these outputs. A green exact-commit live stage is required for G3 evidence.
This does not finish Flow A+B integration or reviewer/owner G4 sign-off.

### G3 / review #53 F3: reservation is not Sales approval

`sph_reserve` now requires an already confirmed (`sale`) order in the fixture
central warehouse. It never calls `action_confirm` and never changes the order's
warehouse. Read-only SPH operators/pickers retain only bounded stock-reservation
authority after their role and order read scope are checked. Normal Sales
confirmation must happen through a separately authorized Odoo Sales path; no
native Sales ACL/group grant was added. Synthetic model/race setup confirms
orders as the existing harness superuser before the reservation requests.

`test_readonly_reserve_cannot_confirm` proves both read-only reservation roles
lack order-write access and cannot confirm a draft through this method. The live
G3 suite repeats the operator attempt over HTTP, checks a durable deny-audit row,
and observes the committed SO remains draft with no picking. Race loser rollback
now means the previously confirmed order/picking remains unallocated, rather than
claiming the order confirmation itself was part of reservation.

Pre-G4 review #53/#55 F1/F2/P3 scheduling, native-actor/coverage, retry evidence,
location coverage and labeling items remain separate follow-up work. This F3
change does not claim those findings are closed or approve G4.

## B5a: discount and pricelist authority

Live baseline probe at `4546b2e` reproduced both missing boundaries: the existing
G1 group-union `sph_bot` (Sales manager, scoped to its own center) committed an SO
line discount and a switch to another own-center pricelist. The probe added no
group grants. See hub finding `dis-d3424628#65` and CI run `38673539533`; only
probe scripts changed before that observation. This does not imply that the
minimal bot ACL alone grants native Sales writes. All probe records are FIXTURE.

Price authority now covers `price_unit`, `discount`, and `pricelist_id` wherever
applicable: SO/PO line creates/writes and SO pricelist writes. The bot is denied
even with the broader native Sales fixture permissions. The dedicated approver
can perform the protected changes with an allow audit in the same transaction;
no native groups/ACLs are granted by this fix. Existing server-only PO draft
preparation retains its bounded private creation capability.

Six additional bound model tests cover SO/PO discount and SO pricelist deny/allow
paths. The live G3 matrix includes all three paths. The same own-center HTTP probe
now requires `Unavailable`, unchanged committed values and durable SPH deny-audit
rows, so a missing ACL, foreign-center denial or expired session cannot stand in
for the authority guard. Sanitized results are in `B5a-price-probe.json`.
B5b/B5c/B5d and G4 remain separate queued work; this closes only F-G3-2.
