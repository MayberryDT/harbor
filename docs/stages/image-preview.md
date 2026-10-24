# In-app image preview

24 October 2026. Source change, not deployed.

## Evidence and change

Native thumbnail clicks in released Harbor on Dell Optiplex and BMAX launched
imv-wayland 5.0.1-2, which crashed with SIGFPE/FPE_INTDIV. Harbor remained
responsive. Direct invocation reproduced it; imv-x11 displayed the same PNG.
This establishes the failure on those machines, not the exact cause on Dennis's.

ChatPage now uses a themed modal preview instead of xdg-open for image clicks,
including the pending attachment preview. Decode size is bounded to 4096x4096;
Zoom in exposes the decoded image with scrolling and Fit restores the overview.
Close and Escape restore composer focus without altering the draft. Missing
images show `Image unavailable`. Conversation/key changes and invalid contact
bindings close the preview. No system file associations are changed.

## Verification

Failure cases considered before implementation: external viewer failure, large
decode, special-character paths, missing file, lost draft/focus, stale contact
preview, compact layout and unreadable screenshot text.

Final native Dell task: `task_b2cdb1be89ba4d848039c33a8e468c88`.
Tested ChatPage SHA-256:
`1dd498a0b14e2aa4f1f47e431a2b86f58c73bd1e3f1e646cf262563386be51d4`.
Actual pointer/keyboard/wheel actions verified opening a 3840x2160 PNG with
spaces and `#` in its filename, Zoom in, scrolling, Fit, Close, demo send/reply,
missing-file error, Escape, unchanged unsent draft, and a 400x650 ChatPage.
No imv process was launched. The source review's zoom and stale-contact findings
were addressed; follow-up review found no material defects.

BMAX confirmation task `task_a875cea2f2fd4b41b12a5094e379f1dd` also passed
native image opening, Escape and continued composer input on the final revision.
Both machines that reproduced the original viewer crash now display the image
inside Harbor. Both tasks finished and released their desktops.

Repeatable fixture, patch, logs, image and RESULT.md are retained in the task
workspace under `/home/tater2/.local/share/agent-computer/workspaces/`.
Extract release cc46d9b into `source`, apply `preview.patch` there, run
`python3 prepare.py`, then `quickshell -n -p shell.qml`. `narrow.qml` constrains
the ChatPage. Move the generated PNG aside to exercise missing-file recovery.
Use native ibara input to click the thumbnail, buttons and composer.

This is an isolated actual ChatPage with demo messages, not a full live-plugin
activation. Installer dependencies/assets were not installed; fixture logs retain
baseline missing Material Symbols/emoji warnings. An initial AK1 run verified
error/draft handling but storage limits prevented its final-revision checks.

Halla artifacts: `/home/halla/build/harbor/image-preview-20261024/`.
`make arch` passed. ChatPage QML lint exited 0 with existing unqualified-access
warnings. `git diff --check` passed.
No helper/protocol code was changed; the real-peer transport suite uses the
released helper and writes `transport-receipt.json` separately.
The first transport run lacked Pillow in the test SDK and stopped during image
verification after nine successful checks; its receipt is retained separately
as `transport-missing-pillow.json`. The rerun installs Pillow only in its
disposable container.

The corrected real TCP-relay run passed: encrypted 64 KiB direct/group text,
history, large edit/search, oversized-message rejection, pending-send shutdown
protection, a 12 MiB file and a 3840x2160 image with decoded-pixel verification.
`transport-receipt.json` has `passed: true` and identifies the released helper
SHA-256 `c14471452ca93de0f3b4ee24cb6dfea4f7e2d21689e7ea205f2d94df4b38738d`.
