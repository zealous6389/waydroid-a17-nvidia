#!/usr/bin/env bash
# Explicit opt-in installation of a locally built package and release-gate execution.
# Upstream deleted every vendor overlay file; this fork refuses nonempty overlays.
# Requires an operator-prepared rollback directory; never backs up/deletes guest /data.
# Usage: install-gate.sh PKGVER [--package FILE] [--install --images-path DIR --rollback-dir DIR]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/common.sh"
VER=${1:?usage: install-gate.sh PKGVER [--package FILE] [--install --images-path DIR --rollback-dir DIR]}
shift
[[ $VER =~ ^[0-9]{8}\.[0-9]+$ ]] || { echo "install-gate: invalid pkgver" >&2; exit 2; }
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
PKG=$REPO/aur/waydroid-a17-nvidia-bin/waydroid-a17-nvidia-bin-$VER-1-x86_64.pkg.tar.zst
install=0; IMAGES=; ROLLBACK=
OVERLAY=${WAYDROID_VENDOR_OVERLAY:-/var/lib/waydroid/overlay/vendor}
STATE=${WAYDROID_VENDOR_STATE:-/var/lib/waydroid-nvidia/vendor-image}
while [[ $# -gt 0 ]]; do
    case $1 in
        --package) PKG=${2:?--package needs a file}; shift 2;;
        --install) install=1; shift;;
        --images-path) IMAGES=${2:?--images-path needs the actual configured image directory}; shift 2;;
        --rollback-dir) ROLLBACK=${2:?--rollback-dir needs a directory}; shift 2;;
        *) echo "install-gate: unknown option: $1" >&2; exit 2;;
    esac
done
printf 'Install plan only unless --install:\n  package: %s\n  images: %s\n  state: %s\n  overlay (must be empty): %s\n' "$PKG" "$IMAGES" "$STATE" "$OVERLAY"
[[ $install == 1 ]] || exit 0
release_require waydroid sudo pacman sha256sum systemctl
[[ -f "$PKG" && -n "$IMAGES" && -d "$ROLLBACK" ]] ||
    { echo "install-gate: package, explicit images path and prepared rollback directory required" >&2; exit 1; }
[[ -f "$ROLLBACK/manifest.txt" ]] ||
    { echo "install-gate: rollback directory needs manifest.txt listing replaced files/config and restore steps; see SKILL.md" >&2; exit 1; }
SUDO=(sudo ${SUDO_ASKPASS:+-A})
if "${SUDO[@]}" test -d "$OVERLAY"; then
    overlay_files=$("${SUDO[@]}" find "$OVERLAY" -mindepth 1 ! -type d -print)
    [[ -z "$overlay_files" ]] ||
        { echo "install-gate: overlay is not empty; inspect and preserve overrides manually:" >&2; printf '%s\n' "$overlay_files" >&2; exit 1; }
fi
# Verify the actual image path/configuration and rollback contents manually before this opt-in.
before=$("${SUDO[@]}" sha256sum "$IMAGES/system.img")
umask 077
LOG=$(mktemp "${TMPDIR:-/tmp/opencode}/wd-setup.XXXXXX.log")
verify_system() {
    local status=$? after
    trap - EXIT
    after=$("${SUDO[@]}" sha256sum "$IMAGES/system.img") || status=1
    if [[ $before != "$after" ]]; then
        echo "install-gate: ERROR: system.img changed or could not be read; consult rollback manifest" >&2
        status=1
    fi
    printf '%s\n' "$before" > "$LOG.system-before.sha256"
    printf '%s\n' "$after" > "$LOG.system-after.sha256"
    echo "install-gate: evidence: $LOG"
    exit "$status"
}
trap verify_system EXIT
waydroid session stop >/dev/null 2>&1 || true
"${SUDO[@]}" systemctl stop waydroid-container.service
"${SUDO[@]}" pacman -U "$PKG"
rc=0
# Keep lxc/setup away from regular user-owned log descriptors.
"${SUDO[@]}" env LC_ALL=C waydroid-nvidia-setup 2>&1 | tee "$LOG" || rc=$?
grep -cE '^PASS' "$LOG" | sed 's/^/gate cases passed: /' || true
grep -E 'FAIL|Release gate|byte-identical|Installed the|rror' "$LOG" || true
[[ $rc == 0 ]] || exit "$rc"
grep -q 'Release gate PASS' "$LOG" && grep -q 'Installed the' "$LOG" ||
    { echo "install-gate: setup exited zero but expected gate/install evidence is missing" >&2; exit 1; }
