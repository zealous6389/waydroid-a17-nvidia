#!/usr/bin/env bash
# Historical AUR helper, NOT part of this fork's normal GitHub release + PKGBUILD workflow.
# --prepare can pin checksums locally without any AUR account or publication.
# Optionally push already-committed metadata only with --enable-historical-aur.
# Default: plan only. --prepare writes local metadata; --publish requires an explicit owned AUR target,
# a prepared clean AUR checkout and fork branch. Never creates commits or assumes original AUR ownership.
# Usage: aur-publish.sh TAG [--repo OWNER/REPO] [--prepare | --publish]
#        [--package-dir DIR] [--aur-package NAME --aur-checkout DIR --aur-branch BRANCH --fork-branch BRANCH]
#        [--allow-original-repo] [--allow-original-aur] [--enable-historical-aur]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/common.sh"
TAG=${1:?usage: aur-publish.sh TAG [--repo OWNER/REPO] [--prepare | --publish]}
shift
release_check_tag "$TAG"
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
TARGET=${WAYDROID_RELEASE_REPO:-$release_repo_default}
A=$REPO/aur/waydroid-a17-nvidia-bin
explicit=0; allow_original=0; allow_original_aur=0; enable_aur=0
MODE=plan; AUR_PACKAGE=; AUR_CHECKOUT=; AUR_BRANCH=; FORK_BRANCH=
while [[ $# -gt 0 ]]; do
    case $1 in
        --repo) TARGET=${2:?--repo needs OWNER/REPO}; explicit=1; shift 2;;
        --allow-original-repo) allow_original=1; shift;;
        --allow-original-aur) allow_original_aur=1; shift;;
        --enable-historical-aur) enable_aur=1; shift;;
        --prepare|--publish)
            [[ $MODE == plan ]] || { echo "aur-publish: choose one mode" >&2; exit 2; }
            MODE=${1#--}; shift;;
        --package-dir) A=${2:?--package-dir needs a directory}; shift 2;;
        --aur-package) AUR_PACKAGE=${2:?--aur-package needs a package name you own}; shift 2;;
        --aur-checkout) AUR_CHECKOUT=${2:?--aur-checkout needs a prepared checkout}; shift 2;;
        --aur-branch) AUR_BRANCH=${2:?--aur-branch needs an explicit branch}; shift 2;;
        --fork-branch) FORK_BRANCH=${2:?--fork-branch needs an explicit branch}; shift 2;;
        *) echo "aur-publish: unknown option: $1" >&2; exit 2;;
    esac
done
release_check_repo "$TARGET" "$explicit" "$allow_original"
if [[ $MODE == publish && $enable_aur != 1 ]]; then
    echo "aur-publish: AUR publication is not requested for this fork; historical push mode requires --enable-historical-aur" >&2
    exit 2
fi
printf 'Mode: %s\nGitHub target: %s\nTag: %s\nPackage directory: %s\nAUR target (no implicit ownership): %s\n' \
    "$MODE" "$TARGET" "$TAG" "$A" "${AUR_PACKAGE:-none}"
[[ $MODE != plan ]] || exit 0
release_require gh jq curl python3 makepkg sha256sum
[[ -f "$A/PKGBUILD" ]] || { echo "aur-publish: trusted local PKGBUILD is missing" >&2; exit 1; }
A=$(realpath "$A")
release_check_pkg_repo "$A/PKGBUILD" "$TARGET"
grep -qx "_tag=$TAG" "$A/PKGBUILD" ||
    { echo "aur-publish: PKGBUILD is not at $TAG" >&2; exit 1; }
is_draft=$(gh release view "$TAG" --repo "$TARGET" --json isDraft -q .isDraft)
[[ $MODE != publish || $is_draft == false ]] ||
    { echo "aur-publish: cannot push AUR metadata for an unpublished release" >&2; exit 1; }
T=$(mktemp -d "${TMPDIR:-/tmp/opencode}/release-checksums.XXXXXX")
# Evidence/downloads are retained. No cleanup removes caches or build outputs.
echo "aur-publish: checksum evidence retained in $T"
mapfile -t SOURCES < <(bash -c 'source "$1"; printf "%s\n" "${source[@]}"' _ "$A/PKGBUILD")
[[ ${#SOURCES[@]} -gt 0 ]] || { echo "aur-publish: empty source array" >&2; exit 1; }
re='^https://github\.com/([^/]+/[^/]+)/releases/download/([^/]+)/([^/]+)$'
sums=()
for i in "${!SOURCES[@]}"; do
    url=${SOURCES[$i]#*::}
    [[ $url == https://* ]] || { echo "aur-publish: unsupported non-HTTPS source: $url" >&2; exit 1; }
    sum=
    if [[ $url =~ $re ]]; then
        asset_repo=${BASH_REMATCH[1]}; asset_tag=${BASH_REMATCH[2]}; asset_name=${BASH_REMATCH[3]}
        # This project's assets must come from the selected fork. Historical Shiro rc10 dependencies
        # remain separately checksum-pinned third-party inputs.
        if [[ ${asset_repo,,} == */waydroid-a17-nvidia && ${asset_repo,,} != "${TARGET,,}" ]]; then
            echo "aur-publish: project asset points at the wrong release repository: $url" >&2; exit 1
        fi
        rel=$T/release-$i.json
        gh api "repos/$asset_repo/releases/tags/$asset_tag" > "$rel"
        sum=$(jq -r --arg n "$asset_name" \
            '.assets[] | select(.name == $n and .state == "uploaded") | .digest // empty' "$rel")
        sum=${sum#sha256:}
    fi
    if [[ -z $sum ]]; then
        # GitHub-generated tag/commit archives must be downloaded and hashed as actually served.
        curl --proto '=https' --proto-redir '=https' -fsSL --retry 5 --retry-all-errors -o "$T/source-$i" "$url"
        sum=$(sha256sum "$T/source-$i" | cut -d' ' -f1)
    fi
    [[ $sum =~ ^[0-9a-f]{64}$ ]] || { echo "aur-publish: no unique sha256 for $url" >&2; exit 1; }
    printf '%s  %s\n' "$sum" "$url"
    sums+=("$sum")
done
printf '%s\n' "${sums[@]}" > "$T/sha256sums"
if [[ $MODE == prepare ]]; then
    python3 - "$A/PKGBUILD" "$T/sha256sums" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
sums = pathlib.Path(sys.argv[2]).read_text().splitlines()
replacement = "sha256sums=(" + "\n            ".join(repr(s) for s in sums) + ")"
text, count = re.subn(r"^sha256sums=\([\s\S]*?\)[ \t]*$", lambda m: replacement,
                      p.read_text(), flags=re.MULTILINE)
if count != 1:
    raise SystemExit("aur-publish: expected one sha256sums array; update manually")
p.write_text(text)
PY
    (cd "$A" && makepkg --printsrcinfo > "$T/.SRCINFO")
    cp "$T/.SRCINFO" "$A/.SRCINFO"
    echo "aur-publish: metadata prepared only. Validate exact remote inputs, review, and sign commits manually."
    exit 0
fi
mapfile -t recorded < <(bash -c 'source "$1"; printf "%s\n" "${sha256sums[@]}"' _ "$A/PKGBUILD")
[[ ${recorded[*]} == "${sums[*]}" ]] ||
    { echo "aur-publish: committed checksums do not match release; run --prepare and validate/review first" >&2; exit 1; }
[[ $AUR_PACKAGE =~ ^[a-z0-9][a-z0-9+_.-]*$ && -n "$AUR_CHECKOUT" && -n "$AUR_BRANCH" && -n "$FORK_BRANCH" ]] ||
    { echo "aur-publish: --publish needs explicit --aur-package, --aur-checkout, --aur-branch and --fork-branch" >&2; exit 1; }
[[ $AUR_PACKAGE != waydroid-a17-nvidia-bin || $allow_original_aur == 1 ]] ||
    { echo "aur-publish: original AUR name requires --allow-original-aur and verified ownership" >&2; exit 1; }
git check-ref-format "refs/heads/$AUR_BRANCH"
git check-ref-format "refs/heads/$FORK_BRANCH"
AUR_CHECKOUT=$(realpath "$AUR_CHECKOUT")
[[ -d "$AUR_CHECKOUT/.git" ]] || { echo "aur-publish: AUR checkout must be a standalone repository" >&2; exit 1; }
[[ $(git -C "$AUR_CHECKOUT" remote get-url --push origin) == "ssh://aur@aur.archlinux.org/$AUR_PACKAGE.git" ]] ||
    { echo "aur-publish: AUR push remote does not match the explicitly selected package" >&2; exit 1; }
pkgname=$(bash -c 'source "$1"; printf "%s\n" "${pkgname[@]}"' _ "$A/PKGBUILD")
[[ $pkgname == "$AUR_PACKAGE" ]] ||
    { echo "aur-publish: pkgname does not match explicitly selected AUR name" >&2; exit 1; }
for checkout in "$REPO" "$AUR_CHECKOUT"; do
    [[ -z "$(git -C "$checkout" status --porcelain --untracked-files=no)" ]] ||
        { echo "aur-publish: tracked changes require manual signed commits first: $checkout" >&2; exit 1; }
done
cmp "$A/PKGBUILD" "$AUR_CHECKOUT/PKGBUILD"
cmp "$A/.SRCINFO" "$AUR_CHECKOUT/.SRCINFO"
(cd "$A" && makepkg --printsrcinfo) > "$T/expected.SRCINFO"
cmp "$A/.SRCINFO" "$T/expected.SRCINFO"
install_file=$(bash -c 'source "$1"; printf "%s\n" "${install:-}"' _ "$A/PKGBUILD")
if [[ -n $install_file ]]; then
    [[ $install_file != */* && $install_file != .. ]] || { echo "aur-publish: invalid install file name" >&2; exit 1; }
    cmp "$A/$install_file" "$AUR_CHECKOUT/$install_file"
fi
# Exactly these explicitly selected destinations; no tag creation, commits, force-push or original inference.
git -C "$REPO" push "https://github.com/$TARGET.git" "HEAD:refs/heads/$FORK_BRANCH"
git -C "$AUR_CHECKOUT" push origin "HEAD:refs/heads/$AUR_BRANCH"
