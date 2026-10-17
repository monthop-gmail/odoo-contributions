# Synthetic Flow A+B dashboard formulas

The dashboard is a JSON report plus standalone HTML artifact, not an Odoo HTTP
endpoint. Open evidence/Dashboard.html after a run; Dashboard-results.json carries
all inputs and namespaced record references. No ACL/group changes are needed.

Each scenario runs its full clean CLI independently. After its assertions, a new
observer cursor reads only that scenario's confirmed SOs, sales lines and native
moves/pickings. Numeric IDs can repeat across fresh databases: the key is always
(scenario, model, id). Both source files must match the current commit and report
zero pre-existing Sales orders. Missing/stale inputs fail the dashboard; they are
never silently interpreted as zero.

| Metric | Formula and boundary |
|---|---|
| Fill rate (reservation) | Sum observed reserved native move quantities / sum requested SO line quantities, across both scenarios. Fixtures use discrete units. Not delivered/received fill rate. Zero demand is unknown/null, not 0%. |
| Backorders | Count distinct native sales picking IDs whose backorder_id is set, namespaced by scenario. Unallocated demand alone is not a native backorder. No partial delivery is executed in these flows. |
| Stockouts | Count distinct scenario SO IDs whose attempted reservation actually returned Unavailable for stock shortage. Excludes expected authorization denials and successful requests. |
| Open blockers (fulfillment) | Count confirmed scenario SOs with requested units > observed reserved units at the snapshot; list each unfilled quantity. This is an explicit demo reporting definition, not an invented real business policy. Excludes hub tasks, owner decisions and pilot governance blockers (not measured here). |
| CI gate blockers (separate field) | Sum failure/error/skipped counts in the five-case live-suite.xml. Expected bot-deny tests are successful cases, not blockers. |

Inputs are recorded in Flow-A-results.json / Flow-B-results.json under measurements.
A purchase confirmation creates planned incoming stock; it does not increase the
fill-rate numerator until receipt/allocation, which this demo does not perform.

Derivation for the intended demo, validated from observed rows rather than assigned
as KPI constants: Flow A requests two units and reserves one; Flow B requests one
and reserves zero. Thus reservation fill rate is 1/3, two shortage attempts and two
unfilled confirmed orders. Native backorders should be absent until a real partial
delivery creates one; the report counts actual records rather than assigning zero.
Any changed observations produce changed values or validation failure. No SLA,
threshold, pilot readiness score or real customer policy is inferred.


B6e I6: stockout IDs now come from a fresh cursor reading durable
`sph.authority.audit` rows with action `sale.reserve.stockout` / outcome `deny`,
scoped to the scenario SO IDs. Audit row IDs/action/outcome are included in each
measurement. Workers independently compare them to the actual HTTP shortage
response (exact UserError class + Unavailable), retaining all prior assertions.
The stockout path reuses the existing separate-cursor audit primitive; no commit
was added to reservation or any business method.

I7: separate-cursor `.locked.bundle` evidence is now feasible and asserted by
failed real HTTP SO and PO writes in G3. A fresh observer sees the durable deny
row and unchanged fields after rollback. Bound tests remain same-cursor,
rollback-only; they are not labelled durable.

## OD2 piece 3: reconciliation with the owner walkthrough

The original `calculate()` formulas above are unchanged. The rendering layer first
revalidates Demo-results.json and Demo-walkthrough.md against both same-tip source
snapshots and pins. It records the exact A/B epoch IDs and demo JSON/Markdown/source
hashes. A3/B5 now carry the existing dashboard measurements as step evidence (no
new query or scenario). Reconciliation requires A's two one-unit requested SOs to
match its race winner/loser and native allocation, and B's one-unit shortage SO to
remain unallocated. Stockout SO identities must match those losing/shortage orders
and the durable audit provenance. Backorders and unfilled confirmed orders come
from these same step snapshots, never inferred from a purchase receipt.

The HTML shows requested/reserved unit numerator and denominator (1 / 3 = 33.33%
for the current measured run), formulas, epoch-namespaced record references, and
links to explicit walkthrough anchors. Count metrics are labelled counts: the SO
population is context for stockouts/blockers, not an SLA percentage. Backorders
have no observed whole-picking population denominator, so the denominator is
explicitly **not applicable**, rather than invented. CI blockers use the five live
cases as their population and remain separate from fulfillment. Empty reference
lists mean no matching observed records, not missing input.

`python3 scripts/dashboard.py --from-evidence` only reads existing evidence and
renders JSON/HTML; it never starts a harness. The P0 report rebuilds the entire
Dashboard-results.json and Dashboard.html and compares both exactly, including
epochs, inputs, demo links/hashes, derivations and HTML. Missing/stale/tampered or
shared/swapped-epoch evidence fails. Both files are included in the evidence-files
digest and upload artifact. No JavaScript, external assets or Odoo endpoint is used;
all dynamic HTML values are escaped.

### M6.4 meanings awaiting owner confirmation — nothing confirmed here

- Reservation fill is observed allocation, not delivered fill or a service level.
- Unfilled demand is not automatically a native backorder.
- Stockouts count audited scenario shortage attempts, not distinct catalog items.
- Open fulfillment blockers count unfilled confirmed SOs, not hub/owner tasks.
- Scenario epochs are separate disposable databases; IDs cannot be joined across
  epochs. These are synthetic demo measurements, not business KPIs or SLA targets.

LOW-OD2P2-1: the profile in A0/B0 is now explicitly labelled **asserted** by the
existing seed invocation, not independently measured. No seed/profile was added.
