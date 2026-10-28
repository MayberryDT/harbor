# Harbor 2 implementation and acceptance ledger

Authorized: the complete redesign and Harbor identity, 24 October 2026.
Source baseline: `/home/halla/build/harbor/harbor2-20261024/baseline`.
This ledger records work in progress, not a release claim.

## Invite boundary: failure cases before implementation

- An old invite must still require its issuer's decision.
- An explicit bearer invite grants one claimant permission, never an unlimited
  list of contacts. Issuing it must disclose that anyone holding it may connect.
- Missing/incorrect token, expired token, missing Ratchet key and subsequent
  claimants must not bypass the established validation.
- A failed acceptance must not loop or add a contact without its durable pin.
- Group invitations retain their existing authorization path.
- Restart must invalidate ephemeral permission together with its issued token.
- An older helper must never receive a request the UI describes as automatic.
- Revocation/replacement must clear permission along with the token.
- Acceptance runs outside Tox's callback, through the same helper gates and
  journaled contact acceptance as an explicit decision.

Acceptance: real helpers create/redeem a bearer link, exchange encrypted
messages, reject reuse; a separate legacy link still emits a pending request.
Retain a receipt with executable hash and assertions, never private state.

## Brand compatibility: failure cases before implementation

- Newly shared links should say Harbor; existing `omaq://` links must parse.
- Internal legacy group wire messages must remain parseable by older peers.
- A CLI must accept both schemes without rewriting recipient key material.
- Environment aliases must never make the helper and its UI use different data
  directories. Existing paths remain authoritative until transactional migration.

## Implemented, awaiting complete delivery acceptance

- Full-width searchable direct/group conversation list, Add and Settings routes.
- Built-in Qt choosers for attachments, avatars, sounds and identity bundles.
- Filename attachment card; one Download action on incoming offers.
- Details contains popup/mute controls. Quiet focused-chat messages, burst sound
  coalescing, Test sound and playback errors. First-map rules retain focus.
- Helper-owned explicit bearer invites, advertised capability and issued policy.
  Legacy approval remains. Review corrected group-busy deferral and policy UI.
- Harbor anchor SVG/wordmark/favicon; T3 favicon registered. New user-facing
  invite links use harbor://; parser still accepts omaq://. Internal group wire
  formatting retains the legacy scheme.

Halla build/helper-hardening, arch and no-signal-build passed before the link
scheme change. QML plaintext gate, panel request source policy, direct invite
binding and surface-owner checks passed before the final attachment cleanup.
Repeat final checks after subsequent edits.

Native helper receipts: `bearer-receipt.json` and `bearer-reviewed-receipt.json`
under the Harbor2 Halla build directory prove first-claim acceptance, encrypted
message delivery, token clear and preserved legacy approval. They predate the
Harbor link scheme change and do not prove the group-busy race or token reuse.

Native task `task_3503310122744b0eb0ca5ef7e623fc9f` on Dell Optiplex:
conversation panel rendered (r128); file popup retained background focus (r130);
chooser and filename card observed (r133–138), Change and Escape/Ctrl+O reopen
(r139–140). Panel real input was refused by ibara's foreground-grab guard;
not counted as passed. Source-only fixture lacks installed Material Symbols,
so icon fallback is visible. No live Harbor identity or plugin was changed.

## Remaining scope

Request queue, full person projection in QML, group/attachment sync, optional mailbox client,
recovery and migration, call-device arbitration, remaining branding/path rename,
complete native journeys, final independent review and delivery remain open.

## Device management projection: failure cases before implementation

- UI must not decode signed roster bytes or infer authorization from a name.
- A stale result from another request/identity must not replace the displayed list.
- Revocation must target the displayed signing key and require scoped consent.
- Unsupported helpers must not present management as usable.
- Partial/malformed device lists must retain the last complete projection.
- Busy, denied, expired and failed operations must release UI pending state.

## Device screen and link continuation

The helper now returns a complete device-name/key/current/active projection;
Service validates it atomically and retains the last good list on malformed data.
Settings offers initialization, refresh and scoped revocation. The first native
management run passed 19 assertions (`device-management-receipt.json`).
Harbor-scheme bearer/legacy redemption passed (`harbor-invite-receipt.json`).

The linking screen can request a link through an already paired computer and
compare the helper's complete code on both ends. Review found initialization
could derail a pending link, incoming links were silent, and helper/shell restart
could lose the journey. Initialization is gated during linking; incoming requests
open Devices and play the configured sound; helper restart invalidates the old
UI; device.status replays live pending helper state with explicit direction.
The short-lived link-invitation bootstrap and first-launch creation are now
implemented; see later verification checkpoints. Person conversation integration
remains incomplete.

The pre-replay native link E2E passed, including restart before recipient consent
(`device-link-ui-backend-receipt.json`). A new real-helper replay assertion and
the broader existing suite are running; final results still need recording.
Notification mute now persists through shell settings. New Tox identities remain
unnamed for nickname setup. Harbor-named installer/update/uninstall entry points
preserve compatibility wrappers; internal data/runtime renaming remains open.

## Latest verification checkpoint

- `device-link-final-receipt.json`: native linking passes, including replay of
  pending challenges on both owner and unlinked target. Replay must run even
  when device.status reports device_not_linked. Sent→linked acknowledgement
  remains correlated to the same request/key.
- AK2 ibara task `task_ca063f1ad2534600bfa3476b12b89089`: native injected-event
  receipt has 14 checks, including device popup/player and completion. Final
  Panel layout observed at r6361 after hiding setup controls during linking.
  No transport/native-button interaction claim. Task finished with no windows.
- `make test` exposed the transport-disabled bearer-state compile issue (fixed).
  Root execution also invalidated a chmod-based permission assertion; the same
  binary passed unprivileged. Run this suite as uid 1000 in the SDK container.
- Float-rule regression expectations now include the additional noinitialfocus
  rule and chat_v7. `float-final.log` passes. Full unprivileged suite continuing.

## Conversation previews: failure cases before implementation

- Summary history requests must never consume a chat's history request or clear
  unread state. Match their own request, stable key and conversation.
- A late history summary must not overwrite a newer live message, edit or clear.
- Numeric contact reuse and identity replacement must not expose old previews.
- Deleted messages and cleared histories must not retain their text in the list.
- Files should show a short type label, never internal envelope/path data.
- Fetch histories one at a time; avoid a burst that blocks helper transport work.
- Keep row order fixed while the panel is open; refresh recency order on reopening.
- Missing/failed history leaves the normal contact status, not fabricated activity.

Conversation summaries now use separately correlated one-at-a-time history
requests. Live previews reject older timestamps, edits/deletions and clear update
the visible text, and opening snapshots recency order independently of search.
Readiness callbacks start the load if the panel opened during connection.
`native-preview-events-receipt.json` passes 19 injected native QML checks, including
summary/chat-history separation and stale-message/delete/clear behavior. Task
`task_50bd079beb954dc5bebd7ca29324b626` finished partial: ibara refused the Back
click because of the compositor grab, so the row-layout visual check remains open.
QML plaintext gate passed after these edits. The full CI-target run is in progress;
SDK lacks Quickshell, so `make test` cannot complete its native fixtures there.

## Link-invitation bootstrap: failure cases before implementation

- A new computer must not need manual friend pairing before device linking.
- Redemption used for linking must reject group invites before creating group
  membership and reject an already established device identity.
- Use the helper's correlated redeemed stable key, never the last contact or a
  QML-parsed token, to choose the linking peer.
- Wait for a ready encrypted session without presenting transient not-ready as
  a lost request; bound retries and do not bypass the two-device code consent.
- Existing-device link invitations are one-use bearer links with five-minute
  expiry. Issuing must disclose that possession allows contact setup, while
  joining the identity still requires explicit code confirmation.
- Identity/helper replacement invalidates pending bootstrap UI; wrong or expired
  links fail visibly without creating a replacement identity.

## First-launch creation: failure cases before implementation

- Start must create the personal identity before reporting nickname completion.
- Retrying after a partial setup must reuse the existing device/root authority.
- Failed or malformed device results must retain the entered nickname and report
  the failure; no nickname-success event may manufacture identity success.
- Linking and creating must be mutually exclusive; delayed replies must match
  the exact setup request and be discarded after helper/identity replacement.
- Profile edits for established users remain nickname edits, not identity resets.

The first-launch UI now initializes an idempotent personal identity, then saves
its nickname; stale/malformed/failed device results cannot complete setup. Review
found and fixed inconsistent active-device projection and the invite emission
scheme-prefix regression. Native task `task_acbacf67bda34742b2e033c516377fa4`
passed 27 injected-event checks; r174 showed the profile/device panel. A delayed
focus callback after window destruction was replaced by a window-owned timer;
the repeat had no TypeError/ReferenceError. Source fixture still lacks optional
bundled font/emoji assets, so this is not packaged appearance acceptance.
Receipt: `native-setup-events-receipt.json` on Halla. The final two literal invite
section headers were changed after the native run to satisfy the plain-text gate.

Phase2 now passes QR encode/decode, invite expiry/revoke, safety matching and
nospam behavior (`qr-phase2-final.log`, RSS 15304 KiB). Its waits now count actual
contact requests and observe correlated results instead of premature timer checks.

## Uninitialized replication failure case

Fresh/legacy users without a personal device roster must remain usable without
one replication-error event every second. Missing setup is an idle state; corrupt
or unreadable established storage must still fail visibly. Creating/linking later
must resume the existing journal initialization, without caching a permanent skip.

## One approval for device linking: failure cases before implementation

The new computer's explicit Link action is consent to join the identity behind
its authenticated invite peer. It must not need a second confirmation after the
owner approves. The owner still compares the complete code shown on both screens
and explicitly approves that named computer. Consent must bind the authenticated
peer, challenge root/head and exact proposed device keys. A missing/false request
accept flag retains the legacy manual-confirmation behavior. Neither a challenge
nor recipient consent alone authorizes a device; changed challenges, replay and
revoked bindings retain existing rejection. Automatic consent is helper-owned,
not a QML-generated cryptographic or authorization decision.

## Desktop fallback: failure cases before implementation

- A newly scheduled chat is not a failed popup; give native mapping time before
  considering the desktop notification fallback, avoiding duplicate alerts.
- Popup-off and explicit desktop-notification-off preferences still apply.
- Canceled file offers and changed/removed contact bindings cannot emit stale
  fallback notices. Identity change clears queued notices.
- Bound queued notification work and serialize notify-send processes. Report
  failed notification delivery visibly; never treat process start as delivery.
- Remove the separate right-side chat surface so it cannot duplicate the normal
  floating chat for old settings. Notification text remains generic/private.


## One-approval and setup evidence

`setup-receipt.json` passes real-helper first launch, validation, retry preserving
root/device keys, profile persistence after restart and visible corrupt-storage
failure. New unlinked installs no longer emit periodic replication errors.
`one-approval-receipt.json` passes the explicit initiating Link action plus a
single owner approval; `manual-approval-receipt.json` passes the legacy explicit
recipient consent path, owner restart, replay and revocation. Both use frozen
`candidate-one-approval`. Review found no concrete trust/correlation defect.

Fallback review found that canceling an offer could erase a pending message
notice, and a queued message could reopen a removed group. Queues now distinguish
message/file kind and revalidate authoritative group membership before effects.
Native fallback verification passed all 32 injected-event checks in a real
Quickshell fixture (`native-fallback-events-receipt.json`). Independent follow-up
review found no material defects in either fix. The notifier exited successfully,
but a desktop toast was not visually observed; visible fallback delivery remains
unverified. The malformed 1px PNG in the existing
RichText network probe was repaired; it previously caused a libpng failure rather
than testing only the text resource-fetch boundary. Full `make test-ci` passed
after these edits in the verification container with `--init`
(`final-test-ci.log`); native Quickshell and Omarchy fixtures are excluded there.

## Measured file journey

`tests/file-journey-e2e.py` passed two real TCP-relay transfers with frozen helper
`467b04a8050bf1cbeda110a54058c3cdfe1e184933f1205cdcae7d355970c66f`.
Each direction sent 1 MiB, waited for explicit download acceptance, verified the
actual `Downloads/Harbor` destination and compared SHA-256 at completion.
`file-journey-receipt.json` records offer latency of 0.348/0.284 seconds and
accept-to-completion of 28.615/16.929 seconds (0.035/0.059 MiB/s).
Both helpers ran on Halla through TCP relays; this is not a LAN benchmark.
First progress was observed after 0.486/0.348 seconds, not instrumented first-byte
arrival. Transfer throughput remains an open performance issue; no speedup is
claimed. Final verification-to-UI completion remains unmeasured.

The Phase6 real-helper file/call/audio journey passed after its IPC command bridge
was corrected to drain incoming events like a normal client. The prior bridge
could be evicted as a slow client during this long test. `phase6-drained.log`
records successful transported-audio, call teardown and remaining call lifecycle
checks with peak RSS 33528 KiB. Audio used isolated PipeWire/Pulse servers on Halla;
this does not prove physical speaker output or multi-device call arbitration.

## Chat opening repair after local installation

Tyler reported conversations would not open after the development installation.
Live diagnostics showed valid contacts and an explicit open queued while window
state was not hydrated. A shell restart allowed a real conversation to map on
Veelox. The initial surface-list request can be discarded by identity-reset queue
clearing; the owner now requests it again on handshake and identity-change ticks.
The fixed-height conversation list now computes height from count, avoiding the
observed contentHeight/card-height binding cycle.

Native fixture before the repair reproduced one queued open, no card and no
hydration. The updated fixture passes 34 checks, including handshake/identity
release into a visible chat, and ibara observed the mapped chat (task
`task_0ff6c798552347fcbdf6c7d8001d1e5a`, r260–261). Receipt:
`chat-open-receipt.json` under the Halla Harbor2 build directory. These scenarios
inject lifecycle ticks and responses, not actual transport handshakes. Ibara
refused a panel pointer action due to its foreground-grab guard; no mouse-input
pass is claimed. Independent review found no actionable issue; plaintext gate,
plugin validation and diff whitespace check passed.

Applied only Panel.qml and ChatSurface.qml to Veelox's live plugin and restarted
the shell. Temporary diagnostic IPC was removed. The helper remained PID4175800,
with the previously tested binary unchanged; private state was not copied.

## Settings simplification failure cases before implementation

Keep navigation bounded: one Settings home, five categories, Back returns home;
closing clears transient pages. Do not expose protocol setup as competing profiles.
Preparing device linking must retain the current profile and only open an invite
following the correlated initialization result; navigation/restart cancels that
continuation. Restore must validate the chosen file before a scoped confirmation;
cancel, stale validation and failures cannot replace identity. Legacy backup is
only tox.save, not chat history or full linked-profile recovery: label this limit.
Use readable setting rows rather than equally weighted outlined action buttons.

### Settings simplification — 24 October 2026

Installed Profile / Devices / Notifications / Appearance / Recovery navigation,
with Advanced subordinate. Settings home uses descriptive rows instead of a wall
of outlined action buttons. Add a computer lazily prepares an existing named
profile before opening the linking invitation. Sounds and message size live in
their respective settings pages; contact verification lives in conversation Details.

Restore now inspects the chosen backup before one scoped confirmation. Its
request-bound password survives inspection and is cleared on cancellation or
completion. Recovery explicitly describes the legacy connection-only backup:
it does not include chat history or linked-profile recovery. Safety verification
shows retry guidance after context replacement or an eight-second reply timeout.

Verification: 14 native QML injected-event journey checks passed, with receipt at
`/home/halla/build/harbor/harbor2-20261024/settings-receipt.json`; repeat using
`tests/friction-native.py` and `tests/settings-native-events.py`. Home and Recovery
rendering inspected on ibara task `task_aa9e600000df4c2db7d48c090ce0deb5`.
This does not prove transport, an actual protected-bundle helper restore, or
pointer-driven navigation. The fixture lacks the icon font. QML plaintext gate,
plugin validation and diff check passed; ChatSurface/Service qmllint returned 0
with warnings. Focused review found no remaining defect after password retention
and verification timeout repairs. Three QML files installed locally; helper PID
4175800 remained current and unchanged. No release or push performed.

## Attachment composer lock, 28 October 2026

Removed the conversation-wide attachment lock from text paste, file selection,
and image send. The Service keeps up to 16 additional outgoing attachments in
memory, in submission order per conversation, while the helper finishes the
active transfer. Other conversations can proceed independently. Stable contact
keys and helper compatibility are rechecked before dispatch. Cancel sends drops
that conversation's queue and cancels its active transfer; identity/helper resets
and contact removal discard queued stages. Files rejected by image inspection
send directly from the native chooser without the former extra Send action.
Incoming acceptance and helper transport validation remain unchanged.

Verification: Halla source snapshot at
`/home/halla/workspaces/harbor-attachment-check`; logs under
`/home/halla/build/harbor/attachment-composer-20261028`. QML lint and architecture
checks passed; lint reports the existing unresolved shell imports/unqualified
access warnings. Independent review identified FIFO, cancellation and global
capacity issues, corrected before the final checks. `git diff --check` passed.
The Halla SDK lacks Quickshell and Omarchy shell components, so native interaction,
clipboard/queue E2E and recipient transfer behavior remain unverified. No live
plugin synchronization, helper restart, commit or publication was performed.

### 1.3.2 delivery verification

Native Dell task `task_390665c129dd40efbcdf847c7eb46aa8` passed
`tests/chat-composer-parity.sh` and `tests/chat-input-scroll.sh`, plus a composer
variant replacing `function fileSendingFor(conv) { return false }` with
`function fileSendingFor(conv) { return true }`. The variant proves composer
image send and text paste remain available under an active-transfer projection;
it does not prove the Service queue's complete network transfer journey.
The disposable task workspace retains `composer.log`, `input.log`,
`busy-composer.log` and the candidate source. Native jobs ended successfully;
ibara finish confirmed cleanup. Source SHA-256 values:

- Service.qml: `ef6354998fe04d43829c3d367a87f3c877ea632cc626e7c071fea68eac9a046e`
- pages/ChatPage.qml: `779804b1cbfb99328786798f7879aa2cd49b48cc816e6593f1ed5b272b5c74d1`

An independent release review approved refreshing only these files' raw and
formatted plaintext-policy digests; existing sink/write allowlists are unchanged.
The initial root-run headless check was invalidated by permission-test behavior;
checks were rerun as Halla's unprivileged UID. A stray QML file introduced only
in the disposable snapshot was removed before the final source-policy check.
Release logs are under `/home/halla/build/harbor/attachment-release-20261028/source/`.

Live update: copied only Service.qml, pages/ChatPage.qml and manifest.json from
`/home/tyler/Work/harbor` to
`/home/tyler/.config/omarchy/plugins/io.zet.harbor`, after announcing the paths and
UI reload. Source/destination hashes match; manifest validation passed,
`rescanPlugins` completed and shell ping returned `ok`. The existing helper PID
3492 remained running. Public-source backup: `/tmp/harbor-132-before-fgoyvd87`.
No private state or helper binary was copied.

Final release checks: unprivileged Halla `make test-ci` passed, including the
plaintext gate, C/CLI suites, no-Signal build, install/update/uninstall and IPC
regression checks. The uninstall mount-boundary subcheck was skipped because a
user mount namespace is unavailable. `release-final.log` is the complete receipt.
The complete `make test` native suite and real queued multi-file relay E2E were
not run; native coverage is the three composer/input runs described above.
