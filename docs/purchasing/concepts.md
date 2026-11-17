# Concepts and business rules

Purchasing's four models use independent metadata and namespace erp-purchasing. Order
is the versioned aggregate. Lines belong only to that order and capture immutable
commercial/item/unit facts at confirmation. Receipt is a unique retained line claim;
AuditEvent records actor/action/resulting version atomically. No foreign tables enter
this provider. Cross-module UIDs are public references, not foreign-owned models.

A draft can be edited. RFQ ready is a preparation state, not evidence of email delivery.
Confirm requires at least one active purchasable item and revalidates shared references.
Expected delivery date is informational. Confirmed terms are immutable. Cancellation
or reopening cannot discard receipt/bill claims. Closing requires all lines received
at that moment and does not require Finance. Later physical returns remain visible;
closed is historical and does not guarantee current availability.

Quantities, prices and discounts are bounded decimal strings. Amounts use Base currency
precision/rounding; no tax is included until Finance. Catalog purchase units determine
ordered quantities; snapshots retain stock units, both factors and exact converted
quantities. Product quantities must match the stock increment without rounding. Service
acceptance does not move stock. Inventory's fixed standard cost is independent of price.

A line has one retained receipt. Service acceptance requires evidence; revoke while confirmed and before
billing retains the record and prevents billing/closing. Re-acceptance after revocation,
replacement of cancelled/returned physical receipts and partial receipts are deferred;
create a separately reviewed corrected order. Physical receipts begin as Inventory draft
supplier-to-internal movements; prepare/complete them there. Stock item company/product/
unit must match the order snapshot. Purchasing retains the movement UID only.

A bill covers the full order only when all services are accepted and physical receipts
are completed/unreturned. The single same-source transaction joins owner-authored Finance
bill statements, Inventory receipt version fences and Purchasing's versioned bill claim.
It either commits completely or rolls back. Finance independently requires finance.write;
Inventory requires inventory.manage for receipt/fence operations. Existing vendor bills
can be reviewed/posted/paid in Finance. Later supplier returns never silently credit bills.
The source quantity, description, price and discount remain locked in Finance draft edits.

Optional adapters import their owners only on use; ready checks only Base/Catalog and
own bindings. Independent purchasing.read/write/manage/configure capabilities derive
from injected identity/Teams, not a new user store. No hosted verification is implied.
