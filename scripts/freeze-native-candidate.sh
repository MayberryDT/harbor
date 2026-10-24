#!/bin/sh
# Run in the Halla build environment. Input directory contains public binaries;
# output is never private identity/history. Receipts use these immutable paths.
set -eu
if [ "$#" -ne 1 ] || [ "${1#/}" = "$1" ]; then
  echo 'usage: freeze-native-candidate.sh /absolute/build-output-directory' >&2
  exit 2
fi
root=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
output=$1
cd "$root"
source_bundle=$(python3 scripts/freeze-native-source.py "$output")
# rsync preserves source mtimes; force both variants from this snapshot.
make -B helper tests/harbor-sync-fault-helper
if [ "$source_bundle" != "$(python3 scripts/freeze-native-source.py "$output")" ]; then
  echo 'native source changed during build; refusing candidate freeze' >&2
  exit 1
fi
printf 'source %s\n' "$source_bundle"
mkdir -p "$output/candidates"
for input in helper/omaq tests/harbor-sync-fault-helper; do
  digest=$(sha256sum "$input")
  digest=${digest%% *}
  directory=$output/candidates/$digest
  mkdir -p "$directory"
  if [ ! -e "$directory/omaq" ]; then
    temporary=$directory/omaq.staging
    cp "$input" "$temporary"
    chmod 555 "$temporary"
    mv "$temporary" "$directory/omaq"
  fi
  actual=$(sha256sum "$directory/omaq")
  actual=${actual%% *}
  if [ "$actual" != "$digest" ]; then
    echo 'candidate hash mismatch; refusing verification' >&2
    exit 1
  fi
  printf '%s %s\n' "$input" "$directory/omaq"
done
