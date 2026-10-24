# Harbor redesign map

24 October 2026 · Approved experience and delivery map; implementation in progress.
Requested by Tyler after daily-use friction with identity, friends, files and
notifications. Tyler authorized implementation together with a Harbor rebrand. This map
preserves the protected requirements in SPECIFICATION.md; implementation status
and verification are recorded in stages/harbor2.md.

## 1. The product people should experience

Open Harbor, find a person, talk. Move to another computer and remain the same
person. Sending a screenshot should feel as ordinary as sending a sentence.
When something needs attention, Harbor shows it and makes the configured sound.

Keep the native Omarchy appearance: existing tokens, compact dimensions,
theme colors and Material Symbols. The approved Harbor identity adds an anchor
mark and consistent product naming. No dashboard or hosted account service. Use one personal profile across linked computers. Do not add an account
switcher, public directory, email login or phone-number signup in this redesign.

Rules for every screen:

- Show the next useful action, not the internal protocol operation.
- One action expresses intent. Do not ask someone to confirm the same intent again.
- Preserve drafts, selected files and navigation through recoverable errors.
- Put progress and failures beside the thing they affect. No unexplained red borders.
- Make security automatic until an actual trust decision is required.
- Popup and sound defaults work out of the box; existing explicit preferences survive updates.
- Never present planned sync, delivery, backup coverage or recovery as completed.

## 2. Screen map and navigation

```text
Bar icon → Harbor panel
           ├─ Conversation list → Chat window
           │                      ├─ Search this chat
           │                      ├─ Attachments / image viewer
           │                      ├─ Direct call
           │                      └─ Conversation details
           │                         ├─ Notifications
           │                         ├─ Shared files
           │                         ├─ Verify contact
           │                         └─ Contact/group actions
           ├─ Add → Add friend / New group
           ├─ Requests → One card per pending request
           └─ Settings
              ├─ Your profile
              ├─ Devices
              ├─ Notifications
              ├─ Appearance
              ├─ Backups & recovery
              └─ Advanced → Connection / Storage / Diagnostics / About

First launch → Start using Harbor / Link this device
               └─ Restore from backup (secondary recovery path)
```

**Panel:** retain the compact 400-pixel baseline. Header: avatar, nickname,
connection status, Add and Settings. Below: find a conversation, request count
when nonzero, and one scrollable list of direct and group conversations. Each
row has avatar, name, short last-message/activity preview, time and unread
indicator. Groups have a clear group icon; no permanent Friends/Groups modes.
Sort by recent activity, with unread marking; do not reorder a row under the
pointer or keyboard selection. Search names locally; message search remains
inside its chat. Empty state: “Start a conversation” with “Add friend”.

Clicking a row opens or raises that conversation. Separate windows remain the
default. Existing per-chat geometry survives. A single-window/bundled preference
can stay in Appearance, but must not become an additional primary navigation mode.

**Requests:** an incoming request raises a compact request surface containing
the person/group, context and two labelled actions. Multiple requests form a
bounded queue, not a single property that silently replaces the previous request.
Dismissal hides the surface, not the request. Requests remain reachable in the panel.

**Remove the action rail.** No main-screen Demo, Theme, Sounds, Safety code,
Identity, Danger zone, Open chat picker, GitHub or Ko-fi. GitHub may be a plain
project link under About; donation controls are removed from the app. Keep license
and attribution information in About. Demo becomes an optional About entry for
development, never part of everyday navigation.

## 3. First use, profile and recovery

### New person

Start using Harbor → nickname → Continue → conversation list.
The nickname is the only required profile field; avatar is optional. Preserve
the existing 1–18 Unicode-character limit and explain invalid input inline.
Show “Connecting…” without preventing profile editing. If identity creation
fails, retain the name and give Retry with a concrete reason.

After setup, show one dismissible prompt to create an encrypted recovery backup.
Do not block the first conversation on choosing a password or exporting a file.
If dismissed, keep the backup status in Settings; do not repeatedly nag.

### Existing person on another machine

Link this device → obtain a short-lived QR/link from Settings → Devices on an
existing device → enter/open it on the new device → name this device → compare
matching codes → approve once on the existing device → conversations appear.

The new-device submission is its consent; do not add another final confirmation
after the existing device approves. Both screens identify the other device.
Do not invent a short guessable authentication code; the QR/link carries the
authenticated linking material, and the displayed comparison code verifies it.

After approval: “Connected · Syncing conversations…” with useful progress if
measurable. New messaging becomes available once authorization and the required
current contact/session state are ready; bulk history may continue in the
background. Show unavailable older history explicitly. Cancel before activation
discards a pending link; removing an already activated device uses Devices.

### Devices and backups

Devices lists this device, other device names, last seen, sync status, and
Add device. Removing a device has one scoped confirmation: it stops future
access after revocation reaches peers, but cannot erase data already held there.
Popup and sound preferences belong to each device; conversation-level overrides
can synchronize with clear local overrides. Nickname/avatar belong to the person.

Backups shows last successful backup, included history and attachment coverage,
Create backup, and Restore. Restore validates and previews the backup date and
scope before one replacement confirmation. Wrong password, corrupt file,
insufficient disk or interrupted restore must preserve the current identity.
Successful recovery creates fresh device/session state, never a concurrent clone.
With no surviving device, backup or secret, explain the actual recovery limit.

## 4. Add friend without the two-sided ceremony

One Add friend screen contains:

- **Share an invite:** Copy link and Show QR.
- **Use an invite:** one paste field, also reached by opening a Harbor invite link.

Recommended normal journey:

1. Alice deliberately creates a single-use invite and sends it to Bob.
2. Bob opens it, sees Alice's profile and presses **Add Alice**.
3. Both get one conversation; Bob's opens immediately, Alice gets a new-contact
   popup. No further “redeem / compare / accept on the other computer” sequence.

Creating the shareable invite grants its holder permission to connect. This is
an intentional change from today's sender-side acceptance rule: a forwarded or
intercepted invite could connect the wrong holder. Display a short explanation
next to sharing: “Anyone with this link can add you once. Send it privately.”
Use short-lived, single-use links, bind activation atomically, and show the
connected person immediately. Exact validity duration must be chosen with the
helper contract; do not invent a timer the helper does not enforce.

Keep **Require my approval** as an advanced invite option for people who need
it, not the everyday default. In that mode Alice approves one visible request.
This is a proposed trust-policy change and requires protocol implementation and
review; never emulate approval in QML or silently change already-issued links.

Safety-code comparison lives in conversation details. Do not require manual code
comparison for every normal contact addition. A changed identity, unexpected
recipient, conflicting link claim or unprovable migration gets a specific trust
decision; no silent reassignment of an existing contact's trusted identity.

Expired link: “This invite expired. Ask Alice for a new link.” Used link:
“This invite has already been used.” Already friends: open the existing chat.
Offline inviter: show a pending connection and retain the attempt; do not claim
success. Without asynchronous transport, explain that the inviter must be online.
Do not force a safety-code ceremony just to recover a transient network failure.

## 5. Chat window

Header: avatar, person name with adjacent status, Call for direct chats, Search,
and Details. Normal window chrome owns closing. Put Pin/keep-open and per-chat
notification choices in Details; remove the row of Auto-off/Auto-open/Mute labels.
When muted or popups are disabled, show a compact, accessible state indicator.

Transcript: readable messages, stable timestamps and delivery indicators. Preserve
selection, reply, edit, reactions, copy, search and local history. Put common
actions on hover and keyboard focus; keep secondary actions in the existing
styled context menu. Do not show transport keys or per-device copies as contacts.

Composer: paperclip, expanding input, emoji, Send. Enter sends; Shift+Enter adds
a line. Formatting is optional and stays on one horizontally scrollable row.
Pasted text works while reconnecting. A confirmed image paste or dropped file
creates an attachment card in the composer. Selecting a file never sends it
without the user's Send action. Attachment cards show thumbnail/type, name,
size, Remove and useful errors. Hide the absolute-path editor from normal use;
Copy full path remains in file details.

Keep the first release to one attachment at a time unless the helper supports
and verifies a queue; do not advertise unsupported multi-file sending. Preserve
drafts when opening details/search, receiving a popup or recovering connectivity.
Queued text and queued files must say what is actually persisted. Retries must
not duplicate an already accepted send.

## 6. Files and images

Sender: choose/drop/paste → attachment card → Send. Recipient: file card in the
chat → **Download** or **Decline**. No second accept dialog and no mandatory
destination picker; use the configured Downloads directory. A separate Save as
action can choose another destination. Opening downloaded files is a distinct
user action. Images open inside Harbor, with zoom, fit and scrolling.

| State | User-facing presentation | Available action |
|---|---|---|
| Selected | Name, size, preview | Send / Remove |
| Preparing | Preparing file… | Cancel |
| Offered | Waiting for Bob to download | Cancel |
| Incoming | Name, sender, size | Download / Decline |
| Transferring | Bytes, progress; speed when measured | Cancel |
| Complete | Open image/file; completion status | Open / Show in folder |
| Declined/canceled | Clear terminal status | Dismiss / Send again |
| Failed | Concrete cause without losing context | Retry / Choose another file |
| Not on this device | Metadata and availability | Download when a copy is available |

Keep explicit download consent as the default. Automatic download of trusted
contacts is a later optional policy with size/storage limits, not part of this
redesign's baseline. Never automatically execute or open a downloaded file.
Show unsupported size/type before Send using helper-advertised limits. Direct
and group limits differ; never imply parity where the current helper lacks it.
In groups, show each recipient's acceptance/delivery independently.

Performance work measures separate clocks: Send→offer visible, offer→acceptance,
acceptance→first byte, active throughput, final verification→visible completion.
Use real relay peers and report file size and network conditions. Avoid tiny
packets, repeated decoding and unnecessary copies where profiling identifies
them; preserve streaming, integrity validation, and relay privacy. Pause/resume
is shown only after durable resume semantics actually exist. An offline recipient
does not imply a file is uploaded anywhere.

## 7. Notifications that reliably work

**Defaults on new installs:** open conversation on incoming messages and file
requests; play the selected sound; show unread badges. Existing explicit mute
and popup-off settings survive updates. A standard desktop notification is the
fallback when a chat surface cannot be shown, not a simultaneous duplicate alert.
Remove the separate right-side chat notification surface as a product choice.

| Event | Visual behavior | Sound |
|---|---|---|
| New message, chat closed | Open that chat at its remembered position | Once |
| New message, chat open elsewhere | Bring/raise on the active workspace if popups enabled | Once |
| Message in focused chat | Append and preserve reading position | No redundant message ping |
| Incoming file request | Open/raise chat and reveal the file card | Once, even in focused chat |
| Friend/group request | Compact request card; retain in Requests | Once |
| Transfer progress | Update the existing file card | Silent |
| Transfer finished | Update card; unobtrusive fallback notice if hidden | Silent by default |
| Incoming call | Incoming call surface | Ring until terminal state |
| Historical sync/replayed event | Update history/unread accurately | No alert storm |
| Local action succeeded | Inline state change | Silent |
| Blocking failure | Persistent relevant error with an action | No repeated error loop |

Opening/raising is not keyboard focus. Never steal a draft or send keystrokes to
a window that appeared unexpectedly. Clicking the popup focuses it. Open each
conversation once; multiple events update the same surface. Different chats
do not stack directly on top of one another. Use one notification/audio owner
across monitors. Coalesce message bursts; a new file offer remains visible even
when its sound is grouped with a recent alert. Bound pending notification queues.

Unread clears only when the relevant content is actually visible in the active
conversation and the helper durably records it. Auto-opening a background window
does not mark a message read. While reading older messages, show New messages
instead of jumping to the end. Requests remain visible until acted on or canceled.

Settings → Notifications: **Open chats for incoming activity**, **Play message
sounds**, sound picker with Test sound, and a concise explanation of overrides.
Conversation details has “Use device defaults” or explicit popup/sound overrides.
Keep call ringing separate from message sounds. If system Do Not Disturb is
available, explain the effective suppression and offer an explicit override;
do not silently ignore user choices in either direction. Expose a local test
notification with actionable diagnostics when popup or playback fails.

For linked machines, show unread everywhere but avoid ringing every speaker for
every message: use authenticated recent activity/read state to suppress duplicate
alerts where reliable. In uncertainty, preserve visibility; do not invent device
presence. Calls ring eligible devices and stop elsewhere when one answers.

## 8. Groups and calls

Add → New group → name → choose existing contacts → Create. No separate group
management mode in the main panel. Invited people get one Join/Decline card;
joining opens the chat. Show “Invited” separately from membership until accepted.
Details owns members, Add people, permissions and Leave group. Owner/admin
actions name their targets. Leave/remove/dissolve each has one scoped confirmation.
Groups appear once per person, not once per linked device.

Direct chat has a single Call action. Incoming call shows caller and Answer /
Decline. Connecting, ringing, active and failed states are distinct. One machine
owns the answered call. End call needs no confirmation. Microphone permission
and unavailable audio are explicit. No group calls or media recording are added.

## 9. Confirmation policy and settings inventory

| Action | Proposed confirmation behavior |
|---|---|
| Send text/file, download offered file, change name/avatar | Action itself is consent; no extra dialog |
| Add friend using normal invite | Recipient's Add action; no later sender confirmation |
| Approve a restricted invite | One request card approval |
| Link device | One existing-device approval after matching code |
| Change theme, sound or popup preference | Immediate, reversible; no confirmation |
| Cancel transfer, end call, close chat | Immediate; status remains where needed |
| Remove contact/device, leave/dissolve group, clear history | One confirmation naming exact scope |
| Restore/replace identity, revoke/replace active invite | One consequence-specific confirmation |
| Verify backup before restore | Automatic validation, not a separate mandatory user chore |

Settings categories stay short: Profile; Devices; Notifications; Appearance;
Backups & recovery; Advanced. Appearance includes system theme default, message
size preview, optional formatting and chat-window mode. Advanced owns connection
diagnostics, optional encrypted mailbox, storage/download folder, protected
identity maintenance and About. Surface diagnostics as plain explanations with
optional technical detail; never dump raw protocol events into ordinary errors.

## 10. Reliability, accessibility and migration

Every asynchronous flow needs loading, success, failure, cancellation and retry.
Keep the entered nickname/invite/path while reconnecting. Persist authoritative
queued work in the helper; UI timers never invent success. Disk-full and uncertain
identity writes must produce specific recovery actions without silently deleting
state. Helper mismatch should offer a supported no-reboot recovery when safe,
explain active-call/group blockers, and preserve drafts through reconnection.

Use labelled primary buttons rather than a grid of unexplained icons. Icon-only
controls get tooltips and accessible names. Tab order follows visual order;
Escape dismisses the current transient layer; focus returns to the invoker.
Do not rely on color alone. Check long Unicode names, 140% message size, narrow
windows, different themes and missing optional assets. Search must preserve its
query and selected message when returning to the transcript.

Upgrades preserve existing contacts, history, drafts, geometry and explicit
notification choices. Do not silently enable a setting a person disabled.
Single-device users stay usable without linking or configuring a mailbox.
Existing invites retain their original consent semantics; the new normal-invite
flow needs a version/capability boundary. Legacy peers get a specific supported
fallback or an upgrade instruction, never a fake success. Move to person identity
only with authenticated proof; otherwise surface the required migration choice.

## 11. Delivery map

| Slice | Deliverable | Main dependency | Exit evidence |
|---|---|---|---|
| 0. Immediate fixes | Prepared file alerts, invitation visibility, built-in picker, promotional removal | Current helper | Native event/picker receipts; release-specific validation |
| 1. Conversation-first UI | Unified list, Add entry, settings, details, readable errors, attachment cards | Existing QML and helper projections | Real two-person message/file journeys and keyboard/theme checks |
| 2. Reliable attention and files | Notification matrix, focus/read behavior, test sound, progress states and measured transfer fixes | Helper progress/events; desktop integration | Closed/open/background chats, multiple monitors, real audio capture and timed transfers |
| 3. Add friend once | Versioned single-use normal invitation and restricted option | Explicit trust-policy decision; helper protocol | Link theft/forwarding semantics, replay/expiry, offline/restart, legacy compatibility |
| 4. One person across machines | Linking UI, device list, contact/history convergence, revocation | Completed multi-device helper, group/file/call semantics | Two people × two machines, concurrent sends, restart and revoked-device tests |
| 5. Recovery and optional offline delivery | Validated backup/restore, mailbox setup and honest availability | Fresh-session recovery and encrypted mailbox integration | All-device loss, bad backup, outage, missing attachment and disk-full journeys |

Do not make slices 0–2 wait for the experimental multi-device backend. Prototype
the setup/device screens early, but do not ship fake working controls. Do not
resume unrelated backend work merely because this design map exists. No calendar
promise until the remaining protocol work is assessed against frozen candidates.

## 12. Definition of done

Measure user tasks, not the number of features added:

- A new person reaches a usable empty conversation list by entering one nickname.
- An invite recipient connects with one Add action; the inviter is not asked again
  in normal mode. The result and trust semantics are visible on both ends.
- Paperclip → select → Send and file request → Download work without paths or
  extra confirmations. Cancel/retry never loses the selected file unexpectedly.
- An unfocused recipient sees and hears a fresh file request. Popups do not steal
  input. Muted and popup-disabled modes behave exactly as labelled.
- A linked machine shows the same person and convergent conversations; no duplicate
  contacts, reused live encryption state, false delivery or missing-history claims.
- Errors name the problem and offer an appropriate next step. No empty red fields,
  silent failed playback, indefinite unexplained spinners or manual PID rituals.
- Real native journeys cover two peers, two devices each for multi-device slices,
  multiple monitors, restart, disconnected peers, large files, duplicate events,
  cancellation, storage failure and recovery. Keep runner, candidate hashes,
  timings, sanitized receipts and visual/audio evidence on Halla.

The first friction patch is prepared and tested within its documented fixture
limits. The full redesign above is authorized and remains in progress. User-facing auto-download,
new hosted services, public discovery and multi-account switching are not included.
