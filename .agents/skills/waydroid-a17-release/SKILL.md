---
name: waydroid-a17-release
description: Prepare and validate a GitHub fork release of waydroid-a17-nvidia with a checksum-pinned binary PKGBUILD and prebuilt vendor/native assets, test installation, and publish only with explicit authorization and fork targets. No AUR account/publication is needed. Use for release planning, packaging, gates, asset checksums, and post-verification cleanup of task-created outputs/cache while protecting installed runtime, Android data and source changes.
---

# Release

Restored/adapted from `cagedbird043/waydroid-a17-nvidia` commit
`28955ede2c365c6822984e64c68b58dda673e285`. All instructions are English.
The original repository/author are **provenance**, not implicit publishing destinations.
The fork default is **`zealous6389/waydroid-a17-nvidia`**.

Only publish when the user explicitly asks. Pushing commits/tags, creating or publishing releases,
uploading assets and pushing AUR metadata are external actions. A local validation request does
not authorize them. The restored scripts default to printing a plan; no script creates commits.
The user has no AUR account and explicitly does not want AUR publication. The normal deliverable
is a validated **GitHub fork release plus PKGBUILD in the repository/release assets**.
The restored `aur-publish.sh` is historical opt-in support; its `--prepare` mode is only a local
checksum/.SRCINFO preparation utility. No AUR ownership is assumed.

Scripts live in `.agents/skills/waydroid-a17-release/scripts/` (`$R` below).
They share `common.sh` for target/tool checks.
Tag format: `a17-YYYYMMDD-N`; pkgver: `YYYYMMDD.N`.
Native bundle identities historically used `v0.2.0-rc11-a17-<suffix>`.

## Paths, targets and prerequisites

```bash
R=.agents/skills/waydroid-a17-release/scripts
export WAYDROID_A17_WS=/path/to/complete/workspace
export WAYDROID_RELEASE_REPO=zealous6389/waydroid-a17-nvidia
TARGET=$WAYDROID_RELEASE_REPO
```

The active workspace reported for this fork is
`/home/aria/Projects/waydroid-a17-nvidia-work`; its native userspace checkout is
`nvidia/waydroid-nvidia`. These are current-task context, not defaults embedded in scripts.
`WAYDROID_A17_WS` otherwise defaults to the release checkout's parent.
`WAYDROID_VENDOR_IMAGE` can explicitly select a separately validated image.
`--assets-dir` and `--package-dir` select local output/package directories.

Local packaging requires a complete source/bundle workspace, a reviewed PKGBUILD,
Python 3, zstd, GNU tar/coreutils, makepkg and updpkgsums (pacman-contrib).
GitHub metadata/checksum preparation additionally requires authenticated `gh`, jq and curl.
Installation needs working sudo authentication, pacman, Waydroid and a real supported host/guest.
Do not install or publish just to test these helpers.

All `gh` publication commands must use `--repo "$TARGET"` or an explicit
`repos/$TARGET/...` API path. Never infer the target from the current directory or remote.
Scripts reject `cagedbird043/waydroid-a17-nvidia` unless **both**
`--repo cagedbird043/waydroid-a17-nvidia` and `--allow-original-repo` are supplied.
An environment variable alone cannot bypass this guard.
The trusted PKGBUILD's `url` must match the selected target before any local metadata/build action.
Review its `_rel`, `source`, vendor-OTA repository argument, maintainer attribution and generated
update URLs too: upstream hardcodes the original repository in more than one place.
Keep original attribution where appropriate; do not represent yourself as the original maintainer.

## Recommended fork release architecture

1. **Build native userspace once, not during end-user installation.** Keep the ongoing Rust RM →
   NVK → nvrm dependency-ordered build, both Android ABIs, its source commits, toolchain versions,
   library hashes and reproducible records. Leave the actual host NVIDIA 620 kernel module untouched.
   Driver compatibility claims require validation against the real loaded module, not only headers
   or successful compilation.
2. **Produce a matching vendor/native pair.** The original reference assets are approximately a
   33 MiB native bundle and an 862 MiB **ext4** vendor image; verify actual sizes/hashes/filesystem
   rather than assuming EROFS. The canonical two-pass vendor build is in `waydroid-a17-build`.
   A native-only repack retaining the existing A17 Codec2 service is an **experimental candidate**
   until all matching-library, ABI, image, XML and media gates pass. Never label it a full A17 build.
   If service ABI or generated codec capabilities change, rebuild the service/XML through the
   canonical process. If a controlled repack is retained, record original image/service hashes,
   every replacement, new native identity and image metadata/properties; prove the unchanged
   service works with the new native stack and that no stale installation identity remains.
   Do not publish a new native archive alongside an unchanged image that still names the old bundle.
3. **Validate before distribution.** Verify BUILD-RECORD and all payload hashes, both ABI ELF/SONAME/
   dependencies, nvrm↔Rust linkage, image↔bundle service/native byte equality, generated XML/caps and
   filesystem-aware release gates. The extraction/gate/setup pipeline must genuinely handle ext4
   (`debugfs`/e2fsprogs), not blindly invoke EROFS-only tools. Verify the chosen system-image pairing.
   Run the matching media host tests and `waydroid-a17-test` Codec2 ByteBuffer, Surface, seccomp,
   Chrome WebCodecs/WebRTC and graphics tests on the real NVIDIA 620 host. Report exact results,
   unsupported/skipped tests and blockers honestly. Synthetic fixtures/syntax checks are not GPU acceptance.
4. **Ship prebuilt assets, not an expensive source rebuild disguised as `-bin`.** Publish the
   validated native bundle and compressed vendor image (split only if useful), checksum manifest,
   exact host/runtime payload or immutable source bundle needed for lightweight host packaging,
   matching release/build records and validation report. Keep required third-party host/guest
   dependencies at immutable versions with real hashes. A PKGBUILD may perform lightweight host
   installation/patching and metadata construction; it must not rebuild Mesa/Rust/Android during
   an ordinary binary-package installation.
5. **Pin exactly what users download.** Point project URLs and update/OTA metadata at the fork's
   immutable release tag. Put a concrete SHA-256 for **every** source entry in PKGBUILD and regenerate
   `.SRCINFO`; never use `SKIP`, mutable branches, invented hashes or missing local-only commits.
   Include an immutable full source bundle when a source revision cannot be fetched remotely.
   GitHub-generated tag archives differ from local `git archive` bytes: validate the actual URL.
   Cross-check local asset hashes against GitHub upload digests, then download/verify final inputs
   independently and run `makepkg --verifysource` plus an isolated package build.
   Hashes establish integrity against the selected release, not independent trust in its publisher.
6. **No AUR publication in this task.** Ship the checksum-pinned PKGBUILD in the repository and
   release assets, including any install file and a concrete package download/build recipe.
   The historical directory name `aur/waydroid-a17-nvidia-bin` does not require uploading anything
   to AUR. Review `provides`/`conflicts`/upgrade behavior and fork attribution as local package metadata.
   Do not ask for an AUR account or claim ownership of `waydroid-a17-nvidia-bin`.

## Release workflow

**Single-ZIP fork release (`a17-20261117-1`):** the restored `package.sh`
and `aur-publish.sh --prepare` retain the original split-image/tag-archive
layout. Do not use them to build or rewrite this release's nine-input
PKGBUILD. Its reviewed recipe consumes an immutable packaging-source asset,
one native tarball, one vendor ZIP and its OTA JSON. Generate `.SRCINFO`
with `makepkg --printsrcinfo`; verify/build in a fresh directory, then
upload the individually checksummed assets manually with `gh`.
The guarded `install-gate.sh` supports this layout and was used for the
actual 620 installation. The original split-layout workflow below is
historical guidance, not the packaging path for this tag.

1. **Build and record:** use `waydroid-a17-build`; rebuild native dependencies after driver-source
   changes. Commit source/product work only when requested, synchronize reviewed `nvidia-product/`
   and format-patch exports, and record the exact source/bundle identities. Do not touch unrelated
   changes or delete outputs/cache before the post-verification cleanup checkpoint.
2. **Document:** update user-visible features, known limitations and status. Distinguish the
   original 615-tested baseline from this fork's actual 620 test evidence. Never advertise an
   unrun gate as passed.
3. **Version and prepare locally:** `"$R/package.sh" <tag> --repo "$TARGET"` prints a plan.
   Explicit `--build` opts into local asset generation, PKGBUILD edits and makepkg.
   Its first new-tag run updates `_tag`/`pkgver`, resets pkgrel and stops for manual review/commit.
   Use signed Conventional Commits and the current primary assistant's one co-author footer
   when creating commits is authorized; do not copy the original Chinese release commit messages.
4. **Package:** rerun with `--build` after committing reviewed changes. Assets go to
   `$WAYDROID_A17_WS/nvidia/release/<tag>` unless overridden. Vendor chunks default to 5 MiB
   (`VENDOR_PART_SIZE` overrides); actual count must equal PKGBUILD `_vendor_parts`.
   Existing archives/chunks/package inputs are never silently deleted or overwritten.
   `--resplit` reuses existing compressed vendor/native archives in an asset directory that
   has no existing chunks/checksum manifest, and compares decompressed image bytes first.
   For a retry, select a fresh directory rather than deleting valuable outputs.
   The local source tar is `git archive HEAD` for preliminary testing only.
5. **Prepare rollback before installation:** inspect the actual `images_path` from Waydroid's config,
   current vendor files, `/var/lib/waydroid-nvidia/vendor-image/install.json` and package ownership.
   Preserve only files/configuration that will be replaced, plus the prior package/reinstall recipe,
   in an explicit rollback directory. Add `manifest.txt` listing paths, hashes and restore steps.
   Do not duplicate all `/data`, wipe it, or change protected image permissions.
   Protect `system.img` with read-only SHA-256 before/after; use sudo to read if needed.
6. **Install and gate, only with explicit authorization:**
   ```bash
   "$R/install-gate.sh" <pkgver>   # Plan only.
   "$R/install-gate.sh" <pkgver> --package /path/to/exact.pkg.tar.zst \
     --install --images-path /actual/configured/images --rollback-dir /prepared/rollback
   ```
   The helper refuses a nonempty vendor overlay instead of deleting debug/user files.
   Inspect and move only confirmed disposable overrides manually, preserving anything needed
   for rollback. Installation stops the user session, runs interactive pacman and setup,
   captures a unique log, checks gate/install evidence and verifies `system.img` stayed unchanged.
   `WAYDROID_VENDOR_OVERLAY` / `WAYDROID_VENDOR_STATE` customize host inspection paths;
   the operator must confirm setup uses the same actual configuration.
   Upstream expected `Release gate PASS: 22 cases + media` and
   `Installed the nvidia-prolapse vendor image <bundle>`.
   Use the actual current gate's full case inventory, not a fabricated fixed count.
7. **Regression:** start the user session, verify actual ANGLE/NVK rendering and first frames,
   run the restored test skill and scenarios affected by this change (cards, native desktop windows,
   IME, clipboard, sharing and KernelSU). Save private logs and a concise public validation report.
8. **Sign/tag/push only when authorized:** verify SSH signing is configured and available first.
   Create the signed Conventional Commits and requested tag manually; verify the destination.
   Prefer explicit destinations such as `git push "https://github.com/$TARGET.git" HEAD <tag>`.
   Do not let helpers create commits or silently push an original remote.
9. **GitHub draft:** create the draft separately from uploads, upload one file at a time so one
   failed upload cannot discard the whole release, and inspect hashes before publication.
   ```bash
   gh release create <tag> --repo "$TARGET" --draft --title "vendor <tag>" --notes-file <notes>
   gh release upload <tag> /path/to/one-asset --repo "$TARGET"
   ```
   Replacing a failed upload with `--clobber` needs deliberate confirmation that the existing
   asset is the intended replacement. Reference format:
   [references/release-notes.md](references/release-notes.md).
   Query the **selected tag**, not every draft:
   ```bash
   gh api "repos/$TARGET/releases/tags/<tag>" \
     --jq '.assets[] | [.name, .size, .digest] | @tsv'
   ```
   Compare each digest to local SHA-256, check all part indices and native identity, and ensure
   manifest/native plus parts give `_vendor_parts + 2` vendor-related assets. Account separately
   for source bundles, reports, APKs or optional DKMS packages; never imply the NVIDIA host module
   was rebuilt. All fixed URLs must resolve to the actual release's assets.
10. **Validate the exact remote inputs:** `aur-publish.sh <tag> --repo "$TARGET" --prepare` calculates
    asset digests via GitHub API, downloads generated archives when needed, writes real hashes and
    `.SRCINFO`, and retains checksum evidence. It can prepare from a draft but does not publish.
    Review the trusted PKGBUILD before sourcing it; its shell code executes on the host.
    Download the exact final tag/archive URLs into a separate test package directory, verify source
    checksums and build there without reusing local `git archive` as proof. Keep caches until
    the final remote-download package build and uploaded assets have been verified.
    Validate final package contents and installation as above. Only then authorize:
    `gh release edit <tag> --repo "$TARGET" --draft=false --latest`.
11. **Deliver the PKGBUILD, not an AUR upload:** include the final PKGBUILD and required install
    file in the repository/release assets, verify they reference the fork's immutable assets,
    and document `makepkg --verifysource` / `makepkg -si` for users with the usual Arch build tools.
    No AUR account is required. The historical helper's push mode refuses even `--publish` without
    a separate `--enable-historical-aur` acknowledgment, plus explicit owned package/checkout/branches.
    That mode is outside this task and must not be invoked. The original package additionally
    requires `--allow-original-aur`, which would still not prove ownership.
12. **Report:** exact gate/regression results and skipped checks, asset identities/hashes,
    relevant commit/tag identities, package source URLs, actual release link if published and
    rollback instructions. If blocked, stop short of publication and report the blocker.

## Release-gate failures

| Error | Cause | Action |
|---|---|---|
| `nvrm (x86_64) was linked against libnv_bionic_native.so …` | Rust replaced without rebuilding nvrm | Rebuild the dependency chain, then matching vendor/bundle |
| `the installed package carries release bundle …, the vendor image …` | Updated package without matching setup/image | Verify intended assets, then authorized setup |
| `has no ELF64 …/linker64` | AUR prepare's git apply silently skipped paths inside a git repository | Preserve `GIT_CEILING_DIRECTORIES` in PKGBUILD |
| Service mismatch or `media/xmlgen-check` failure | Image service/XML differs from bundle | Canonical two-pass build; do not hand-edit hashes to fake success |
| Missing `media/tools/check-xmlgen-elf.py` | Package omitted a shared ELF gate helper | Fix installer file list and rebuild package |
| EROFS extraction error on original vendor | Input is ext4, not EROFS | Detect filesystem and use supported ext4 extraction/gate logic |
| Historical rc10 dependency download TLS failure | Network failure | Reuse verified immutable workspace copies; never skip checksums |

## Cleanup: after upload AND remote-input package-build verification

The latest user instruction supersedes the earlier request to retain expensive caches:
**after the release is uploaded and the PKGBUILD download/build is verified, remove even expensive
local outputs/cache created by this task**. The current skill-restoration agent is not authorized
to perform publication or cleanup; this is the later release operator's checklist.

Before that checkpoint, preserve ongoing build products, toolchains and caches. Never clean paths
while the native build is using them. Afterward, inventory exact paths, ownership, sizes, creation
provenance and active references. Eligible task-created items include native/Android build outputs,
Mesa generated trees, downloaded toolchains, isolated Cargo/ccache caches, task-specific container
images, duplicate archives/extractions, failed downloads and temporary evidence after retaining the
published validation record. Do not delete preexisting/shared caches just because this build used them.
For generated git worktrees, inspect/prune only their corresponding metadata using the proper git
worktree procedure; never destroy source changes or blindly remove worktree metadata.

Always preserve installed runtime and configured system/vendor images, all Android user data,
KernelSU/runtime state, source checkouts and modifications/patches, package metadata, relevant git
history, and any rollback artifact still needed for the installed deployment. Verify runtime does
not reference a candidate build directory before deleting it. Upload and verify canonical release
artifacts first so local cleanup does not lose the only valid copy.

The helpers do not automatically delete anything: cleanup is a separate reviewed action. Use
explicit task-created paths only; no broad `git clean`, indiscriminate container prune or deletion
of workspace/source roots. If root-only artifacts cannot be removed without interactive sudo,
list their **exact reviewed paths** and give the user narrowly scoped cleanup commands in the
final report instead of weakening sudoers, changing unrelated permissions or bypassing authentication.
Do not provide a runnable broad deletion command before that inventory and verification checkpoint.

If pacman owns the deployment, use the package/setup workflow rather than bypassing package
ownership with `scripts/reinstall-vendor.sh` / `install.sh`. Upstream's machine used the original
package name; discover this fork's actual package/configuration instead of assuming it.
