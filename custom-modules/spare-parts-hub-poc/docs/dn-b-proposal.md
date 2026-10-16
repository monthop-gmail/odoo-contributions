# DN-B proposal — upgrade and backfill impact (analysis only)

Source: hub dis-d3424628 #154 (options memo), #156 (review), #159 and #161
(approved bounded hardening). **DN-A remains the P0 posture.** DN-B is not
implemented here; no picking rule, visibility group, membership or ACL changes
are authorized by this proposal. SPH is NOT pilot-ready.

Current DN-A: every picking is covered by the global rule. A center member sees
explicitly tagged own-center rows; blank rows remain closed without the explicit
picking-only grant and native rights. The PO-only grant does not open pickings.

DN-B would narrow the SPH rule to positively identified SPH-owned pickings and
return confirmed native-only pickings to native ACL/company rules. It needs an
owner-approved marker and trusted classification process first. A blank center
alone cannot safely mean native-only. DN-C's explicit `sph/native/unknown` model
is a separate alternative if legacy ambiguity cannot be resolved safely.

## Proposed impact table — no backfill executed

| Existing/new population | DN-B upgrade risk | Proposed classification/backfill work, only after approval | Required acceptance / rollback evidence |
|---|---|---|---|
| Existing tagged SPH PO receipts | Losing a center or changing rule semantics could disclose another center or hide valid receipts | Preserve validated PO→receipt ownership; reconcile center and company against the server-owned PO, with exception review | Before/after counts and IDs match; same-center allow, cross-center deny, company isolation; restore the original mapping if reconciliation fails |
| Legacy PO receipts with blank center | A blanket blank→native fallback would expose SPH receipts | Use authoritative purchase-line/order linkage and approved membership/company mapping; quarantine unresolved rows under DN-A | No unclassified SPH receipt enters native fallback; every backfill decision has provenance and a reviewer; restore snapshot and rule together on failure |
| Native delivery/internal transfer with blank center | Current deny becomes broader native visibility; this is a policy change, not harmless cleanup | Owner defines proof of native-only ownership; inventory applicable users, native ACLs and company scope before classifying | Authorized native user allow, unauthorized company/role deny; verify no SPH payload in the native-only set |
| Untagged rows with mixed, missing or contradictory origins | Free-text origin/name guesses can misclassify documents | Keep fail-closed until a named business owner resolves evidence; do not infer ownership from missing tags | Unknown remains denied; unresolved count and exception list block policy switch; no forced automatic classification |
| Backorders, returns, copies and chained transfers | Derived rows could lose ownership or acquire the wrong center | Define inheritance/reclassification rules for every creation path and reconcile legacy chains | Synthetic chain tests preserve ownership/company and cross-center deny; rollback covers parent and derived rows |
| New PO receipts after a switch | Newly created untagged SPH rows could escape the narrowed domain | Preserve server-side PO ownership propagation; decide whether to enforce a positive ownership marker/constraint | No public client can omit/spoof/reassign ownership; malformed/new unknown SPH rows deny, with no visibility gap |
| Existing PO/picking hub grants and role unions | Backfill or implied-group changes could widen PO/picking visibility accidentally | Inventory explicit assignees; retain separate grants and native ACL intersection; no automatic grant assignment | Grant independence/revoke and bot-union deny matrix; compare pre/post effective access, not only group labels |
| Company/center/warehouse/commercial-partner mappings | Treating these as interchangeable can assign the wrong owner | Validate each relation independently; define treatment of inactive or revoked memberships | Active-company and forged-context tests stay green; ambiguous membership is not an ownership source |
| XMLID/rule records and caches | Duplicate rules or stale domains can alter effective access during upgrade | Preserve one `sph_core.scope_stock_picking` XMLID and intended rule identity; plan cache invalidation and ordered schema/data/rule phases | Test from an existing synthetic transactional DB, count all relevant rules and verify effective access after upgrade and fresh sessions |
| Cutover, audit and recovery | A partial backfill/rule switch can create a leak window or irreversible loss of classification history | Approve a consistent DB+filestore snapshot, dry-run diff, maintenance/transaction strategy, provenance retention and a rollback owner before any switch | Witnessed synthetic restore and rollback of code/schema/data/rules/grants; reconcile receipts, moves/reservations and audit references; any incomplete classification or regression = no-go |

## Owner inputs and future gates

Before implementing DN-B: decide whether P1 has mixed SPH/native warehouse use in
one DB, approve the ownership marker, authoritative sources, unknown-row policy,
classification/review owner and explicit operational roles. OD4, real-data/privacy
review, M6–M8 and separate staging/migration authorization remain prerequisites
where applicable. No recovery objectives or business policies are invented here.

An approved future implementation would need synthetic transactional upgrade
fixtures, classification counts/provenance, every creation path, the full
same-/cross-center and company matrix, bot denial, grant revoke, independent
review and a witnessed recovery drill. This document provides no migration code,
SQL backfill, new grant, deployment plan execution or pilot approval.

## INFO-B8P0-3 — what the present upgrade evidence proves

The current rehearsal installs previous addon code on a clean disposable
`sph_poc` DB, then runs `-u sph_core` on that same DB. It verifies rule/XMLID
identity and grant separation. The probe records zero existing SOs, POs, pickings
and reservations before/after upgrade (before its rollback-only visibility probe).
Catalog and initial stock are synthetic seed fixtures. **This is NOT a
business-data migration**, not a backfill test, and not proof that retained
transactional rows/filestore/history survive a future policy migration. Those
need separate approved synthetic-data fixtures and, later, owner-authorized
operational planning. No real/PII data is used or authorized.
