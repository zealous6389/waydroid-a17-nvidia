---
name: waydroid-a17-build
description: Build this project's Waydroid Android 17 NVIDIA vendor image and its pieces — individual vendor modules (hwcomposer, gralloc, Codec2 service), the Rust RM backend / NVK / nvrm native stack, the native bundle and its pin, and the full two-pass vendorimage — and keep this release repository and patches in sync with the source repositories. Use for compile, rebuild, bundle, stage-product, Soong, patch application or patch-export tasks.
---

# Build

Restored from `cagedbird043/waydroid-a17-nvidia` commit
`28955ede2c365c6822984e64c68b58dda673e285`, with English documentation and path/safety checks.
The performance results below are historical upstream observations, not validation on this fork's machine.

## Workspace

Upstream kept this release repository (`publish`) inside `~/Projects/waydroid-a17`.
Sources and outputs belong to that separate workspace, not this repository. Scripts use
`$WAYDROID_A17_WS`, defaulting to this repository's parent directory. This fork's standalone
checkout is not automatically a complete workspace: set `WAYDROID_A17_WS` explicitly if needed.
Missing prerequisites are errors, not successful builds.

| Workspace path | Contents | Corresponding release-repository path |
|---|---|---|
| `src/` | LineageOS 24.0 + WayDroid-ATV tree (repo) | `patches/<repository>/` |
| `src/hardware/waydroid`, etc. | Branch `nvidia-a17` (`local-build` for the device tree) | `patches/hardware_waydroid/`, etc. |
| `nvidia/waydroid-nvidia` | Branch `a17-local`: Rust RM, NVK, nvrm, Codec2 media sources, Waydroid host patches | `patches/waydroid-nvidia/` |
| `nvidia/product` | `vendor/nvidia-prolapse` product layer (git, main) | `nvidia-product/` (rsync mirror) |
| `nvidia/build/native-*` | Native bundles (`BUILD-RECORD.json` + payload) | Release assets |
| `scripts/` | `build.sh`, `stage-product.sh`, etc. | `scripts/` (identical copies; run from the workspace) |

See [references/patch-bases.md](references/patch-bases.md) for patch bases and counts at the restored upstream revision.
Native builds require Podman and the prebuilt `localhost/nvk-native-a17` image
(`WAYDROID_NATIVE_IMAGE` overrides its name), the source workspace, Android NDK r29,
and the existing offline Cargo/dependency cache. Full vendor builds additionally need the
Android source tree, build container and workspace build scripts. Rust/Cargo alone are not sufficient.

`scripts/build.sh` defaults to Ninja, 4 build jobs, a 4-CPU time quota and affinity,
a 32 GiB hard memory limit, no extra swap, nice 10 and idle I/O. Override explicitly with
`WAYDROID_BUILD_EXECUTOR`, `WAYDROID_BUILD_JOBS`, `WAYDROID_BUILD_CPUS`,
`WAYDROID_BUILD_CPUSET`, and `WAYDROID_BUILD_MEMORY`.
Affinity uses `taskset` inside the container: the upstream rootless cgroup did not expose the
cpuset controller, so `--cpuset-cpus` was unavailable. Blueprint's visitor limit is
`runtime.NumCPU()*2`; a CPU time quota alone does not limit the CPU count seen there.

Go defaults to `GOMEMLIMIT=10GiB` and `GOGC=10`, overridden by
`WAYDROID_BUILD_GOMEMLIMIT` / `WAYDROID_BUILD_GOGC`. The `build_soong` patch forwards both
explicitly to `soong_build`, launched with `env -i`; Go's soft target is not an RSS limit.
Full Soong analysis on upstream's machine still hit a 24 GiB hard limit, so these defaults
are not proof that full-tree builds are solved. Siso graph scheduling alone once used about
18 GiB RSS, causing Java compilation in a 20 GiB container to be OOM-killed; retain Ninja
and resource limits for normal desktop use.
After OOM, inspect the cgroup peak and actual phase first. Do not automatically keep increasing
the budget, or substitute small targets such as aapt2 for vendor acceptance.

### Cached incremental builds with frozen inputs

Only consume the combined graph directly with the same prebuilt Ninja version after the existing
Soong/Kati graph has completed successfully and definitions/configuration are frozen.
First verify that graph depfile inputs exist and are unchanged, used/available environments match,
glob results are unchanged, and the Kati graph contains the current bundle identity.
Keep the same container, absolute mount paths and working directory, restoring the JSON environment
from `out/soong/ninja.environment`.
Follow `build/soong/ui/build/ninja.go` for arguments, retaining keepdepfile/keeprsp,
duplicate-edge checks, and missing-depfile/output checks. Build the actual header output first,
then `vendorimage`, both under hard resource limits.
This branch has no `m --skip-soong`; `--config-only` does not perform an equivalent build.
This is a cached incremental build, not a reproducible graph-regenerating build. Regenerate the
graph after BP/MK, glob or product-parameter changes; never manipulate timestamps, remove
dependencies or shrink the graph to evade that requirement.

Historical upstream results: with 46 GiB host memory available, a 32 GiB hard limit and one Ninja job,
the cached incremental build produced the actual `framework-minus-apex-headers` output,
with cgroup peak `26567045120` bytes and no OOM. The same cached compilation with 24 GiB and 4 jobs
was killed. Leave host headroom when selecting a budget; this is not evidence that cold Soong
analysis passed.
A usable cached graph does not mean all target outputs are cached: `vendorimage` still had
37,805 actions, of which a single job completed only 7,697 normal compilation actions within
one hour. Set long-build lifetimes according to actual action counts, retaining hard resource limits.
Do not repeatedly interrupt healthy compilation with a one-hour external timeout or remove real
dependencies such as SwiftShader/LLVM to shrink the graph.
The final upstream cached `vendorimage` completed with 4 jobs, 4 CPUs and a 32 GiB limit,
`memory.peak=34359738368`, `oom=0`, `oom_kill=0`; the Codec2 service and both-ABI Rust/NVRM outputs
were byte-identical to the bundle.

## Individual modules (fast iteration)

```bash
export WAYDROID_A17_WS=/path/to/complete/workspace
WS=$WAYDROID_A17_WS
cd "$WS"
scripts/stage-product.sh   # After changing nvidia/product or media sources.
scripts/build.sh lineage_nvidia_waydroid_x86_64-cp2a-userdebug <module>   # e.g. hwcomposer.waydroid
```

Outputs are in `src/out/target/product/waydroid_nvidia_x86_64/vendor/`. Install to the corresponding
path under `/var/lib/waydroid/overlay/vendor/`, then restart the session (the `waydroid-a17-test` skill).
Overlay takes precedence over the vendor image; inspect and remove test overrides before release.

The Codec2 service module is `android.hardware.media.c2@1.2-service-nvprolapse`.
`stage-product.sh` copies its sources from `nvidia/waydroid-nvidia/nvidia-prolapse/media/{core,c2}`
to `src/vendor/nvidia-prolapse/media-src/`.
Host unit tests: `make -C nvidia/waydroid-nvidia/nvidia-prolapse/media test`;
real GPU tests from that media directory: `make realtest-all` and `make realenc`.

## Native stack (after changing driver-source/)

Commit in `nvidia/waydroid-nvidia` first, then run from this release repository's root:

```bash
S=.agents/skills/waydroid-a17-build/scripts
$S/rebuild-native.sh               # Rust RM → NVK → nvrm (32/64 bit) → nvc2-xmlgen; upstream observed ~2 minutes.
$S/rebuild-native.sh --rust-only   # Rust libraries only, for testing; not releasable.
```

`nvc2-xmlgen` is a non-default `xmlgen-cli` feature binary of the RM crate and calls only the
RM C ABI dynamically. Build RM first, then use Make's Cargo adapter target (Cargo decides
incrementality on every call):

```bash
make -C "$WS/nvidia/waydroid-nvidia/nvidia-prolapse/media" xmlgen \
  RUST_PROFILE=release CARGO_TARGET_DIR="$WS/nvidia/waydroid-nvidia/build/nv-rm-rust" \
  NV_C2_RM_LIB_DIR="$WS/nvidia/waydroid-nvidia/build/nv-rm-rust/release"
# Bionic: same target directory, Android RM, explicitly selecting the NDK C linker (not clang++).
make -C "$WS/nvidia/waydroid-nvidia/nvidia-prolapse/media" xmlgen-android \
  RUST_PROFILE=release CARGO_TARGET_DIR="$WS/nvidia/waydroid-nvidia/build/nv-rm-rust" \
  NV_C2_RM_LIB_DIR="$WS/nvidia/waydroid-nvidia/build/nv-rm-rust/x86_64-linux-android/release" \
  RUST_LINKER="$WS/nvidia/waydroid-nvidia/build/hwcomposer-work/ndk/android-ndk-r29/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android33-clang"
```

Both targets check ELF64, RM dynamic dependencies and caps/XML imports. Android output additionally
requires linker64 and must not depend on GNU libc or contain development-machine RUNPATHs.

nvrm records the hash of the Rust library it links. The gate compares that with the payload's
`libnv_bionic_native.so`. Replacing Rust without rebuilding nvrm makes `waydroid-nvidia-setup`
report `nvrm (x86_64) was linked against libnv_bionic_native.so …`.

### Updating the Mesa pin

Changing `PIN` in `mesa/build.py` does not automatically switch existing `build/mesa-rm-source`
and `build/mesa-gl-source`. These generated source trees' git worktree metadata uses absolute
`/work` paths: operate only inside the native container, with `nvidia/waydroid-nvidia` mounted
at `/work`. Save existing diffs first, confirm changes come from the canonical patch stack,
then fetch the new tag.
Use `git cat-file -e <PIN>^{commit}` to confirm the object was downloaded, not merely
`rev-parse --verify`, which resolves a hash.
Switch both generated trees to the new pin, clean generated overlays, then run
`build.py --prepare-only` and `build.py --gl --prepare-only` to verify the full patch stack applies.
Rebuild `--target host --rust-profile release` first, so Android builds use matching
`mesa_clc` / `vtn_bindgen2`, then run the complete `rebuild-native.sh`.
The bundle's top-level `mesa_commit` comes from actual nvrm build records for both ABIs;
packaging refuses mismatched pins.

## Complete vendor image (two passes)

The gate requires the image's Codec2 service to match the bundle byte-for-byte, while that service
must itself be built against the bundle:

```bash
.agents/skills/waydroid-a17-build/scripts/build-vendor.sh \
  --base nvidia/build/<previous-bundle> --out nvidia/build/<new-bundle> \
  --release v0.2.0-rc11-a17-<suffix> --note "<changes in English>"
```

The sequence is: assemble bundle (keep old service) → stage → build service → reassemble bundle
with new service and update `nvidia/product/vendor/nvidia-prolapse/native-bundle.json` →
stage → `vendorimage` → byte-for-byte checks. Upstream observed about 5 minutes with warm ccache.
Use `make-bundle.py` in the same directory for standalone bundle creation.
Output must be workspace-relative and strictly below `nvidia/build`; existing bundles require
explicit `--replace`. The two-pass wrapper replaces the bundle it just created on its second pass.
Commit the pin in `nvidia/product` after completion.

## Synchronizing this release repository

- Product mirror: inspect both directories first; `rsync -a --delete --exclude=.git "$WS/nvidia/product/" nvidia-product/`
  removes destination files absent from the workspace. Do not run it without confirming the intended scope.
- Patches: in each source repository, use
  `git format-patch -q --start-number <N+1> -o <release-repository>/patches/<repository>/ <last-exported-commit>..HEAD`,
  continuing existing numbering. Update the reference counts.

## Do not

- Rewrite commit `eec39aa` or its ancestors in `nvidia/waydroid-nvidia`:
  `BUILD-RECORD` records it, and `install.sh --source` requires a descendant.
- Touch generated artifacts outside `src/out` to "fix" an Android build.
  Inspect `/tmp/c2svc-build.log` and `/tmp/vendorimage-build.log` on failure.
- Build a full vendor image without first building an individual module: Soong errors surface
  faster in a single-module build.
