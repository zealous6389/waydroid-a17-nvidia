#!/usr/bin/env bash
# Shared safeguards for the fork's release helpers. Source from trusted local scripts.
# Upstream provenance: cagedbird043/waydroid-a17-nvidia@28955ede2c365c6822984e64c68b58dda673e285.
# The original repository is historical provenance, never the implicit publishing target.
release_repo_default=zealous6389/waydroid-a17-nvidia
release_check_repo() {
    local target=$1 explicit=$2 allow_original=$3
    [[ $target =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ && $target != *..* ]] ||
        { echo "release: invalid owner/repository: $target" >&2; return 1; }
    if [[ ${target,,} == cagedbird043/waydroid-a17-nvidia ]]; then
        [[ $explicit == 1 && $allow_original == 1 ]] ||
            { echo "release: original repository requires explicit --repo and --allow-original-repo" >&2; return 1; }
    fi
}
release_require() {
    local command
    for command in "$@"; do
        command -v "$command" >/dev/null || { echo "release: missing command: $command" >&2; return 1; }
    done
}
release_check_pkg_repo() {
    local pkgbuild=$1 target=$2 actual
    # PKGBUILD is executable shell code: use only a locally reviewed, trusted file.
    actual=$(bash -c 'source "$1"; printf "%s\n" "$url"' _ "$pkgbuild") || return 1
    [[ ${actual%/} == "https://github.com/$target" ]] ||
        { echo "release: PKGBUILD url=$actual does not match explicit target $target; update/review it first" >&2; return 1; }
}
release_check_tag() {
    [[ $1 =~ ^a17-([0-9]{8})-([0-9]+)$ ]] ||
        { echo "release: tag must look like a17-YYYYMMDD-N" >&2; return 1; }
}
