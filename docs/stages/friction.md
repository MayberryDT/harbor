# Everyday usability — 24 October 2026

Tyler asked for less friction across identity, adding friends, files, alerts and
the panel. The first patch fixes observed interaction failures; it does not
claim that multi-device support or faster transport has shipped.

## First patch

- Incoming file offers use the existing conversation popup and sound path.
  Respect explicit popup/mute preferences; wait for preferences at startup,
  reject wrong-contact events, and discard canceled/replaced queued offers.
  Retire file notification dedupe on terminal events because Tox reuses IDs.
- Incoming invitations open the request panel and play the configured sound
  from the single surface owner.
- The paperclip and Ctrl+O open Qt's built-in FileDialog. No zenity, kdialog or
  yad dependency, and no mandatory absolute-path entry. Cancel/reopen is one
  action. Selection remains bound to the conversation and stable contact key.
- Remove GitHub and Ko-fi actions; use the full profile/request header width
  while preserving the independent lower-left menu and action-rail widths.

No transfer auto-accept, encryption, contact trust, destructive confirmation,
helper protocol, or live private-state changes are included. These edits are
uncommitted and have not been copied to the live plugin.

## Remaining product work

1. **One Add friend journey.** Put sharing an invitation and using a received
   invitation in one place. Target one clear consent moment, followed by the
   conversation opening. Treat creating/sharing an invite as sender intent,
   rather than making both people complete repeated approvals. This needs an
   explicit protocol design for intended-recipient binding versus a single-use
   bearer link; never silently bypass the existing trust checks in QML.
   Keep safety-code comparison available and emphasize actual identity changes.
2. **One person, several devices.** Setup offers Create identity or Link this
   device. Show device name and matching code, approve once on an existing
   device, then synchronize contacts/history. Device management and recovery
   belong in settings. Export/import is not simultaneous-device linking.
   The specification owns the security and recovery contract; the experimental
   source remains separate from the released helper until complete E2E passes.
3. **Files that explain their state.** One chooser or drop/paste, one Send,
   one recipient download decision. Show waiting for acceptance separately
   from transferring, with byte progress and recoverable failures. Measure
   offer latency, acceptance latency, throughput and completion independently
   on real peers before promising speed improvements. Do not weaken relay
   privacy to disguise a performance issue.
4. **Conversation-first panel.** Primary actions are conversations, Add friend,
   and Settings. Move identity maintenance, backups, verification and destructive
   tools out of the main action rail. Make popup/sound state legible together;
   avoid the current proliferation of notification controls. Preserve explicit
   user mute/popup choices. Check the resulting layout with keyboard input,
   narrow windows, multiple monitors and more than five contacts.

## Verification

Candidate evidence: `/home/halla/build/harbor/friction-20261024/`.
`checks-final.log`: plaintext adversarial policy, surface-owner gate,
direct-invite-fingerprint gate and `make arch` passed. Plugin manifest validation
and `git diff --check` passed. Independent review found transfer-ID reuse,
picker cancellation and menu-width issues; all were fixed and rereviewed with
no remaining concrete blockers.

Native task: `task_c6be233bbed444ec868848074656c7bb`, BMAX B4 Plus.
`native-receipt.json` records eleven checks, including readiness, with final
source hashes. The repeatable runners are `tests/friction-native.py` and
`tests/friction-native-events.py`. This is the actual QML/Service event path with
helper events injected and private-helper startup disabled, not a network E2E.

Native observations: file popup r3020; full-width invitation panel without
promotional controls r3031; paperclip opens dialog r3033; Escape then Ctrl+O
reopens r3034; selecting `notes #1.txt` preserves the path r3036. The real
notification player exits zero; the machine has dummy audio output, so physical
speaker audibility is unproven. Installer-provided icon font/emoji assets were
absent from this source-only fixture. No physical user machine was modified.

The geometry regression passed on BMAX (`geometry.log`); its first Halla run
could not launch Quickshell. Panel source assertions passed on Halla, with its
native portion explicitly skipped there. The full helper/network suite was not
rerun for this QML-only patch. No new transfer-speed or multi-device claims.
