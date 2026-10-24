#!/bin/sh
# Harbor entry point; preserve the legacy installer implementation during migration.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec "$root/uninstall-omaq.sh" "$@"
