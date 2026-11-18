#!/usr/bin/env bash
# Run a shell command as root inside the running Waydroid container.
# Usage: guest.sh '<command>' (sudo; set SUDO_ASKPASS for graphical authentication)
set -euo pipefail
[[ $# == 1 ]] || { echo "usage: $0 '<guest command>'" >&2; exit 2; }
LXC_PATH=${WAYDROID_LXC_PATH:-/var/lib/waydroid/lxc}
LXC_NAME=${WAYDROID_LXC_NAME:-waydroid}
for cmd in sudo lxc-attach; do
    command -v "$cmd" >/dev/null || { echo "guest: missing command: $cmd" >&2; exit 1; }
done
[[ -d "$LXC_PATH/$LXC_NAME" ]] || { echo "guest: missing container: $LXC_PATH/$LXC_NAME" >&2; exit 1; }
exec sudo ${SUDO_ASKPASS:+-A} lxc-attach -P "$LXC_PATH" -n "$LXC_NAME" --clear-env \
    -v PATH=/system/bin:/vendor/bin -- /system/bin/sh -c "$1"
