# Harbor product specification

Agreed with Tyler, 23 October 2026. This specifies the next product, not current
capabilities. [Plan](IMPLEMENTATION_PLAN.md) owns delivery state and authority.

## Product and protected direction
Private Omarchy-native chat for small trusted circles: direct and group
conversations, attachments, existing direct audio calls, and one personal identity
usable concurrently on several machines. No phone number, public directory,
telemetry or mandatory hosted account. Preserve the existing QML/Quickshell
interface: quiet, compact, keyboard-first and following the active Omarchy theme.
The native helper owns encryption, transport, persistence and permissions.
[Message direction](../COPYWRITING.md) and [creative compass](../juice.md) explain
the intended experience. Existing layouts/tokens remain the visual baseline.

## Link and manage machines
On a new installation choose Create identity or Link existing identity. Linking
uses a short-lived, single-use invitation and explicit confirmation on an
already authorized machine. Show device names and a verification code on both
ends; wrong, expired, replayed or rejected requests cannot authorize a device.
The person remains one contact to everyone else. Each machine gets independent
transport and encryption keys and sessions; cloning Tox savedata or mutable
Ratchet sessions is forbidden. A durable authorized-device roster binds device
keys to the personal identity. Device additions/removals must be authenticated
and cannot silently change a contact's person identity.
Show linked devices and allow revocation from a surviving authorized machine.
Revocation prevents future delivery/key access after peers learn the change;
it cannot erase history or keys already held by a lost device. Stale/offline
rosters and conflicting updates must fail safely with visible recovery.
Existing contacts must migrate through authenticated proof or explicit identity
verification, never silent trust replacement. Legacy peers receive a clear
unsupported/upgrade state rather than dropped messages or plaintext fallback.

## Conversations everywhere
A linked machine receives existing contacts and available conversation history
through authenticated encrypted synchronization. Show progress and missing
history explicitly. Concurrent messages converge to one transcript with stable
message identifiers, deterministic ordering and duplicate suppression across
retries, reconnects and restarts. Sync sent and received messages, replies,
edits, deletions, reactions, read state and group membership/roles. A late event
must not resurrect deleted content or regress delivery/read state.
Typing/presence are ephemeral; drafts and window geometry may remain local.
An offline machine catches up on return. Attachment metadata synchronizes;
bytes download on demand with authenticated integrity, size bounds, explicit
acceptance and clear unavailable state when no retained copy exists.
Preserve existing payload bounds and streaming; do not buffer 1 GiB in memory.
Group membership represents people, not duplicate device members. Removing a
person/device must stop future authorized group access when the change is known.
Direct calls ring eligible online devices; answering on one stops ringing on
the others. One call endpoint owns microphone/audio; no recording or history
replay of media. Calls remain direct-only for this release.

## Optional encrypted mailbox
Harbor works without a mailbox when peers holding required data overlap online.
Users may configure a self-hosted mailbox for asynchronous delivery and catch-up
when their machines never overlap online. It stores encrypted envelopes and
cannot decrypt conversation or attachment contents. Device authentication,
revocation, replay protection, bounded retention/storage and retry behavior
must be enforced. Display mailbox availability and queued versus delivered state.
An outage cannot lose an accepted durable message or falsely mark it delivered.
Document what traffic metadata the operator can observe; encrypted contents do
not imply metadata anonymity. No mandatory Harbor-operated service, public
mailbox deployment, hosting purchase or account creation is authorized here.

## Recovery
Offer an encrypted recovery backup of personal identity, contacts, backed-up
conversations and the state needed for safe restoration. Show backup date,
covered history and attachment coverage before export and before restore.
Never imply unbacked-up messages/files can be recovered. Wrong passwords,
corruption, disk-full and interrupted restore leave the previous identity intact.
Recovery onto a new device must create fresh device/session state, supersede lost
devices and prevent replay/rollback of old authorization. Never restore a live
Ratchet session by copying it onto a concurrent machine. Explain any required
peer verification after all-device loss. Lost backup and secret are unrecoverable;
there is no operator bypass. Backups and link secrets never enter source sync.

## Security and acceptance
Keep direct communication encrypted with authenticated per-device sessions and
no plaintext fallback. Keep TCP-relay privacy mode; do not expose contacts' IPs
through UDP discovery or hole punching. Retain existing local plaintext-at-rest
limitations until explicitly changed; do not imply the entire local store is
encrypted by the identity passphrase. Do not invent cryptographic primitives.

Delivery requires native E2E with two people and at least two devices each:
concurrent sends and restart convergence; link expiry/replay/rejection;
revocation including offline stale devices; new-device history; groups and roles;
attachment hashes and unavailable bytes; mailbox outage/duplicate delivery and
non-overlapping online windows; recovery after all devices are lost; corrupt and
stale backups; call answer arbitration and audio cleanup. Inject interrupted
writes and insufficient disk where persistence is promised. Enumerate failures
before isolated implementation. Retain a repeatable runner, candidate hashes,
commands and sanitized receipts under Halla build output. A real Omarchy UI
walkthrough must verify keyboard navigation, theme changes, focus, sync/error
states and multiple windows. Independent review is required before delivery.

## First engineering decision
Validate the smallest complete multi-device exchange before broad UI work.
Existing Tox groups, device roster trust, mailbox persistence and legacy contact
migration need explicit protocol design and threat review; this specification
does not claim those mechanisms already work. Start from Tox's warning about
concurrent cloned profiles and Signal Sesame's per-device session model:
https://wiki.tox.chat/users/faq
https://signal.org/docs/specifications/sesame/
No mobile clients, non-Omarchy support, public discovery, group calls or bespoke
cryptography are required for this release.
