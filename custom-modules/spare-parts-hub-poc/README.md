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
advisory locks for participating operations, then locks every existing matching quant row
in ID order before availability checks and native move assignment. Native quant
updates participate in the same advisory/row lock protocol. Advisory locking alone
does not refresh a REPEATABLE READ snapshot or prove absent-quant correctness:
row conflicts can require Odoo whole-request serialization retries. No reserve method
commits; Odoo's HTTP transaction owns atomic commit/whole-request retries. FCFS
means serialized confirmation at the stock lock; simultaneous arrivals have no
invented center priority.

All-or-nothing is the default. Explicit partial allocation retains outstanding
demand, records a backorder amount and uses native delivery backorders. Reservations
expire after 48 hours (FIXTURE policy), through the installed active cron; CI invokes its entrypoint explicitly because
scheduler threads are off. Expired requests cannot replay into a fresh
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

The historical F3 change alone did not close the other #53/#55 findings.
B5c and B5d coverage is recorded below; G4 remains pending.

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

### B5b authority path coverage

Six individually bound bot-denial tests cover SO-line priced creation, PO-line
creation outside the private draft capability, `do_scrap`, direct scrap completion,
quant creation, and `_update_available_quantity`. Existing guards cover these paths;
no authority expansion is needed. Transaction tests assert denial and unchanged
state without asserting independently committed deny rows. The live G3 matrix also
calls `do_scrap` and quant creation over HTTP, checking durable deny audits from a
fresh cursor after request rollback. Denied creation uses plain `res_id=0` because
no resource was created. All data and actions are synthetic harness fixtures.

### B5c expiry schedule and native competitor evidence

An active `ir.cron` calls `sph.reservation._cron_expire()` hourly (SYNTHETIC
ASSUMPTION sweep cadence; the fixture TTL remains 48 hours). CI leaves scheduler
threads disabled and explicitly invokes the installed cron through
`method_direct_trigger()` in the committed live harness. Fresh observers must see
an expired ledger, zero reserved native move quantity and zero reserved quant
quantity. This proves the installed scheduled action works; it does not measure
wall-clock scheduler timing.

The final two G2 rounds put SPH first and native assignment first respectively in
the advisory-lock queue, observing the first waiter before submitting the second.
Both HTTP requests wait behind the external gate before release. The suite requires
both actual winner outcomes, zero double allocation, and `Unavailable` for the SPH
loser. `G2-request-results.json` and the manifest record launch order, winner actor,
lock witnesses and cron-release evidence. B5d remains separate.

### B5d review close-out scope

PO purchase/done/date_approve writes require the private checked-button transition
capability. Reviewed human direct writes are denied, including forged client
context flags; normal confirmation still creates native receipts. `approver()`
has no uid-1, sudo or cron exception (see AGENTS.md).

The native assignment client uses the dedicated FIXTURE native actor. SPH picker
membership is never widened; G2 checks it remains outside stock_manager. The two
SPH reservation clients retain their original roles. Bound cross-center reserve
denials cover both directions under a shared commercial parent.

**Conservative location scope retained:** availability in `sph_reserve` and the
band projection counts only quants exactly at central `lot_stock_id`, not
`child_of`. Native assignment can consider descendants; therefore child-only
stock can be rejected/understated. This PoC supports the flat synthetic location
fixture only; it does not claim general hierarchical availability. Changing to
`child_of` requires matching location locking/reconciliation tests, rather than a
domain-only expansion. No business policy for child locations is inferred.

G2-retry-serialization.log captures matching server transaction-conflict/retry
lines and records their observed count in G2 results/manifest; no retry is invented
if none appears. G2-lock-waits.log remains the required contention evidence.
Live JUnit classnames identify each real gate; gate_acceptance reflects actual
runner success/skips/failures and always keeps G4 PENDING. Historical #61 and the
old blocked task are not implementation or G4 evidence.

### M5 seed boundary

The entire privileged fixture initializer is **disposable-test-harness only**:
it requires the explicit `disposable-test-harness` profile and the dedicated
`sph_poc` database. Missing, demo and pilot profiles fail before any seed writes.
The native stock-manager actor must never be reused in a demo/pilot seed; no such
seed is supplied here. A future demo seed must be separate and omit this actor.

M5 pins exact central `lot_stock_id` availability with child-only stock denied; S2 `child_of` support remains out of scope.

### B6b: one-command synthetic Flow A

From this folder run `python3 scripts/flow_a.py`. It removes this checkout's
harness volumes, starts a clean pinned Odoo 19 harness, seeds a distinct synthetic
Flow A dataset, runs two concurrent HTTP reservists, writes evidence, and always
tears down the harness. Docker/Compose and the existing Python harness are needed.
CI runs the same worker after real G3 via the existing live step; no workflow or
permission change is needed. `--running` is for an already initialized harness.

The Flow A seed accepts only disposable-test-harness / sph_poc, creates two
FIXTURE FLOW A centers, two scoped human reservists and two portal requesters,
and one catalog item with exactly one free unit at the exact central location.
It creates no stock-manager actor/grant; existing bot and approver personas are
referenced, and no bot approves anything. The base gate-test harness retains its
separate test-only native competitor, which is not part of the Flow A seed.

Synthetic authorized setup confirms Sales orders **before** reservation, respecting
the existing F3 boundary. The winner's reservation links to that confirmed SO and
native move; reservation never confirms a draft SO. Both HTTP requests wait behind
a lock gate; fresh observers require exactly one allocation, loser Unavailable,
zero double allocation and no negative stock. This is synthetic evidence, not a
business-policy or pilot sign-off. Flow B remains outside this command.

`evidence/Flow-A-results.json` records commit, pins, synthetic center/persona/product/
location IDs, SOs, winner reservation->SO->move link and observed outcomes;
`Flow-A-assertions.xml` records success. Session material is never printed or saved
in evidence. Existing G1/G2/G3 artifacts and the 77-test floor remain intact.

Review #94: mixed locked writes by an approver are rejected, role and scope reserve
denials both use UserError(Unavailable), and legacy PO state=done is defensively
rejected only (Odoo 19 locking uses boolean locked).

**WIPE WARNING:** `flow_a.py` deletes this checkout's disposable harness volumes
before starting. Never point it at a non-disposable database or reuse its compose
project for valuable data. Flow A now requires one company and deletes all of its
server-side sessions on success or failure, including `--running`; evidence has
no session IDs.

### B6c: one-command synthetic Flow B

From this folder run `python3 scripts/flow_b.py`: down -> clean pinned harness up
-> Flow B -> always down. **WARNING:** it wipes this checkout's disposable volumes;
never point it at any non-disposable DB. `--running` uses an existing disposable
harness, and all created sessions are deleted in finally, including failed runs.

The isolated Flow B seed is single-company, disposable-test-harness / sph_poc
only, rejects demo/pilot profiles and creates no stock-manager grant. A new
FIXTURE center/product has zero free stock. A scoped reservist's real HTTP
reservation fails with Unavailable and no reservation. A dedicated FIXTURE FLOW B bot with the existing sph_bot role calls
sph_prepare to create only a draft RFQ. Its HTTP button_confirm is denied with a
durable separate-cursor audit; an independent observer sees draft/no receipt.
A distinct human approver reviews and confirms; evidence requires purchase state,
a native receipt, bot maker != human checker, and a human allow-audit row. No
receipt is validated, stock received or financial action performed.

CI now has distinct live cases for G1, G2, G3, Flow A and Flow B (5 total), using
the same scenario workers on the workflow's initialized disposable harness.
Flow A retains every prior race assertion. Flow-B-results.json includes final
commit SHA, pins, synthetic IDs, shortage/bot-denial/human-confirm outcomes and
session cleanup status. Flow-B-assertions.xml is included with existing evidence
in sph-harness-evidence; the GitHub artifact ID/digest is reported in the hub.
These are synthetic scenario results, not pilot sign-off. Dashboard and War Room
remain outside this round.

Flow B uses a separate bot fixture so G1's deliberately widened group-union bot stays untouched; no G1/G3 test grants or assertions are removed.

### B6d Part 0: clean CI and audit-test boundary

CI executes the full Flow A and B CLI paths independently: each down -> fresh
harness up -> scenario -> always down. Host evidence survives volume deletion;
scenario record IDs belong to separate disposable DB epochs and must not be joined
across scenarios. Dedicated live testcases remain separate. Bundle bound tests
now inspect rollback-only same-cursor deny rows before the assertion savepoint
rolls back; this narrow test-mode sink never commits and is not durable evidence.
Runtime deny audits retain their separate committed cursor. Cleanup logs contain
only a fixed failure label; cleanup failure cannot mask an existing scenario
error, and a failed cleanup on an otherwise successful scenario fails closed.
Flow B center, partner, reservist and bot now have stable fixture_flow_b_* xmlids.

### M3 measured dashboard artifacts

After the five real live cases pass, CI runs `scripts/dashboard.py` and includes
`evidence/Dashboard.html` and `Dashboard-results.json` in sph-harness-evidence.
Open the HTML locally after downloading the artifact. Rebuild with
`python3 scripts/dashboard.py` when matching Flow A/B JSON and live-suite.xml exist.
Formulas and derivation: [docs/dashboard-formulas.md](docs/dashboard-formulas.md).
The report validates current SHA and fresh scenario DB snapshots; numeric record
IDs are namespaced by scenario. No endpoint, ACL/group grant, fake KPI constant or
SLA target is added. Open blockers means unfilled confirmed scenario orders; hub
and pilot governance blockers are not measured. Dashboard failure fails CI after
the separate five-case JUnit is written. The static live runner now invokes its
unit-test entrypoint, including dashboard stale/unclean-input controls.

### M2 SPH-side opaque incident references

`sale.order.sph_incident_ref` and `purchase.order.sph_incident_ref` are optional
opaque metadata. Existing human approvers may attach/replace/clear on in-scope
orders using a single-field write; bot writes, bundles and nonempty create-time
injection are denied. Existing record rules still govern reads. Reservations use
the SO link via order_id, rather than copying an independent reference.
Contract: [docs/incident-contract.md](docs/incident-contract.md). No external FK,
HTTP/MCP/provider import, secret or runtime ai-collab/ai-war-room dependency exists.
The counterpart/OD6 is not built. G3 exercises bot deny/human allow over real HTTP
and checks the audit snapshot. No stock/price/purchase authority is implied.

B6e stockout reporting reads durable `sale.reserve.stockout` audit rows from fresh
cursors, retains exact UserError/Unavailable checks, and validates audit provenance
in the dashboard. G3 additionally observes durable SO/PO `.locked.bundle` rows
after failed RPC rollback; no new business-method commit is introduced.


### P0 rehearsal evidence (B8-P0)

The existing CI live-suite command now additionally installs B7c commit
`631cd523d014595411b7726b09a6a5eae8175fd8` in an isolated Compose project, upgrades
that same `sph_poc` database to the checkout tip, and always removes that project's
containers/volumes. It fetches the public previous commit read-only if checkout
is shallow; no credentials or workflow permission changes are needed.

`python3 scripts/harness.py up` then `python3 scripts/live_suite.py` runs G1–G3,
full Flow A/B (each CLI wipes/rebuilds its own disposable epoch and tears down),
the upgrade check, and writes `evidence/P0-report.json`, `.md`, and `.sha256` into
`sph-harness-evidence`. Always finish with `python3 scripts/harness.py down` (CI
already has an always-teardown step). These commands destroy this checkout's
**disposable** harness data and must never target another database.

The consolidated report revalidates bound execution, live cases, same-tip clean
Flow A/B snapshots, measured dashboard values, durable G3 counts and upgrade
identity/grant assertions. It includes per-evidence-file/content-manifest hashes
and the reviewed base artifact digest. The upload archive digest exists only
after upload; it is recorded in the final hub post, avoiding a circular self-hash.
Missing/stale/failed/skipped evidence makes the report/job fail.

DN-B8-1 remains **owner-decision-needed-before-P1**: picking ownership and native
warehouse narrowing are unchanged. This is synthetic P0 evidence, not pilot
sign-off, staging or deployment authorization.

#### P0 report hardening (#152 / #161)

Upgrade assertion fields now derive from raw probe measurements (XMLID/rule IDs,
global/model fields, actual group/visibility counts and empty-business-row counts).
The report recomputes those checks and rejects disagreement or any failed check.
`p0-evidence-baseline.json` versions the reviewed G3 coverage (140 deny / 22 allow)
and minimum G2 coverage/contention (4 rounds / at least 1 witnessed lock-wait round).
A smaller internally consistent G3 matrix or zero contention cannot produce PASS.
Intentional coverage changes require an explicit baseline update and review.

INFO-B8P0-3: **NOT production/business-data migration approval**. Alongside the
empty-business-DB check, the retained-data check installs `e481eeda`, commits
synthetic POs, receipt/picking rows, an SO/reservation and center assignments, then
updates that same isolated DB to the checkout tip. Before/after snapshots, XMLIDs,
rule IDs and DN-A visibility must agree. This does not authorize real-data
migration or DN-B backfill. See the
[DN-B upgrade/backfill impact proposal](docs/dn-b-proposal.md) for analysis only.
DN-A remains fail-closed; picking rules, groups and access policy are unchanged.

#### Reviewed baseline changes (OD2 piece 1)

The exact G3 baseline remains **140 deny / 22 allow / 162 total**. The baseline
file carries `baseline_version`, `reviewer` and `review_source_ref`; the matching
entry in `p0-baseline-reviews.json` registers the canonical baseline SHA256.
A changed baseline or unregistered version fails with **baseline bump requires
review**. To propose a bump: retain failing evidence, explain each changed path,
obtain independent review in the hub, then update version/reviewer/source and the
registration together in a reviewed commit. Never reduce coverage merely to make
CI pass. The registration is review metadata, not a cryptographic authorization
service; changes to both files require independent review.

`test_leftovers.py` exercises RFQ composition and sending with a captured mail
transport and SMTP/SMTP_SSL tripwires. Native Purchase capability exists only in
that rollback-only test actor, never in P0 seed data. It also records warm-cache
mail/attachment search/read query counts and timings at 2/10/30 authorized POs,
with one foreign candidate excluded at every size. These measurements characterize
the synthetic path; they set no SLA and certify no production capacity. Markers
`SPH_RFQ_CAPTURE` and `SPH_RULE_PERFORMANCE` are preserved in module-test logs.
DN-A stays fail-closed; no picking rule, group, ACL or runtime policy is changed.

### One-command owner walkthrough (OD2 piece 2)

From this folder run **`python3 scripts/demo.py`**. WARNING: this deletes this
checkout's disposable harness volumes. Never point it at a non-disposable DB.
It reuses the existing Flow A CLI (down → fresh pinned up → scenario → down), then
Flow B CLI on another fresh epoch, and always attempts a final teardown. Existing
single-company / `sph_poc` / `disposable-test-harness` guards and session cleanup
remain in force. No new seed/persona/profile is introduced; a separate demo/pilot
seed remains out of scope.

Read `evidence/Demo-walkthrough.md` in step order: synthetic persona/center,
action, expected outcome, measured observed outcome, PASS/FAIL. The header records
the checkout SHA, pins and distinct scenario epochs. Record IDs are **not
joinable across epochs**. Flow A shows two centers racing for one unit and its
reservation→SO link. Flow B shows shortage, bot draft/confirmation denial with
durable audit, a different human approver, and an unvalidated receipt. It also
observes zero completed stock moves/invoices and unchanged zero on-hand stock for
the shortage product. No real stock/financial operation is performed.

`python3 scripts/demo.py --from-evidence` only renders existing same-tip
`Flow-A-results.json` / `Flow-B-results.json`; it does not start or wipe a harness.
CI uses this builder after its existing full fresh Flow A/B live cases, without
rerunning scenarios. `Demo-results.json` stores the validated ten-step table and
source hashes; the P0 report reconstructs both JSON and Markdown from those
sources and hashes both artifacts. Stale/mixed SHA/pins, missing or changed steps,
failed observations or altered Markdown make the demo/report fail. Both are in
`sph-harness-evidence`. This is a **synthetic P0 demo, not pilot sign-off**; owner
validation and independent review remain separate.

Optional LOW-OD2P1-1 is implemented: the live CI entrypoint checks baseline and
registry diffs against independently reviewed `7ca94792` (#172). Touching BOTH
files fails with `baseline+registry co-change requires independent hub review`.
A shallow clone may fetch that public commit read-only using the existing fetch
pattern; no workflow change, credential or permission is added. Advancing this
reviewed anchor itself requires independent review. A single-file change still
faces the existing digest/version/reviewer/source registration validation.

### Dashboard linked to the demo (OD2 piece 3)

After the existing demo/live run, open `evidence/Dashboard.html`. It displays the
measured numerators/denominators, formulas, counted epoch-namespaced records and
links to the matching walkthrough steps. Header: SHA, image/runtime pins, exact
G3 140/22/162 and scenario epochs. **SYNTHETIC P0 — not KPIs, no SLA targets, not
pilot sign-off**. M6.4 metric meanings remain awaiting owner confirmation.

To reproduce downloaded same-tip evidence, place Flow-A/B results, Demo results
and walkthrough, and live-suite.xml in `evidence/`, then run
`python3 scripts/dashboard.py --from-evidence`. It only renders: no harness wipe,
scenario, database or external service is started. Both dashboard files reproduce
byte-identically for the same inputs. The P0 report now validates the entire JSON
and HTML, demo hashes and epochs, and hashes both outputs. See
[dashboard formulas and reconciliation](docs/dashboard-formulas.md).

Optional LOW-OD2P2-2 remains for independent review: making baseline_diff.py flag
its own edits against its current fixed anchor would flag the implementing commit
itself. No self-approval/anchor exception is introduced to turn that red check
green. The existing baseline+registry co-change gate and hub-review requirement
for changing its anchor remain intact; this piece leaves that script unchanged.

The artifact also includes `Dashboard-formulas.md`, an exact validated copy of the
repo formula document, so its owner-confirmation link works when downloaded
without the checkout. The P0 report checks the copy against the source.
