# Nickname draft loss — 24 October 2026

Reproduced using real pointer input on an isolated Omarchy desktop: with
`activeHelperProtocol = 0`, type `Dad` and click Save. The disabled control lets
the click reach the card's background `MouseArea`; `dismissTransientSections()`
then replaces the draft with the empty saved nickname. This is independent of
the nickname's contents. The outline alone does not identify a validation error.

The fix keeps header clicks away from background dismissal, marks typed drafts
as active edits, and lets valid Save attempts explain why the helper cannot
accept them. Failure text occupies the existing lower menu frame and wraps;
the fixed header retains its original height. Request correlation and the
helper's validation/persistence remain unchanged.

## Repeatable UI check

Use an isolated Panel instance with helper startup disabled and a controlled
`sendImmediateOp` boundary; never point it at a real profile. The checked
fixture is retained on BMAX B4 Plus under
`/home/tater3/.local/share/agent-computer/workspaces/task_eb026e2689e8447d895ae0adb6341f62/`.
`prepare-ui.py`, `nickname-cases.md`, `ui/harbor/Panel.qml`,
`ui/harbor/Service.qml` and `ui/shell.qml` identify the fixture and scenarios.
The panel uses a FloatingWindow for input inspection because the automation
cannot target layer surfaces. Only the shell container and helper boundary
are adapted; nickname controls execute their actual handlers.

1. Set the fixture's initial helper protocol to 0 and compatibility to unknown.
   Start `quickshell -n -p ui/shell.qml` with `OMAQ_HOME` and `OMAQ_STATE` pointing
   at the fixture's `isolated/data` and `isolated/state` directories.
2. Type `Dad`, click Save: the draft must remain and readable helper feedback
   must appear inside the lower-left frame, without scrolling or a tooltip.
3. Repeat with initial protocol 17 and compatible helper. Type a valid nickname
   and press Enter. The boundary records `nickname.set` and returns its exact
   request ID in a nickname event; the panel must show the saved nickname and
   clear feedback.

Baseline disappearance: input operation `op_b38a245afe444bc29f7f6719346e56b8`.
Fixed failed-save frame: `frame_27b198a39d8149548433bcfa59f7f0bf`;
log `ui-final.log`. Final ready-helper Enter save records `NICK_RESULT Dad Dad`
in `ui-success.log` after input operation `op_a00c19c5a4d64312a6b2796515d8bc27`.
Checks use disposable text only. Pending double-click and delayed profile-refresh
cases were identified beforehand but were not exercised in this manual run.

Independent code review found the initial feedback placement was clipped;
including nickname feedback in the existing menu sizing fixed it. Targeted
follow-up found no further material issue. `git diff --check` and Omarchy plugin
validation passed. The inherited `panel-request-focus.sh` runtime fixture fails
before execution because its immediate-send replacement no longer matches
Service.qml; it is not counted as a passing runtime check.

The native helper's existing phase5 check passed separately on Halla against
the preserved basic-chat candidate. Log:
`/home/halla/build/harbor/nickname-20261024/phase5.log`.
The controlled UI response is not proof of native persistence or full live
panel integration. Dad's machine was not accessed: the reason its helper is
unavailable remains unconfirmed. No live synchronization, restart, commit or
push was performed.
