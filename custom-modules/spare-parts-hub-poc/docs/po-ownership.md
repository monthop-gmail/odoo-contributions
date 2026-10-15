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

## B7b capability closure

`approver()` invokes the same `_sph_po_scope` hook on POs (and the parent PO of
purchase lines), before maker/role checks or any delegated write. This covers
review, review-check/approval, confirmation, force approval, RFQ wizard and
incident metadata. All state/date/identity writes check scope before transition
checks. Draft editing checks scope before its maker-only operation. `_sph_digest`
is scoped human authority; `_sph_digest_value` is a private internal audit snapshot
only, avoiding recursive authorization while recording a denial. Neither private
method is callable through native RPC. Public caller context cannot grant access.
Bot force-approve retains the existing silent, unchanged-state denial when scope
is valid; foreign/empty scope raises the same generic Unavailable as other paths.

Global rules also intersect native access on PO lines, PO-linked messages and
attachments. The latter rules resolve their parent projection at each search,
not as cached PO IDs; normalized Odoo 19 Boolean search operators are supported.
Native read/export permissions remain unchanged. Native-capable rollback actors
prove positive and negative mail/attachment/line reads and search/count behavior;
ordinary SPH actors still receive no new native Purchase ACL. Purchase portal and
binary streaming check actual-user scope before native token elevation. Tokens
are not a substitute for center membership. Returning a checked RFQ wizard does
not send mail in this harness.

Bindings cover every section-G capability, no membership, both A→B and B→A with
one commercial parent, unknown/legacy-unassigned/revoked targets, spoofed context,
atomic mixed batches, and human explicit hub grant/revoke. The unassigned row is
emulated only by rollback-only schema/data setup, never by a business-method
commit or a weakened create constraint. Live G3 additionally observes committed
HTTP scope denials, unchanged states/reviewer/digest/receipts/quantities, bot group
unions including hub/native managers, and portal/binary token denials. No native
manager/hub grant remains on P0 actors after the matrix. Existing G1 union tests
now explicitly assert same-center positive access, so membership cannot mask the
bot/group-union negative checks.

P0 uses clean disposable databases; no upgrade/backfill of historical unowned POs
is provided. No main merge, deploy, new credentials or real data is authorized.

## B7c Part 0 — system actors, predicate and receipts

PO state/date/locked gates run under sudo using the actual `env.user`. A system,
uid-1 or cron-like actor without center membership is denied; sudo is not a
membership or approver grant. Do not enable a native PO automation expecting an
implicit privileged bypass. `_approval_allowed()` now raises
`AccessError('Unavailable')` on denial rather than returning False. Existing SPH
callers propagate that exception; no caller relies on a False return.

`stock.picking` no longer uses `_sph_scoped()` fallthrough: visibility requires
explicit membership, or the separate `group_sph_picking_hub` visibility grant. Native
ACLs remain unchanged. PO-created receipts inherit the PO center server-side.
The dedicated native G2 competitor receives the picking-only visibility grant only
inside its disposable race worker and revokes it before successful completion;
this preserves both native/SPH race outcomes without granting stock-manager to
an SPH role or seeding hub visibility. Native receipt tests cover empty scope,
same-center allow, cross-center deny and explicit-grant revoke.

## B7c I9 — actual assignments and one active company

`_sph_po_company` is the company choke point used by `_sph_po_scope` before any
role/review predicate or delegated action. It validates the entire client
`allowed_company_ids` selection against actual actor assignments, even under sudo;
unassigned IDs cannot be silently intersected away. The first selected company
is the active company (default: actor's primary company). Each operation is
limited to that one company, even if the actor is assigned to additional companies.
A supplied `force_company` must be an integer equal to that active company; it
cannot redirect approval. Empty/malformed selections deny. An explicit hub grant
broadens center visibility only, never company authorization. Direct company
changes must also pass this gate. Search/line and linked-surface projections keep
the same active-company boundary.

Tests arrange valid maker/checker, revision, two_step/0 and center scope before
probing foreign-company confirmation, to prevent another predicate masking the
company denial. Rollback-only tests add a synthetic second company and prove
active-company restriction, mixed-batch atomicity, company-access revoke, explicit
hub non-bypass and sudo non-bypass. The live worker probes forged contexts on an
otherwise valid reviewed PO, independently observes committed deny rows and
unchanged revision/state/receipts, then confirms under legitimate context. Its
second company is a disposable adversarial fixture, not a multi-company seed or
workflow: subsequent Flow A/B commands rebuild clean single-company databases.

P0 remains a single-company synthetic rehearsal. This evidence does not authorize
multi-company operation, staging, merge/deploy or pilot start. RFQ mail-send tests
and mail/attachment projection performance are backlog, not implemented here.

## B8 — independent PO and picking visibility grants

`group_sph_po_hub` grants all-center PO visibility only. The separate
`group_sph_picking_hub` grants all-center picking visibility only. Neither implies
the other, any native ACL/group, or any SPH approval/stock mutation authority;
both have zero seeded assignees. Native ACL and company rules still intersect
these visibility rules. A bot remains nonhuman even with either grant and native
manager/approver group unions.

The picking rule intentionally remains GLOBAL on **every picking** for P0. A
blank center is an ownership gap, not reliable evidence that a delivery/internal
transfer/legacy receipt is unrelated to SPH. Excluding blank rows would silently
restore broad native visibility and could leak an untagged SPH document. Without
a picking-only grant, missing membership yields no pickings and center members
see only explicitly tagged own-center pickings. Untagged pickings require the
explicit picking-only grant plus native rights. PO receipts remain server-tagged
from their PO. This is a conservative synthetic-harness boundary, not a claim of
compatibility with unrestricted native warehouse operations. Revisiting the
protected set needs an explicit ownership classification and separate approval.

The native race competitor now temporarily receives only the picking grant;
it never receives PO hub visibility. The worker restores its original groups and
asserts both grants absent before successful completion. Tests pin blank-row
behavior and grant independence in both directions with native-capable rollback
actors, without changing any shipped native ACL. B8-P0 rehearsal, RFQ mail-send,
projection performance, staging and pilot sign-off are outside this change.
