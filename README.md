# BatchCustody

An AI-assisted prototype for explicit custody **records** over fixed public content manifests. A sender proposes a named handoff; only the recipient can accept. Acceptance permanently consumes one input lot and produces recipient/remainder lots, preserving every item's declared integer quantity. It is a reusable attestation ledger, with no asset transfer, real stock promise or physical delivery oracle.

**Status:** local prototype; not deployed, published or audited. No live network consensus, gas measurement or real custody operation has been tested. Constructor takes **zero arguments**; deployer becomes immutable issuer. Deployable source: `batch_custody.py`.

## Why GenLayer

Batch opening and recipient acceptance require public content availability and integrity. The leader downloads every manifest object and verifies its SHA256; validators independently download/hash **every object**, rederive the complete result and compare canonical JSON. Captures bind the immutable manifest, chain/contract/batch and exact pending offer, source quantities and acceptance time. This is substantive source revalidation, not schema-only approval. Source bytes, metadata and any prompt-like content are inert; no LLM is involved.

After consensus, deterministic code enforces named recipient, expiry, source-lock identity/revision, exact amount vector and output capacity. The same input lot becomes SPENT once; later calls cannot split it again. Cancel/expire unlock without a web dependency. The issuer has no forced-transfer or recovery override over other holders' lots.

## Interface and demonstration

Complex inputs are strict JSON **strings**. Identifiers/nonces are `[A-Za-z0-9_-]{1,64}`. Digests are lowercase 64-hex. Recipient is a different nonzero `0x`20-byte address. Manifest URL format is exact `https://raw.githubusercontent.com/<owner>/<repo>/<40 lowercase hex commit>/<path>`, with no query, credentials, ports, mutable refs or dot/empty path segments.

| Method | Effect / result |
|---|---|
| `open_batch(batch_id, manifest_json) -> str` | Issuer only, unused batch ID. Independently verifies all public content and creates initial ACTIVE lot owned by issuer. Returns its lot ID. |
| `propose_transfer(batch_id,lot_id,expected_revision,amounts_json,recipient,nonce,ttl_seconds) -> str` | Current holder only. ACTIVE input at expected revision; locks it and increments revision. Returns immutable PENDING offer ID. |
| `accept_transfer(offer_id) -> dict` | Named recipient only, strictly before deadline; revalidates source; consumes input and returns `{recipient_lot,remainder_lot}`. Empty string remainder means no remainder exists. |
| `cancel_transfer(offer_id)` | Sender only; PENDING -> CANCELED; source becomes ACTIVE, keeping incremented revision. Works offline and at/after deadline. |
| `expire_transfer(offer_id)` | Any caller, at or after deadline; PENDING -> EXPIRED, source unlocked. Works offline. |
| `get_batch`, `get_lot`, `get_offer` | Immutable manifest/lineage and mutable terminal status, current revision and acceptance evidence. |
| `audit_batch(batch_id) -> dict` | Original and live item totals, conservation boolean and active/locked/all lot and offer counts. Counts LOCKED input once, never also as a second reservation inventory. |
| `get_configuration()` | Issuer, protocol and limits. |

Manifest is 1..8 entries, exactly `{item_id,url,sha256,quantity}`. Quantity is exact positive integer <=1e9, **not boolean**. IDs are unique. JSON manifest input <=12000 characters; each downloaded content object1..16384 bytes. Entries are canonicalized by item ID; root manifest hash covers URLs, hashes and quantities. Amount vector is a nonempty object containing available item IDs with exact positive quantities <= source lot quantities; omitted items remain with sender.

The fixture uses real public GenLayer boilerplate README and licence bytes pinned to commit `e685f1f12c4c357787d48390692a654baf576f03`. Quantities **10 guide record units and 7 licence record units are explicitly synthetic**. They are not copies actually held, ownership, scarce objects, licence grants, tokens or shipping inventory. See `fixtures/manifest.json` and `fixtures/sources.json` for exact public URLs/digests. The public licence bytes are preserved in `fixtures/public-license.txt`.

Example integration, with separate actual transactions from issuer and recipient:

```python
# issuer: root = open_batch("manuals", json.dumps(saved_manifest))
# issuer: oid = propose_transfer("manuals", root, 0,
#             '{"guide":4,"license":2}', recipient_address, "handoff-1", 600)
# recipient: outputs = accept_transfer(oid)
# recipient receives quantities {"guide":4,"license":2}
# issuer remainder is {"guide":6,"license":5}
# audit_batch("manuals")["live_totals"] remains {"guide":10,"license":7}
```

Integrators should verify protocol/contract/chain, fixed batch manifest hash, holder, exact quantities and terminal `ACCEPTED` offer with named recipient. Do not infer custody from a PENDING proposal. Track lot IDs rather than summing historical lots: SPENT ancestors must be excluded. A recipient may later transfer an output lot to another named address using its fresh per-lot revision0.

## State and security boundaries

- Input lot lifecycle is ACTIVE -> LOCKED -> SPENT after acceptance, or LOCKED -> ACTIVE after cancellation/expiration. Source revision increments at every proposal and is never reset. A canceled/expired offer is terminal; it cannot consume a re-locked input. Accepted source is never revived. There is no merge operation.
- Sender-scoped nonce key includes batch and sender. Successful proposal burns that nonce permanently even on later cancellation/expiry. Another custodian can use the same nonce without consuming another sender's key. All IDs bind chain, contract, batch, parties, source lot/revision, amounts, nonce and timestamps. The recipient sees exactly the immutable offer it accepts.
- TTL60..86400 seconds. At deadline, acceptance fails and anyone can expire. There is no automatic timer transaction; callers invoke cleanup. Sender can cancel before recipient accepts, so a proposal is not irrevocable delivery consent. Transaction ordering determines which valid terminal action wins.
- Up to64 offers and64 total lots per batch. Full transfer creates1 output; partial transfer2. Different pending offers may compete for remaining output capacity; acceptance can then fail safely while cancel/expiry remains available. Capacity includes SPENT history and canceled offers; it is a permanent per-batch bound, not recycled.
- Source outage, SHA mismatch or validator disagreement prevents opening/acceptance; it does not destroy a pending offer or quantities. Re-fetching every manifest object on acceptance is conservative even if only one item is offered. No hidden fallback trusts a cached proof.
- Acceptance captures freeze the **pre-transition** offer by value. The stored receipt cannot reference its enclosing subsequently mutated offer. Source manifest and quantities cannot be changed by later proposals.
- Byte checks are after download; the exact SDK does not expose redirect/final-URL controls or pre-download byte caps. Matching pinned hashes prevent accepting altered bytes, not transport DoS or source disappearance.
- Public data only. No private documents, personal metadata or sensitive shipping details. Issuer-defined public content/quantities establish a record namespace, not lawful ownership, real-world inventory, supplier independence, delivery authenticity, title or insurance. There is no payment, staking, external settlement or actual asset custody. SHA collision resistance and GenLayer consensus assumptions remain dependencies.

## Reproduce and evidence

Python3.12, isolated environment, no browser/wallet/RPC:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\verify.py
```

The verifier sets up official **GenVM v0.2.12**, exact pinned runner `1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`, stdlib `11rhn002yfajawsz7fai6mykznbxkxs6l91iskj5cm82c92qhy3v`, then whole-package pytest, full official lint/semantic check and ABI schema extraction. Requirements: `genlayer-test==0.29.2`, `genvm-linter==0.11.0`, `cloudpickle==3.1.2`. Setup initially needs public SDK downloads. Results and hashes are under `evidence/verification.json`.

Tests execute the real source/storage/calldata/authorization/clock/captured validator functions; only external HTTP is mocked from real saved bytes and adversarial responses. `tests/conftest.py` contains only Windows fd0 file-cleanup and official warp-metadata compatibility, no accounting substitute. Direct mode is not gas metering or a live network consensus test.

Actual TDD evidence: 20 initial failures against minimal deployable contract. The SDK's `create_address` returns bytes before SDK setup; the test helper now renders either bytes or Address correctly. The corrected suite was rerun against the empty contract and again had20 genuine failures (`tdd-address-corrected-red.log`). A later real run found4 failing acceptance tests caused by a cyclic mutable capture reference; `tdd-capture-cycle-red.log` preserves it. Freezing pre-transition offer fixed it. Final **20 tests pass**, full lint/semantic and schema exit0. Tests cover conserved partial/full downstream transfers, wrong caller, locked/spent reuse, cancellation/revision/replay, deadline cleanup, malformed quantities/manifest, changed bytes and independent validator rejection. No failing test log is relabeled as success.

Original code/tests are MIT; upstream public software bytes retain their own included licence. This package is independent of DatasetSplitCovenant and all counted Projects; it consumes no sibling source at runtime or test time.

## Independent review

A second agent read the frozen source hash, state/consensus paths, documentation and recorded SDK evidence on 2026-10-21 and reported no reproducible important issue. It made no source edits and did not rerun the tests. See `evidence/peer-review.json`; this bounded review is not a security audit, deployment or live consensus claim.

## Commit-locator correction

A follow-up SDK regression reproduced acceptance of dot-only repository segments in the old URL validator. The validator now rejects both `.` and `..` before accepting a commit locator. Exact source-byte SHA256 checks remain enforced. Two new real SDK regression cases failed before the fix and pass after it; full SDK checks were rerun. The earlier review and source hash describe the superseded version, not this corrected version.

## Actual Studio deployment

Network: GenLayer Studio (61999), Normal/full consensus, zero transaction value. Contract: `0x2703f9d6a523150e6d975c47CAca61861A94C3F6`. Deployment transaction: `0x82aa4f18e6c832c129d7b80c599856e39375b2047b19ba627dd6a9764d0ffb4f`, FINALIZED/SUCCESS with majority agreement and exact corrected source-byte SHA256. Constructor deployment only is verified; full multi-wallet custody transfer is not claimed live.
