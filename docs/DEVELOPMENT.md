# Development and verification

Start with [the living plan](IMPLEMENTATION_PLAN.md), then the relevant sections
of [the specification](SPECIFICATION.md). Read [juice](../juice.md) for experience
work and retain useful scoped findings there. Existing source remains at
`/home/tyler/Work/harbor`; preserve its staged implementation. Do not migrate or
create branches/worktrees without the repository's explicit preparation approval.

Builds, dependency installations and tests belong on Halla. Use a disposable
source snapshot (never private runtime state) and keep outputs beneath
`/home/halla/build/harbor`. A future canonical checkout belongs under
`/home/halla/workspaces/harbor`; it does not exist at this checkpoint.

## Observed environment, 23 October 2026
Halla is Ubuntu 24.04 with cc, pkg-config, Python 3, Node and Docker. OpenSSL,
PulseAudio and image pkg-config packages are present. Tox/Signal pkg-config
packages and QML command-line tools are absent from the default environment.
The earlier frozen helper cannot run there directly: ldd reports missing
`libtoxcore.so.2` and `libsignal-protocol-c.so.2`. Earlier logs are provenance,
not a successful current Halla rebuild. Passwordless sudo is unavailable.
Do not alter ibara's existing SDK containers to bootstrap Harbor.

## Harbor-owned build environment
Current Halla SDK: `harbor-build:implementation-20261023`, image ID
`sha256:d272b0e02f937c82fdf5ee040e412b5d492ec65a6ae4948a101613dace6b973d`.
It extends the preparation SDK with `jq`, required by the inherited native
window-script fixture. The recipe now includes that dependency. The earlier
preparation SDK is image `325180b3885b8b017dfba84a1f3667b44f0679fc7b06e634ba910554b8f12737`.
The first temporary image was externally pruned; this replacement uses the same
recipe. A recoverable `docker save` archive is retained at
`/home/halla/build/harbor/implementation-20261023/sdk/harbor-build.tar.gz`, SHA-256
`29f6437ed298880acd36e4334f241ca4869597e63b2522e6706c8d16f41d1a30`.
The current complete archive is `sdk/harbor-build-jq.tar.gz`, SHA-256
`3c868e4fe323c82a9ee09a6c9e13c033429c347b6550ccc22e819512452a9057`;
current versions are in `sdk/packages-jq.txt`. Restore with `gzip -dc ... | docker load`.
During active development `harbor-sdk-jq-hold-20261023` keeps the SDK in use to
protect it from external image pruning. Remove that Harbor-owned holder when
work is complete; no live user app runs inside it.
[Container recipe](../packaging/build-host/Dockerfile) pins the inspected base;
package repositories roll, so preserve the existing image for this exact setup.
Installed package versions, container build log, candidate build/check log and
helper SHA-256 are retained under
`/home/halla/build/harbor/preparation-20261023/`.
`source/` there is a disposable snapshot, not a canonical Git checkout.
`make helper` (including helper hardening) and `make arch` passed in this image
with networking disabled. No private user data or live configuration was copied.

Repeat the setup checks on Halla:
```sh
docker run --init --rm --pull never --network none \
  -v /home/halla/build/harbor/preparation-20261023/source:/source \
  harbor-build:implementation-20261023 sh -c 'make helper && make arch'
```
Refresh the disposable source snapshot from the actual checkout before future
work; keep build output on Halla. The image includes Qt tools, but real shell
integration/interaction still requires Omarchy. Native multi-device checks now run against frozen candidates as described below.

## Existing commands
Use `docker run --init` for verification: updater process-group timeout checks
require normal orphan reaping. Running Python or a shell directly as container
PID 1 can retain killed descendants as zombies and falsely report them alive.
Keep that environment distinction separate from application/test changes.

From a disposable source snapshot in that full environment:
`make helper`, `make arch`, `make test-ci`, and
`python3 tests/harbor-e2e.py /absolute/path/to/helper/omaq`.
The E2E requires real TCP relay connectivity and uses disposable identities.
Inspect its output/receipt handling before selecting the build-output directory.
`make test` includes native QML fixtures; see [baseline limits](HARBOR.md).
Omarchy manifest validation and live UI interaction require an Omarchy host;
never activate a live plugin merely to satisfy a headless build check.

## Frozen native E2E candidates
Run `sh scripts/freeze-native-candidate.sh /build` inside the SDK with the public
source snapshot mounted at `/source` and the implementation output mounted at
`/build`. Run as Halla’s UID/GID. The script forces fresh normal and fault builds (source synchronization preserves
mtimes, so incremental fault builds can otherwise be stale),
freezes all native source inputs before and after compilation, rejects a changing
snapshot, checks hardening and copies executables to `/build/candidates/<sha256>/omaq`.
Use those paths for every long native test. Never hash a mutable helper at the
end of a test and call that candidate identification; early implementation runs
with that flaw must be repeated.

New native runners take the frozen helper and an absolute JSON receipt path:
`devices-e2e.py`, `device-link-e2e.py`, `device-sync-e2e.py`,
`person-discovery-e2e.py`, `person-chat-e2e.py`, `person-boundary-e2e.py`, and
`person-endpoint-boundary-e2e.py` under `tests/`. Discovery optionally accepts a
fault-helper path to verify the endorsement-before-pin crash boundary.
`device-sync-crash-e2e.py` and `device-sync-rekey-e2e.py` take normal helper,
fault helper, then receipt. Network checks require TCP relay connectivity and
use only temporary disposable identities.

Compile `tests/journal-io-faults.c` inside the SDK with
`cc -shared -fPIC -Wall -Werror -o /build/journal-io-faults.so tests/journal-io-faults.c -ldl`.
`person-journal-io-e2e.py` and `contact-projection-e2e.py` take normal helper,
that shim, then receipt. The shim is loaded only into the disposable target
helper and injects actual storage sync failures plus mid-query SQLite cursor
errors (legacy event-directory failures remain for migration checks). Freeze
the C shim with the Python runners and compile it from that bundle; retain its
SHA-256 and use a fresh output filename rather than replacing a loaded shim.

Outputs and sanitized receipts live under
`/home/halla/build/harbor/implementation-20261023/`. Consult each receipt’s
candidate hash and declared scope; file presence alone is not passing evidence.
The specification’s complete native/UI/mailbox/recovery journeys remain
unfinished. Favor E2E and never add post-implementation unit or tautological tests.

Freeze runner code/imports with `python3 scripts/freeze-native-runners.py /build`
and use the returned bundle path. `person-actions-e2e.py`,
`legacy-revocation-e2e.py`, `revocation-io-e2e.py` and
`person-history-capacity-e2e.py` take helper then receipt. The legacy attack runner
requires the fault helper; its `sync.inject kind=legacy` route is absent in
production and deliberately simulates hostile retained-key software.
`device-revocation-boundary-e2e.py` takes helper, compiled
`device-link-receive-driver.c` executable, then receipt; its decrypted-boundary
control is explicitly separate from real network delivery.
