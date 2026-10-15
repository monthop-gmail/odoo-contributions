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
