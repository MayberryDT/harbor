# Harbor fork

ID: `io.zet.harbor`. Hosted bar widget, singleton Service and existing native
helper. Forked from OmaQ; no new dependencies or third-party services.

Protocol 17 identifies the expanded helper. Harbor clients refuse the older
helper rather than displaying new branding around old limits.

## Limits and transport

64 KiB UTF-8 text input, 1 GiB streamed file transfers, 64 MiB encoded inline
image input. Inline images allow 8192 pixels per side and 128 MiB decoded RGBA; avatars
retain 4096 pixels per side, 16 MiB decoded RGBA and 512 KiB encoded bounds. IPC JSON, event escaping, send queues, history lines, edits and searches
must all accommodate the larger text. Paths and invite payloads remain 511 bytes.

HB1 fragments are hex-encoded ASCII to avoid cutting a UTF-8 character across
Tox messages. Direct payloads are fragmented after Signal encryption and only
passed to decryption after complete reassembly. Group messages use the existing
Tox encrypted group transport. Each envelope has a random 128-bit ID, total size,
and byte offset. Assemblies are bound to stable direct keys or group+member keys,
require contiguous offsets and expire after five minutes without progress.
Sixteen incoming and outgoing slots bound memory; four fragments per pump keep
Tox iteration responsive. Sender queues respect per-destination ordering and
retry backpressure; accepted sends remain queued during an outage and restart
from byte zero after an idle timeout. Queued is not delivered. Receipts retain their existing meaning.

Expanded payloads require Harbor at both ends. Compatibility negotiation and
cross-restart transport queue persistence are deferred; an old peer cannot
reassemble HB1. Existing small frames and private state stay compatible.

## Verification

`tests/harbor-e2e.py` enumerates failure paths and uses fresh native helper peers
through real TCP relays. The durable receipt records byte sizes and hashes, not
private state or message content. Verification status is recorded at delivery.

## Verified candidate — 23 October 2026

The frozen helper SHA-256 is
`c14471452ca93de0f3b4ee24cb6dfea4f7e2d21689e7ea205f2d94df4b38738d`.
The real-network test passed 64 KiB Unicode direct/history/edit/search/group
messages, oversized rejection, pending-send shutdown protection, a 12 MiB binary
file with exact SHA-256 equality, and a 3840×2160 PNG (~24 MiB) with independently
decoded pixel equality. The 1 GiB file cap is configured; this run transferred
12 MiB, not a full 1 GiB file. Repeat with `tests/harbor-e2e.py` and a built helper.

Receipt and helper are retained on Halla under
`/home/halla/build/harbor/20261023/`. The E2E uses disposable identities and writes
only hashes/sizes to its receipt. Independent review addressed transport ordering,
shutdown, identity binding, CLI/link migration and plaintext-rendering boundaries.

The full native `make test` transcript-layout fixture hits tooltip TypeErrors
also reproduced against the unchanged installed upstream plugin. Its layout
assertions report success but its warning gate fails. This is a host/upstream
baseline limit, not a passing full native suite or live desktop verification.

At the original pre-activation checkpoint, source was prepared in `/home/tyler/Work/harbor`; it had not
been committed, pushed, or activated. Local activation is recorded below.
Publishing remains subject to the repository confirmation requirements.

## Local activation — 23 October 2026

The tested helper above is running in Harbor on Veelox. OmaQ acknowledged a
guarded shutdown before Harbor started. The existing profile projected 2 contacts;
no private identity or history was copied. This confirms local activation, not
a fresh end-to-end message exchange with those contacts.
