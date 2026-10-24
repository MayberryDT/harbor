# Multi-device implementation boundaries

Read [the living plan](IMPLEMENTATION_PLAN.md) for authority and current order.
[The specification](SPECIFICATION.md) remains the product contract.

## Trust foundation
`helper/devices.c` implements a bounded signed authorization chain. Person root,
per-device Ed25519 signing key, Tox transport key and Signal identity key are
separate. Root recovery authority stays on the initializing machine and is never
copied by linking. Versioned records sign a domain, person root, sequence,
predecessor SHA-256 and complete device binding. Version 2 also requires the
subject device’s Ed25519 consent over `Harbor-device-consent-v2` (including NUL),
root32 and the Ed/Tox/Signal tuple96. The distinct genesis root signature does
not substitute for subject consent. Proofless version 1 is not accepted. Records are canonical fixed
binary fields; names are bounded strict UTF-8. Currently at most 32 historical
devices and 64 authorization records are supported; revoked keys cannot rejoin.
A competing valid same-root chain becomes a durable conflict that blocks this
layer. No highest-sequence or arrival-order winner is selected.

Private files use owner-only modes, no-follow reads and durable creation.
Initialization retains its exact signed initial record and a committed marker;
missing established rosters require explicit repair rather than a new genesis.
`device.*` IPC exposes public proposals/rosters and requires explicit acceptance
for authorization, adoption and revocation. These are engineering operations;
they do not yet constitute the finished native device-management interface.

`helper/device_link.c` carries HD1 control frames inside existing pinned Signal
sessions. Both Tox and Signal keys must match the authenticated peer. The displayed
code binds root, shown roster head, request and both device proposals. Activation
requires consent at both ends. Accepted authorization is durable before delivery;
restart resumes an exact active binding with fresh consent. Retries recheck the
current roster and cannot resend a revoked authorization. Signed same-root roster
extensions may propagate without approving a different person identity.

## Foreign endpoint endorsement
Signed foreign rosters propose endpoints; they cannot reserve another contact’s
keys or install pins. `endpoint-anchors/<Tox key>` stores an exact root/Ed/Tox/
Signal binding only after direct endorsement. Legacy experimental `people/.key`
anchors are not reused. Sibling contact imports contain metadata, not endpoint
endorsements. All foreign peer authorization and application fanout consult the
exact endorsed binding. Unverified destinations remain visible to the engine as
blocked pending obligations.

`helper/endpoint.c` obtains a fresh response from each proposed physical Tox
peer. HPE2 is a narrow public identity-metadata exchange inside Tox’s authenticated
encryption, before Signal bootstrap. It never carries application data. The
nonce is 16 random bytes represented by 32 lowercase hexadecimal characters.
The response signs `Harbor-endpoint-endorsement-v2` including NUL, nonce16,
root32 and tuple96 using that device’s Ed25519 key. The responder requires its
current local active root and exact tuple. The recipient checks its current,
non-conflicting contact roster immediately before recording the anchor.
The exact Signal identity is pinned during promotion; no Tox private-key signing
was introduced. A stored Signal session created from a public bundle alone does
not prove the peer possesses that identity's private key. Fresh authenticated
confirmation is still required before treating bootstrap as possession proof.

Reciprocal roster/contact synchronization supplies both ends with rendezvous
metadata. A private probe intent precedes saving any provisional Tox friendship;
these friendships have no Signal pin, ordinary contact projection or application
access. Probe identities hash the root and full tuple; a false claim cannot
reserve a legitimate claim’s physical endpoint. Transport ownership is shared
across competing proposals for cleanup, and a verified explicit invitation may
take over a provisional friendship through the ordinary durable add intent. Promotion records the endpoint anchor before installing and synchronizing
the pin, and retries incomplete promotion after restart. Anchor publication uses
a fsynced hidden staging file and atomic no-replace rename. Metadata reads finish
both file and directory fsync before reporting success, so a readable result of
a failed commit cannot authorize a pin or discard its recovery intent. Cleanup re-resolves the
Tox key and preserves independently pinned or own-device use. There are at most
64 probe records, four active per person, a five-minute deadline, five-second
retries and an hour cooldown after failure. Advertisements do not renew leases.
Tox friendship exposes transport presence/profile metadata during the bounded
probe. This lifecycle is undergoing native E2E and independent review.

Explicit invitations work in both directions while probes exist. Redeeming a
verified invitation can replace only an owned unpinned provisional friendship.
If the inviter already has a provisional friendship, toxcore may suppress the
native friend request. HPI2 then returns the active invitation ID and recipient
Signal key through the exact authenticated Tox channel. It enters the existing
pending-invitation/UI-confirmation path; it cannot install a pin by itself.
A private bounded rendezvous debt precedes the recipient’s native add and retries
until ordinary pinned Signal bootstrap completes or the invitation expires.

## Replication foundation
`helper/device_sync.c` replicates immutable events among authorized devices of
one person. It currently exposes `sync.publish`, `sync.list` and `sync.status`;
person-addressed direct sends and history project from this journal; UI and
remaining chat operations are not wired to it yet.
HSX1 wraps a per-device Signal ciphertext; the inner HS2 event binds a stable
128-bit ID, Lamport counter, person root, original device label, conversation key
and body. HM2 direct-message IDs bind the complete immutable event: first 128
bits of SHA-256 over `Harbor-event-v1|clock16|person64|author64|conversation|kind`,
LF and the exact body, without a terminating NUL. A foreign sender cannot reserve
another person’s event slot or reuse an ID for different clock/content. Device-local
request lookup preserves exact retries without regenerating their timestamp or
clock. HM2 bodies omit an inner self-referential ID. Clock ownership uses the person root rather than a device label that
a foreign roster could claim. Foreign events claiming an own-device label are
rejected before journaling.
HSA1 acknowledgements are authenticated Signal messages. Events copied by a
currently authorized sibling have that sibling as synchronization provenance;
this is not independent proof of an original remote message signature.

Accepted local events are durable before success. Each recipient's encrypted
outbox is durable before network submission and retries the same ciphertext.
The Signal pre-decryption-commit callback persists authenticated inbox plaintext
before session advancement. A duplicate ciphertext can recover from that cache,
including after process restart, and is acknowledged only after its replica event
is durable. ACK debt is persisted before removing the encrypted outbox.
Contact projection failure withholds acknowledgement, including on retries of
already journaled contact events. A verified older roster prefix is already
projected when a newer roster is present; replay never replaces the newer state
or treats that safe supersession as a storage failure.
New authenticated sessions discard only old encrypted envelopes; logical events
remain for safe re-enveloping under the same event ID.

`helper/journal.c` now owns immutable events in SQLite WAL with FULL synchronous
commits, a person owner, verified schema version and a durable existence marker.
A transactional verified legacy import precedes ready state; retained prototype
event files become read-only. Missing, corrupt, unsafe and wrong-owner stores
fail closed. Reopening completes a write barrier before readable events can
authorize acknowledgements. Signed roster/endpoint checks remain in the helper;
the storage library does not replace application authorization. See SQLite's
[atomic commit](https://www.sqlite.org/atomiccommit.html),
[durability settings](https://www.sqlite.org/pragma.html#pragma_synchronous) and
[C open API](https://www.sqlite.org/c3ref/open.html).

Request/conversation indexes replace journal scans for retry lookup and history
selection. Pending-work insertion is atomic with each event. Bounded fair batches
interleave new events and older obligations; offline and unendorsed destinations
retain debt. Verified own/contact roster head changes requeue affected events.
Projection debt is distinct from delivery scheduling: contact metadata selects
the longest applicable roster and then canonical event order, so an old retry
cannot overwrite a newer name. Startup reconciles installed contact cards into
deterministic sibling intent. Authenticated HP1 updates now preflight admission,
commit the complete card to the journal before cache installation, then endorse
the exact source endpoint. The two card files are projections, not competing
publication authority.

Schema v3 additionally imports ciphertext outbox, authenticated inbox, ACK and
rekey ledgers into `envelopes(bucket,name,body)` in one transaction. `ledger_ready`
commits sole authority before retained source directories are sealed read-only;
unsafe inputs fail closed without partial activation. Inbox commit remains before
Signal advancement; outbox ciphertext is exact and durable before send; ACKs
precede outbox removal; rekey removal of old ciphertext and its intent is atomic.
Queue results commit separately after durable envelope effects. This removes the
file engine's lifetime count ceiling. Initial replication and native queued-byte
migration pass, while crash/rekey/I/O and independent acceptance remain pending.
These details are not complete product acceptance.

The prototype's 4096-event cap is removed from the authoritative journal and
person history model; the native >4096-event/framing journey is still running.
Backlog counts represent logical pending events, including unavailable recipients.
Event order uses Lamport counter, original device label and ID; local wall clocks
are not a convergence authority. Existing local plaintext-at-rest limitations
also apply to the replica journal and authenticated inbox cache.

## Person actions under verification
Person conversations use `p:<root>`. HA1 events have kinds `edit`, `delete`,
`reaction` and `read`, and exact body
`HA1|actorRoot|targetRoot|originalRoot|messageId|requestId\n<payload>`.
The canonical immutable event ID covers the kind and complete body as well as
its actor/device/conversation/clock. Edits and deletions require the original
person; reactions have one current value per person. A read marker names a
message from the other person and covers that person's preceding messages in
the converged order. Request retries from one device reuse the original event
and clock; a conflicting request payload fails.

Projection first collects messages, then applies ordered actions, so an action
received before its message survives catch-up. Deletion is permanent in the
projection and suppresses text even after a later edit. It does not erase copies
or immutable journal bytes already held by another device. Read state takes
precedence over later delivery ACKs. Native four-helper acceptance and independent
review are still running; presentation integration remains outstanding.

Legacy pins authenticate keys but do not override learned membership. Business
ingress/egress, file chunks and avatar sends require current authorization.
Stable physical-key validation still permits local history, search, clearing,
surface settings, file status/cancellation and call termination after revocation.
Identity metadata has its own narrow authorization path so revocation updates
can reach a revoked recipient. Call audio authorization is checked before
playback/pumping; real audio acceptance remains pending.

## Remaining application integration
Map people to device rosters separately from the existing `d:<Tox-key>` session
namespace. Preserve the latter as per-device encryption/storage bindings. Connect
contacts, direct messages, edits, deletions, receipts, attachments and existing
history to the replica layer; retain clear compatibility and migration states.

New multi-device groups need authenticated person membership and encrypted
per-device fanout. Native Tox NGC counts devices as members and cannot by itself
represent person roles or revoke a device's group keys. Preserve old native groups
until an explicit, safe migration is available; never hide duplicates and claim
revocation is solved. Calls need device-wide ring/answer arbitration.

The optional encrypted mailbox, offline authenticated prekeys, encrypted recovery
backup/restore, native UI and complete product acceptance remain implementation
work. No deployment or live identity import has occurred.

## Offline endpoint bootstrap — proposed, not implemented
HPE2 relies on a live authenticated Tox channel. Mailbox-only discovery needs a
separate possession exchange before the exact endpoint anchor can authorize any
Signal destination. An issuer's forwarded claim remains insufficient.

The candidate uses libsodium sealed boxes to the device's existing Tox X25519
public key, carrying a fresh 32-byte nonce and exact requester/recipient person,
Ed25519, Tox and Signal tuples. The expected device responds only for its own
current active tuple and signs the request-bound response with its device Ed key.
Each receiver verifies its own challenge; the other side needs an independent
challenge too. A query alone never endorses its sender. A combined three-message
exchange may carry the reciprocal challenge in the first response. Responses
are sealed to their intended requester; no application plaintext is carried.

This is a design inference, not a security proof. Libsodium documents sealed
boxes as anonymous encryption: they do not authenticate the sender. Device
signatures, fresh pending nonces, current roster/tuple checks and reciprocal
possession are therefore required separately. Current OQB2 responses cache request hashes locally but do not carry a fresh
request binding on the wire, and session creation from a public bundle is not
possession proof. The mailbox path must authenticate the ordered bootstrap ID,
exact request/response bundles and endpoint-exchange transcript, then exchange
fresh control messages inside that Signal session before application activation.
Endpoint endorsement, session creation and Signal confirmation are distinct. Persist exchange and
promotion debts before effects, bound admission/retry/expiry, reject stale/forked
rosters, and preserve the online probe's ownership/cleanup invariants. Do not
activate this route until independent design review and native adversarial E2E.
Canonical transcript bytes, mailbox capability propagation and lifecycle details
remain to be resolved before implementation.

Primary references inspected 23 October 2026: libsodium 1.0.22 in the retained SDK
exports `crypto_box_seal`/`crypto_box_seal_open`; see its
[sealed-box construction and authentication limits](https://doc.libsodium.org/public-key_cryptography/sealed_boxes).
Tox 0.2.23 uses a 32-byte random secret and libsodium X25519 base multiplication
for transport keys; see [the exact key generator](https://github.com/TokTok/c-toxcore/blob/v0.2.23/toxcore/crypto_core.c).
The installed Tox API exposes `tox_self_get_secret_key`; any adapter must keep
that key internal, check the derived public key, and erase temporary key copies.
This does not authorize exporting a Tox secret or signing with it.

The independent offline-design review conditionally retains this direction but
requires the canonical three-message transcript to bind M2 to M1 and M3 to M2,
separate secret nonces/request IDs/roles/deadlines and both current-known heads.
It also requires durable exact-ciphertext retries, two-way writer capabilities,
expiry limits, key validation and the Signal confirmation above. Its report is
`/home/halla/build/harbor/implementation-20261023/review-offline-endpoint-design.md`.
This is a conditional design verdict, not implementation or complete-composition
security proof. Ordinary public-bundle parsing must not be relabelled confirmation.
