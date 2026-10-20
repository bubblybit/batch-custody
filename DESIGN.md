# BatchCustody design and implementation plan

AI-assisted prototype; local implementation only. The user delegated design and execution. A public record-of-custody primitive, not physical delivery evidence or asset custody.

## Contract

Zero constructor arguments; deployer issues fixed batches. Manifest is an on-chain canonical JSON array of 1..8 entries {item_id,url,sha256,quantity}; exact commit-pinned raw.githubusercontent.com content, positive exact integer quantity <=1e9, unique IDs and <=16384 bytes per content response. Quantities are synthetic declared units, including in the real-public-software fixture. They do not represent ownership, scarcity, licences or tokenized assets. Every entry's bytes are independently fetched and SHA checked on batch opening and on recipient acceptance.

Each lot is an immutable quantity vector and named holder with ACTIVE -> LOCKED -> SPENT transitions. Propose locks an entire ACTIVE input lot at a CAS revision, offering a positive bounded subset to one different nonzero recipient. Accept is explicit by that recipient before the exact deadline. It spends the input permanently, creates one recipient lot and, if necessary, one sender remainder lot. No accepted input can be spent twice. Cancel (sender only) or expire (any caller at/after deadline) terminalizes the offer and unlocks its source, retaining the incremented revision. A fresh nonce is mandatory for another offer; nonce scope is batch+sender so another party cannot squat another sender's nonce.

API: `open_batch(batch_id,manifest_json)` returns initial lot ID; `propose_transfer(batch_id,lot_id,expected_revision,amounts_json,recipient,nonce,ttl_seconds)` returns offer ID; `accept_transfer(offer_id)` returns output lot IDs; `cancel_transfer(offer_id)` and `expire_transfer(offer_id)` never need web access. `get_batch`, `get_lot`, `get_offer`, `audit_batch` provide the bounded graph and conservation audit. Offer IDs and capture packets bind chain/contract/batch/source lot/revision/sender/recipient/amounts/nonce/deadline. TTL 60..86400 seconds, max64 offers and64 total lots/batch. Concurrent offers can exhaust output capacity; the blocked pending offer can still cancel/expire. Acceptance is atomic and source failure leaves it pending without changing quantities.

`audit_batch` counts each ACTIVE or LOCKED lot once and excludes SPENT lots; it compares every item total against the original manifest. Reservation does not create a second inventory. There is no forced issuer transfer, balance refund minting, financial settlement, private delivery oracle, or emergency admin override.

## Plan and TDD

1. Prepare standalone official SDK harness and tests against a minimal deployable contract. Preserve actual assertion failures for absent behavior.
2. Independently verify fixed public content and manifest on opening/acceptance. Reject changed bytes, forged validator packets, duplicate item IDs, boolean/zero quantities, mutable URLs, oversized content.
3. Implement lot CAS, nonce scope, named acceptance and exact expiration. Tests use several real SDK addresses, split and re-transfer output lots, literal conserved quantities, rejection of overspending/double acceptance/old offers, sender cancellation, anyone expiration, offline recovery, caller isolation and deadline boundary.
4. Execute whole-package direct pytest and exact v0.2.12 full lint/semantic/schema; preserve all logs. Write API/limits/reproduction and safe contribution ZIP. No browser or deployment. Submit for independent review.

Tests mock only external HTTP. No copied production accounting algorithm runs in host tests; assertions check literal quantities, ownership and terminal state through actual deployed contract methods.
