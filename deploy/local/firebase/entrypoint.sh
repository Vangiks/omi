#!/bin/sh
# Data lives in memory while the emulators run. It reaches the volume in two
# ways: --export-on-exit when the CLI gets SIGTERM or SIGINT, and a snapshot
# every SNAPSHOT_INTERVAL seconds so a kill or power loss loses at most that.
set -eu

SNAPSHOT_INTERVAL="${SNAPSHOT_INTERVAL:-300}"
META=firebase-export-metadata.json

# A snapshot swap cut short by a kill leaves the previous copy in .old.
if [ ! -f "$EXPORT_DIR/$META" ] && [ -f "$EXPORT_DIR.old/$META" ]; then
    rm -rf "$EXPORT_DIR"
    mv "$EXPORT_DIR.old" "$EXPORT_DIR"
fi
rm -rf "$EXPORT_DIR.tmp" "$EXPORT_DIR.old"
mkdir -p "$EXPORT_DIR"

snapshot_loop() {
    while sleep "$SNAPSHOT_INTERVAL"; do
        # Export next to the live copy, then swap, so a half-written export
        # never replaces a good one.
        if firebase emulators:export "$EXPORT_DIR.tmp" --project "$FIREBASE_PROJECT" --force >/dev/null 2>&1; then
            mv "$EXPORT_DIR" "$EXPORT_DIR.old"
            mv "$EXPORT_DIR.tmp" "$EXPORT_DIR"
            rm -rf "$EXPORT_DIR.old"
        else
            rm -rf "$EXPORT_DIR.tmp"
            echo "snapshot: export failed, will retry in ${SNAPSHOT_INTERVAL}s" >&2
        fi
    done
}
if [ "$SNAPSHOT_INTERVAL" -gt 0 ]; then
    snapshot_loop &
fi

set -- emulators:start --only firestore,auth --project "$FIREBASE_PROJECT" \
    --export-on-exit "$EXPORT_DIR"
# The first start has nothing to import.
if [ -f "$EXPORT_DIR/$META" ]; then
    set -- "$@" --import "$EXPORT_DIR"
fi
exec firebase "$@"
