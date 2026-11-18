# NVIDIA open 620.70.06 bring-up

Published as
[`a17-20261117-1`](https://github.com/zealous6389/waydroid-a17-nvidia/releases/tag/a17-20261117-1).
The exact tested package, native/vendor assets, source bundle and checksums
are available there. See the
[public-download/build verification and scoped cleanup record](release-a17-20261117-1-verification.md)
for the post-publication result.

## Scope

Port the exact RM ABI profile proposed in
[Shiro836/nvidia-prolapse#1](https://github.com/Shiro836/nvidia-prolapse/pull/1),
not a driver-version bypass. Unknown releases must still fail closed.

The public 620.70.06 headers change two allocation structures:

| Structure | 615.78.08 | 620.70.06 |
|---|---:|---:|
| `NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS` | 28 bytes | 32 bytes |
| `NV_CTXSHARE_ALLOCATION_PARAMETERS` | 12 bytes | 16 bytes |

The channel group's `internalFlags` moves from byte 24 to byte 28.
The newly reserved bytes must remain zero. Do not change the canonical
615 profile or assume all future 620 releases have this ABI.

## Machine and baseline

Test machine: RTX 4060 Ti (8 GiB), CachyOS, kernel `7.3.4-1-cachyos`,
KDE Wayland, NVIDIA **open** kernel module **620.70.06**.
The driver was already installed; this work does not replace or downgrade it.
No Waydroid installation, `/var/lib/waydroid`, or Android user data existed
at the start.

Baseline source: `Shiro836/waydroid-nvidia`
`29ffa3a237b0d79a751748bd9bb82c50dd577808` plus this repository's
patches `0001`–`0075`, applied in filename order.

- CPU Rust tests: **270 passed, 51 ignored**.
- Direct `nv-native-check --gpu-map`: correctly reproduced
  `NVIDIA 620.70.06: no exact public ABI profile`.
- Independent public-header assertions for both changed structures:
  **passed with `cc -m32` and `cc -m64`**, against NVIDIA OGKM tag
  `620.70.06`, commit `e6a2e01579fbbd1ca2ed43fef2ee2589e9bd8bd9`.

These baseline/header results are **not** confirmation of Android graphics,
video, or a successful full release gate. Runtime results must be recorded
separately.

## Installed candidate gate

The proper checksum-pinned fork PKGBUILD built locally with all nine
inputs verified. Package `20261117.1-1` was installed by the operator.
Setup verified all 19 mapped native binaries against the bundle and
passed **22 cases + media** on loaded NVIDIA kernel module `620.70.06`,
covering Android x86_64/i686 compute, graphics, interop, ANB, ASTC,
ETC2 and GL probes, plus media XML generation/validation.
The two gradient probes are judged by their expected output, not their
exit code; the gate reports them as passed with exit 1.

Evidence: `/tmp/opencode/wd-setup.QMi3PS.log` and
`/var/lib/waydroid-nvidia/gate-20261117-232950/`.
Installed bundle: `v0.2.0-rc11-a17-620-20261117`.
The protected system-image SHA-256 still matches the pre-install value.
Setup enabled `waydroid-container.service` at boot; the initial scaffold
had it disabled. Publication is tracked separately from this install checkpoint.

### Running Android framework results

The user session reached `Android with user 0 is ready`. SurfaceFlinger
reports `Google Inc. (NVIDIA), ANGLE` with Vulkan on
`NVIDIA GeForce RTX 4060 Ti (NVK NV196)`, OpenGL ES 3.2.
This is an actual guest renderer query, not a host Vulkan result.

The restored English integration scripts passed on the installed image:

| Check | Result |
|---|---|
| ByteBuffer AVC / HEVC / VP9 / AV1 decode | Each 60 frames, 1280×720, zero bad buffers |
| AVC running flush / queued-work destruction | Passed; replay produced 60 frames |
| Malformed bitstream | Rejected, EOS, zero pictures |
| AVC / HEVC / AV1 encode | Each 60 pictures in / 60 out; host FFmpeg clean and ffprobe confirms 60 frames |
| PRIVATE Surface AVC / HEVC / VP9 / AV1 | Each 60 inputs / outputs / images, EOS, zero errors, clean destruction |

Evidence: `/tmp/opencode/codec-evidence.QsF4z1` (`result.exit = 0`)
and `/tmp/opencode/surface-evidence.kUQnpK` (all four client exits 0).
These confirm framework Codec2 integration with the retained A17 service
and new userspace native stack on NVIDIA 620.70.06.

After `waydroid show-full-ui`, the operator confirmed that Android
visibly renders and appears to work correctly. This is operator visual
confirmation, not an independently inspected screenshot or a performance
benchmark. The operator's current-boot kernel-journal query found no
matches for `NVRM: Xid|nvidia.*(fault|timeout)`.

Guest Chrome is absent (`pm list packages | grep -i chrome` returned no
matches), so Chrome WebCodecs/WebRTC is untested. Guest
`/system/bin/strace` exists, but seccomp syscall tracing has not been run.
VP9 superframe guest cases, KernelSU and broader desktop integrations
are also unvalidated in this fork run. Strict Clippy remains a preexisting
failure, as below. These results establish tested GPU/media functionality,
not exhaustive correctness, stability or performance.

## Patched host evidence

- CPU Rust tests: **272 passed, 51 ignored**.
- Full independent C oracle: **76 layouts, 203 constants, 1,001 checks
  per ABI passed for both m32 and m64**, including both new reserved
  fields. Consumed NVIDIA header blobs are verified against the pinned
  commit; emitted objects, values and provenance are retained under
  `/tmp/opencode/nvidia-620-evidence/full-profile-final/`.
- Direct GPU VA mapping and VRAM CPU round trip: **passed**, 16,384 words
  checked on PCI `0000:01:00.0`, device `10de:2803`, driver 620.70.06.
- Eleven explicitly enabled hardware fixtures passed: RM event ownership,
  cross-client opaque FD memory, kernel fences, typed VA kinds, repeated
  CPU mappings, block-linear metadata, pool allocation attributes, exporter
  completion, transactional full queue, 3,000-frame slot reuse, and bounded
  teardown behind an unsignaled gate.
- The standalone multiqueue shader fixture first lacked the NAK compiler.
  After building it, that fixture explicitly rejected Ada (`SM 0x809`)
  because its experimental shader path requires Blackwell (`SM 0xa04`).
  This is **not** a passed multiqueue test. The Ada runner excludes that
  known architecture-specific fixture; actual Vulkan multiqueue must be
  tested through the matching Mesa driver, not by weakening its guard.
- Strict Clippy on the host Rust 1.100 toolchain fails on existing
  media/style diagnostics; the full host runner therefore does **not**
  currently report an overall pass. An isolated baseline comparison
  confirmed the same multiset of **60 diagnostics** before and after the
  ABI patch (both exit 101).
- Packaging regression tests in a disposable pytest environment:
  **38 passed, 1 skipped**. These test gate/install logic, not GPU rendering.
- Real host NVDEC decoding: **9/9 passed**, 60 pictures each, zero
  mismatching pictures against FFmpeg references. H.264, HEVC, VP9 and AV1
  NV12; H.264/HEVC/VP9 YV12; HEVC Main10 and VP9 profile 2 P010.
- Real host NVENC encoding: **15/15 passed**, covering AVC profiles,
  HEVC/AV1, NV12/NV21/I420/RGBX/BGRX, decoded frame counts and PSNR checks.
  The rate-change regression also passed.
- The separately executed NVDEC engine-capability hardware fixture passed.
- Final supported-Ada host fixture run: **13/13 passed**, including 540
  RGB-to-NV12 cases byte-exact against the CPU reference. Strict Clippy
  still makes the combined runner exit nonzero for the baseline diagnostics.
- Actual Mesa Vulkan multiqueue test: **passed**, including a serial rerun.
  The renderer was `NVIDIA GeForce RTX 4060 Ti (NVK NV196)`,
  Mesa `26.2.6 (git-8e87a503eb)`, with two graphics queues and eight
  compute queues. All six graphics/compute queue combinations passed
  eight device-lifecycle repetitions each, including ownership transfers.

Raw logs: `/tmp/opencode/nvidia-620-evidence/patched-host/` and
`/tmp/opencode/nvidia-620-evidence/patched-hardware/`; host codec log:
`/tmp/opencode/nvidia-620-evidence/host-codecs.log`.

The first host codec attempt failed because `/dev/dma_heap/system` was
root-only. The user granted a **temporary per-user ACL**, not a permanent
udev rule, before the successful rerun. Original ACL:
`/tmp/opencode/nvidia-620-evidence/dma-heap-system-before.acl`.
Restore it after host media testing with:

```bash
sudo setfacl --restore=/tmp/opencode/nvidia-620-evidence/dma-heap-system-before.acl
```

This node is recreated on reboot; verify the node and saved ACL before
restoring during a later session. A permission failure is not evidence of
a codec/driver regression.

## Repeatable host checks

After applying every patch in `patches/waydroid-nvidia/` to the base above:

```bash
bash scripts/test-nvidia-driver.sh \
    /path/to/waydroid-nvidia \
    /path/to/new-results-directory \
    /path/to/open-gpu-kernel-modules-620
```

The results directory must not already exist. It retains the environment,
source diff/hashes, individual logs, and final exit status. The header
checkout is optional; if supplied, its commit and tracked cleanliness are
checked before compiling both CPU ABIs.

The runner performs CPU tests, strict Clippy, direct RM mapping, and a
bounded, serial set of explicitly named hardware fixtures. A filter matching
zero tests is an error. It does not install files, start services, alter the
driver, or claim Android validation. The historical standalone
`nv-native-check --copy/--compute` paths hardcode Blackwell classes and are
not appropriate Ada validation.

Use the restored `.agents/skills/waydroid-a17-test/` guest tests after the
matching native stack is built and installed. Never swap only
`libnv_bionic_native.so`: NVK and nvrm record its hash and must be rebuilt
with it. A candidate pin may be prepared for image assembly, but do not
publish it or a release until the matching bundle/vendor image has passed
the release gate.

## Work locations and cleanup

All bring-up downloads/builds are outside the release checkout:

| Path/resource | Purpose |
|---|---|
| `~/Projects/waydroid-a17-nvidia-work/` | Isolated disk-backed workspace, source and build products |
| `/tmp/opencode/waydroid-nvidia-620` | Compatibility symlink to that workspace's source checkout |
| `/tmp/opencode/open-gpu-kernel-modules-620` | Read-only public header oracle |
| `/tmp/opencode/nvidia-620-evidence` | Baseline package inventory, images, evidence |
| `/tmp/opencode/aur-waydroid-a17-620` | Disposable baseline A17 package build |
| `/tmp/opencode/nvidia-620-pytest` | Disposable packaging-test Python environment |
| Podman image `localhost/waydroid-nvidia-620-build` | Isolated native build toolchain |

The final cleanup target is **after** publishing the fork release and
verifying a fresh PKGBUILD download/build against its checksums. At that
point remove this experiment's local build outputs, caches, downloads,
staging trees and named Podman build image—even the expensive outputs.
The release must retain the built assets and reproducible source/provenance
first. Keep the installed runtime and Android user data.
Do **not** run a global image/system prune. No build container is intended
to remain running.

No AUR account or AUR publication is required: distribute the release and
PKGBUILD through `zealous6389/waydroid-a17-nvidia`. The PKGBUILD must download
prebuilt native/vendor assets, not rebuild Mesa or require Podman/Rust.

The initial package list is
`/tmp/opencode/nvidia-620-evidence/packages-before.txt`. To review additions:

```bash
LC_ALL=C comm -13 \
    <(LC_ALL=C sort /tmp/opencode/nvidia-620-evidence/packages-before.txt) \
    <(pacman -Qq | LC_ALL=C sort)
```

Review that list before removing anything: packages installed for unrelated
work later will also appear. Do not automatically remove all additions or
all orphans. Keep runtime dependencies while Waydroid is still installed.
Host installation, activation, and rollback details must be recorded here
before changing the host. Do not remove Android data as an incidental part
of reverting a driver experiment.

### Planned package-managed Android test scaffold

The unmodified `20261111.1-1` A17 package was built with the existing
PKGBUILD; every download passed its pinned SHA-256 check. Installing this
baseline is only a test scaffold, **not** installation of the 620 fix.
The repaired native stack must be staged separately before claiming support.
Use the VANILLA Android 17 image (no Google login needed), release
`WayDroid-ATV/waydroid-builds/20261017`, SHA-256
`4c7e13a39bcbecc598726c959c6f4eb2aa8a89e67f2902581ab250ec6a75184b`.

The scaffold installation will add package-owned host files and initialize
`/etc/waydroid-extra/images` and `/var/lib/waydroid`. No service needs to be
enabled yet. To undo the package installation later, stop the user session
and container, disable the container service if this test enabled it, and
remove **only** `waydroid-a17-nvidia-bin` with `pacman -R`. Its package hook
handles a configured NVIDIA vendor restoration. Preserve the new images and
Android data for retesting, or explicitly review and remove those
test-created directories after all mounts are gone. Do not use `pacman -Rsc`
or a broad recursive deletion.

The user installed and initialized this scaffold. `waydroid init` started
`waydroid-container.service`; the user session was still stopped when
checked. The matching NVIDIA render node is `/dev/dri/renderD129`;
`renderD128` is the integrated GPU. Discover by PCI path on other hosts.

### Native build isolation

`/tmp` is a 16 GiB tmpfs on this machine, unsuitable for cold native build
outputs. The source checkout was moved to
`~/Projects/waydroid-a17-nvidia-work/nvidia/waydroid-nvidia`; its original
`/tmp/opencode/waydroid-nvidia-620` path is only a symlink. The separate
workspace also holds `nvidia/build/native-baseline` and a private copy of the
product layer. A matching candidate bundle pin is prepared in both product
copies; it is not yet a published, validated release.

The reconstructed 75-patch baseline and new ABI changes are separate
SSH-signed commits (`67c5f68` and `eeb3a41`) in that disposable source
checkout, branch `a17-nvidia-620`.

For a cold native-only rebuild, after building the image:

```bash
bash scripts/build-waydroid-native.sh \
    "$HOME/Projects/waydroid-a17-nvidia-work/nvidia/waydroid-nvidia"
```

This rebuilds **Waydroid userspace libraries**, not NVIDIA's kernel module,
host driver, or firmware. The wrapper uses a rootless disposable Podman container, four jobs and an
8 GiB memory/swap-total limit by default. It rebuilds host NAK, both-ABI
RM/NVK/nvrm and the Android XML generator, using committed source and
read-only input images. It does not install or activate the results.
`WAYDROID_NATIVE_IMAGE`, `WAYDROID_NATIVE_JOBS` and
`WAYDROID_NATIVE_MEMORY` are explicit overrides; `WAYDROID_NATIVE_CPUSET`
controls affinity. Logs stay under the
source checkout's `build/nvidia-620-logs/`.

The real Mesa multiqueue probe, unlike the Blackwell-only standalone RM
shader fixture, can be repeated after this build:

```bash
SOURCE="$HOME/Projects/waydroid-a17-nvidia-work/nvidia/waydroid-nvidia"
LD_LIBRARY_PATH="$SOURCE/build/nv-rm-rust/release:$SOURCE/build/nvk-host/src/nouveau/vulkan" \
  timeout 180s "$SOURCE/build/native-vulkan-multiqueue-host" \
  "$SOURCE/build/nvk-host/src/nouveau/vulkan/libvulkan_nouveau.so"
```

The cold build initially exposed two missing-workspace prerequisites:
the old `hwcomposer` extraction step only understands ext4, while this
Android 17 system image is EROFS with packed APEXes; and Mesa's deliberately
offline Cargo invocation needs the RM crate cache seeded first. The wrapper
now reuses the existing release gate's EROFS/APEX reader for both runtime
closures and runs locked `cargo fetch` before offline compilation. It does
not change filesystem formats or bypass runtime checks.

### Local test image and package

There is no complete Android source workspace on this host. A **local,
native-only test repack** is therefore distinct from a full Soong
`vendorimage` rebuild:

- `scripts/repack-nvidia-test-image.py` validates the new bundle's recorded
  baseline, clones the ext4 vendor image, and mounts **only the clone**.
  It updates the mapped native prebuilts and two NVIDIA identity properties,
  retaining the original A17 modules, Codec2 service, timestamp, inode
  permissions and xattrs. It then unmounts, runs read-only fsck, and verifies
  every mapped binary against the bundle. It never activates an image.
- `scripts/package-nvidia-test.py` validates the image/bundle and produces
  an offline candidate PKGBUILD for version `20261117.1-1`. It keeps
  the baseline's host integration, dependencies and uninstall hooks, and
  replaces only the native bundle and vendor ZIP/channel. The channel
  points to the installed local file, not an imaginary public release.
  Generating/building this package neither installs it nor establishes a
  GPU pass.
- **24 helper tests passed**, including output-overlap rejection, identity
  failures, permission/xattr preservation, and retaining a still-mounted
  directory rather than recursively deleting it after an unmount failure.

The pre-activation scaffold checkpoint is
`~/Projects/waydroid-a17-nvidia-work/evidence/scaffold-before/`: the original
vendor image, `waydroid.cfg`, service state and checksums. Keep it and the
original `20261111.1-1` package until the experiment is removed or accepted.
Never restore an image while the container has it mounted.
