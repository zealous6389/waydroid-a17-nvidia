#!/usr/bin/env bash
# Prepare prebuilt vendor/native release assets and a local binary package.
# Adapted from upstream commit 28955ede2c365c6822984e64c68b58dda673e285.
# Default is a plan. --build opts into local writes/builds, never publication or installation.
# No outputs/caches are deleted automatically: cleanup is a separate authorized post-verification action.
# Usage: package.sh TAG [--repo OWNER/REPO] [--build] [--resplit]
#        [--assets-dir DIR] [--package-dir DIR] [--allow-original-repo]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/common.sh"
TAG=${1:?usage: package.sh TAG [--repo OWNER/REPO] [--build] [--resplit] [--assets-dir DIR] [--package-dir DIR]}
shift
release_check_tag "$TAG"
PKGVER=${BASH_REMATCH[1]}.${BASH_REMATCH[2]}
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
WS=${WAYDROID_A17_WS:-$(dirname "$REPO")}
TARGET=${WAYDROID_RELEASE_REPO:-$release_repo_default}
explicit=0; allow_original=0; build=0; resplit=0
A=$REPO/aur/waydroid-a17-nvidia-bin
ASSETS=$WS/nvidia/release/$TAG
while [[ $# -gt 0 ]]; do
    case $1 in
        --repo) TARGET=${2:?--repo needs OWNER/REPO}; explicit=1; shift 2;;
        --allow-original-repo) allow_original=1; shift;;
        --build) build=1; shift;;
        --resplit) resplit=1; shift;;
        --assets-dir) ASSETS=${2:?--assets-dir needs a directory}; shift 2;;
        --package-dir) A=${2:?--package-dir needs a directory}; shift 2;;
        *) echo "package: unknown option: $1" >&2; exit 2;;
    esac
done
release_check_repo "$TARGET" "$explicit" "$allow_original"
IMG=${WAYDROID_VENDOR_IMAGE:-$WS/src/out/target/product/waydroid_nvidia_x86_64/vendor.img}
printf 'Local packaging plan only unless --build:\n  target: %s\n  tag: %s (%s)\n  image: %s\n  assets: %s\n  package: %s\n' \
    "$TARGET" "$TAG" "$PKGVER" "$IMG" "$ASSETS" "$A"
[[ $build == 1 ]] || exit 0
release_require python3 zstd tar split sha256sum makepkg updpkgsums
[[ -f "$A/PKGBUILD" && -f "$IMG" ]] ||
    { echo "package: missing trusted PKGBUILD or vendor image; check WAYDROID_A17_WS/WAYDROID_VENDOR_IMAGE" >&2; exit 1; }
A=$(realpath "$A")
release_check_pkg_repo "$A/PKGBUILD" "$TARGET"
if ! grep -qx "_tag=$TAG" "$A/PKGBUILD"; then
    sed -i -e "s/^pkgver=.*/pkgver=$PKGVER/" -e 's/^pkgrel=.*/pkgrel=1/' -e "s/^_tag=.*/_tag=$TAG/" "$A/PKGBUILD"
    echo "package: bumped PKGBUILD to $TAG; review and create a signed Conventional Commit, then rerun" >&2
    exit 1
fi
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
    { echo "package: commit reviewed tracked release changes first; build/cache files are not automatically deleted" >&2; exit 1; }
PIN=$WS/nvidia/product/vendor/nvidia-prolapse/native-bundle.json
[[ -f "$PIN" ]] || { echo "package: missing native bundle pin: $PIN" >&2; exit 1; }
NB=$(python3 -I -c 'import json,pathlib,sys; p=json.load(open(sys.argv[1]))["path"]; print(pathlib.Path(sys.argv[2], p).resolve())' "$PIN" "$WS")
[[ -f "$NB/BUILD-RECORD.json" ]] || { echo "package: missing pinned native bundle: $NB" >&2; exit 1; }
mkdir -p "$ASSETS"
ASSETS=$(realpath "$ASSETS")
NATIVE=waydroid-a17-nvidia-native-x86_64.tar.zst
# Refuse overwrites; use a fresh asset directory to retry without losing evidence or caches.
shopt -s nullglob
existing=("$ASSETS"/vendor.img.zst.part* "$ASSETS"/vendor.img.zst.sha256)
[[ ${#existing[@]} == 0 ]] || { echo "package: split assets already exist; choose a fresh --assets-dir" >&2; exit 1; }
if [[ $resplit == 1 ]]; then
    [[ -f "$ASSETS/vendor.img.zst" && -f "$ASSETS/$NATIVE" ]] ||
        { echo "package: --resplit needs verified compressed image/native archives in the asset directory" >&2; exit 1; }
    zstd -dq -c "$ASSETS/vendor.img.zst" | cmp - "$IMG"
else
    [[ ! -e "$ASSETS/vendor.img.zst" && ! -e "$ASSETS/$NATIVE" ]] ||
        { echo "package: archives exist; preserve them and choose a fresh directory, or use --resplit" >&2; exit 1; }
    zstd -q -19 -T0 "$IMG" -o "$ASSETS/vendor.img.zst"
    (cd "$NB" && tar --sort=name --owner=0 --group=0 --numeric-owner --mtime=@0 --zstd -cf "$ASSETS/$NATIVE" .)
fi
split -b "${VENDOR_PART_SIZE:-5M}" -d -a 2 "$ASSETS/vendor.img.zst" "$ASSETS/vendor.img.zst.part"
(
    cd "$ASSETS"
    sha256sum vendor.img.zst.part[0-9][0-9] vendor.img.zst
    sha256sum "$IMG" | sed 's|  .*|  vendor.img|'
) > "$ASSETS/vendor.img.zst.sha256"
parts=("$ASSETS"/vendor.img.zst.part[0-9][0-9])
listed=$(bash -c 'source "$1"; printf "%s\n" "$_vendor_parts"' _ "$A/PKGBUILD")
[[ ${#parts[@]} == "$listed" ]] ||
    { echo "package: ${#parts[@]} image parts, PKGBUILD lists $listed; update source array and retry in a fresh directory" >&2; exit 1; }
# A local git archive is only preliminary input, NOT the GitHub-generated tag archive.
source_tar=$A/waydroid-a17-nvidia-$TAG.tar.gz
native_tar=$A/waydroid-a17-nvidia-native-x86_64-$TAG.tar.zst
[[ ! -e "$source_tar" && ! -e "$native_tar" ]] ||
    { echo "package: tag inputs already cached; do not overwrite them automatically" >&2; exit 1; }
for part in "${parts[@]}"; do
    [[ ! -e "$A/vendor-$TAG.img.zst.${part##*.}" ]] ||
        { echo "package: part already cached: $part" >&2; exit 1; }
done
git -C "$REPO" archive --format=tar.gz --prefix="waydroid-a17-nvidia-$TAG/" HEAD > "$source_tar"
cp "$ASSETS/$NATIVE" "$native_tar"
for part in "${parts[@]}"; do cp "$part" "$A/vendor-$TAG.img.zst.${part##*.}"; done
# Historical rc10 third-party inputs are immutable dependencies, not publication targets.
for file in "$WS"/nvidia/release/waydroid-nvidia-*-v0.2.0-rc10.tar.zst; do
    [[ -e "$A/${file##*/}" ]] || cp "$file" "$A/"
done
cd "$A"
updpkgsums
umask 077
LOG=$(mktemp "${TMPDIR:-/tmp/opencode}/wd-makepkg.XXXXXX.log")
# Deliberately no -C / --cleanbuild / --clean / -f: preserve costly build products and prior packages.
makepkg --log > "$LOG" 2>&1 || { tail -20 "$LOG"; echo "package: full log: $LOG" >&2; exit 1; }
makepkg --packagelist
cat "$ASSETS/vendor.img.zst.sha256"
echo "package: preliminary local build only; validate exact published GitHub inputs before distribution"
