# B7a PO ownership (P0; partial I8 implementation)

OD1 dec-14c7ad89 / hub #125: each PO belongs to exactly one creator center,
single-company synthetic P0. `purchase.order.sph_center_id` is required,
readonly/copy=False and immutable through write. Create and sph_prepare derive
it from exactly one actual-actor membership; zero/ambiguous creators deny even
with a visibility exception. Client center values and center-default context
keys deny, including values matching the legitimate center. No ownership is
inferred from the supplier/commercial partner or a client company/context value.

`_sph_po_scope` is the shared center + company hook. B7a wires create/prepare and
the native read/search/export boundaries. A new GLOBAL PO rule checks explicit
memberships, independent of `_sph_scoped()`. Empty membership denies. The only
all-center exception is `group_sph_po_hub`, with no implied native ACL/role and
no seeded assignees. Visibility never grants native Purchase read/export or
approval permission. Native-ACL positive/negative tests deliberately grant the
existing Purchase-user group and native export permission ONLY in rollback-only unit fixtures, so an ACL
failure cannot mask a broken center rule. The live harness temporarily tests the
hub exception using existing bounded incident metadata authority, revokes it,
and verifies no assignees remain. No native Purchase ACL is added.

All scope/owner failures use Unavailable and the existing durable ID-free deny
audit mechanism. Authorized searches filter foreign rows without disclosing their
existence. Trusted sudo observer reads remain available for reconciliation;
creator checks still run under sudo using the actual actor, not uid=1 fallthrough.

Fixture changes give the existing bot/approver one explicit center; G3 aligns
its positive fixture actors and SO/PO center rather than relying on broad visibility.
Flow B explicitly scopes its approver to that synthetic center. No P0 actor has a
hub-wide grant. Foreign-company unit setup explicitly authorizes its trusted
fixture creator; the approver remains outside that company and must be denied.

**Not complete I8/I9:** B7b still must wire the helper into sph_draft/review/check/
confirm/approve/RFQ/digest/incident and all remaining section-G paths, then prove
the full matrix including lines/mail/attachments. B7c owns remaining company and
forged-context approval tests. Existing sudo capabilities not covered by this
piece are not claimed center-safe. Do not describe B7a as pilot readiness.

P0 uses clean disposable databases; no upgrade/backfill of historical unowned POs
is provided. No main merge, deploy, new credentials or real data is authorized.
