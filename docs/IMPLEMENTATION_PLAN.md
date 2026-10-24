# Harbor — usability delivery

## Current scope

Tyler requested a broad reduction in friction on 24 October 2026: reliable
popups and sound, simpler files and adding friends, easier identity/device
management, and removal of the GitHub/Ko-fi panel controls.

Harbor 1.3.1 is published and installed on Veelox. The earlier installation and
per-phase approval instructions in this plan are obsolete. Preserve the large
unrelated experimental multi-device/mailbox working-tree changes.

## First patch prepared

[Everyday usability](stages/friction.md) records the implemented alert, chooser,
and panel fixes, native evidence, limitations, and remaining product journeys.
These new changes have not been committed, published, or synchronized live.
Build/test output stays under `/home/halla/build/harbor/friction-20261024/`.

## Harbor 2 implementation

[The full redesign map](REDESIGN.md) defines the approved screens, journeys, consent
policy, notification behavior, migration, delivery slices and acceptance criteria.
Tyler authorized implementation of the complete redesign and Harbor rebrand on
24 October 2026. This is the active scope; completion still requires evidence.

## Next work

The conversation-first panel, bearer-invite flow, Create identity and one-owner-
approval linking are implemented with the scoped evidence in the stage log.
File transfers now have a repeatable relay benchmark; measured throughput remains
slow. Complete visible desktop fallback and packaged native interaction checks,
then finish person-centric conversations, group/attachment synchronization,
fresh-session recovery, optional mailbox integration and call-device arbitration.
The specification owns the agreed multi-device requirements. Do not ship the
experimental helper merely because the QML usability patch passes.
