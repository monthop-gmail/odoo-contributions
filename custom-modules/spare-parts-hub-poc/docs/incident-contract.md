# SPH incident reference contract v1

This is a version-neutral data contract, not a live War Room integration. It does
not select a provider, Odoo version for a counterpart, transport or external DB.
The current implementation is Odoo 19 CE. No runtime dependency on ai-collab or
ai-war-room exists: no provider import, HTTP client, MCP call, credential or FK.
The external owner/counterpart remains OD6 and is not implemented here.

| Record | Field | Meaning |
|---|---|---|
| sale.order | sph_incident_ref | Optional opaque incident identifier for this sales/fulfillment context |
| purchase.order | sph_incident_ref | Optional opaque incident identifier for this purchasing context |
| sph.reservation | No copied field | Follow existing order_id to its SO reference; no duplicate mutable value |
| sph.authority.audit | incident_ref | Snapshot of the current order reference on an audit event; no external FK |

The reference is a Char of at most 128 ASCII characters, matching
`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`, or empty/False to clear. It is not a URL,
a secret, a title or a place for personal/private document content. Synthetic
examples: `fixture:incident:001`. Format validation cannot certify the data's
classification: operators must still supply synthetic opaque IDs only here.
The field is not copied when an order is duplicated.

## Authority and audit

Only an active human in the existing SPH purchasing-approver role may attach,
replace or clear a reference on an existing order they can read. Bot membership
denies even when unioned with human/native groups; uid-1/sudo is not an exception
to this role check. A write must contain only sph_incident_ref. Validation and
record scope precede a narrowly elevated single-field write. Bundled writes are
rejected. Creation with a nonempty reference is rejected (attach after creation).
No ACL, rule, group grant, business approval or stock authority is added.

Reads follow existing model ACLs and center/native record rules. This field never
bypasses those rules or acts as an access token. Invalid/foreign writes return
Unavailable; attempted invalid content is not copied into audit metadata.

Successful changes emit `incident.reference / allow` in the same transaction as
the field change. Audit rows identify actor, local model/plain resource ID and
current reference; clearing records an empty snapshot. Denials use the existing
separate-cursor durable audit path at runtime. Bound tests never claim durable
separate-cursor evidence; live G3 checks it. Existing approval/revision/price/stock
boundaries are independent of this metadata. A reference cannot approve an order,
reserve stock, confirm a purchase or validate a receipt. No business-method commit
is introduced.

## Counterpart handoff (document only)

An external owner may later exchange an event envelope such as:
`{contract_version:1, origin_system:<opaque>, resource_model:<local model>,
resource_id:<local ID>, incident_ref:<opaque>, action:link|replace|clear}`.
Identifiers are scoped by origin system/database, not globally unique numeric IDs.
No such event is automatically emitted, consumed or delivered by this module.
No incident existence, URL resolution, bidirectional sync or delivery guarantee is
claimed. Human reconciliation and any counterpart implementation require separate
ownership/approval. Current audit rows prove only the SPH-side change; an external
acknowledgment must be separate evidence. There is no invented live War Room.

Tests cover field type/copy behavior, allowed human writes, bot and create/bundle
denials, scope, clear and invalid syntax. Fixtures and CI use only opaque
`fixture:incident:*` values. This contract is not pilot/production sign-off.
