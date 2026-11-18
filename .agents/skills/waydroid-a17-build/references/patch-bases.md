# Patch bases

Restored from upstream commit `28955ede2c365c6822984e64c68b58dda673e285`.
The `waydroid-nvidia` count includes this fork's exact NVIDIA 620.70.06 ABI patch;
the other counts remain the historical upstream snapshot.

`patches/<directory>/` contains `git format-patch` output for each repository's local branch
on top of the following bases. Apply with `git am` in numbered order.

| Directory | Source-tree path | Upstream | Branch | Base | Patches |
|---|---|---|---|---|---|
| `hardware_waydroid` | `hardware/waydroid` | https://github.com/WayDroid-ATV/android_hardware_waydroid | lineage-23.0 (ATV manifest) | `3af187c1de51` | 34 |
| `external_minigbm` | `external/minigbm` | https://github.com/WayDroid-ATV/android_external_minigbm | lineage-24.0 | `5f5797cacd14` | 9 |
| `hardware_interfaces` | `hardware/interfaces` | https://github.com/WayDroid-ATV/android_hardware_interfaces | lineage-24.0 | `1b0bcde9a85b` | 1 |
| `external_wayland-protocols` | `external/wayland-protocols` | https://android.googlesource.com/platform/external/wayland-protocols | AOSP | `2dabfe6879b2` | 3 |
| `device_waydroid_waydroid` | `device/waydroid/waydroid` | https://github.com/WayDroid-ATV/android_device_waydroid_waydroid | lineage-24.0 | `ce2f57ee2768` | 4 |
| `vendor_waydroid_init` | `vendor/waydroid/init` | https://github.com/WayDroid-ATV/android_vendor_waydroid_init | main | `e97b43d97f70` | 2 |
| `waydroid-nvidia` | `../nvidia/waydroid-nvidia` | https://github.com/Shiro836/waydroid-nvidia | public-test | `29ffa3a237b0` | 76 |
| `build_soong` | `build/soong` | https://github.com/LineageOS/android_build_soong | lineage-24.0 | `d40efa6ca919` | 1 |

The AUR package applies `waydroid-nvidia` patches with `git apply` in `prepare()` because the patches
contain binary test bitstreams. `GIT_CEILING_DIRECTORIES` is required; otherwise makepkg inside a
git repository can silently skip every path.

From scratch: `podman build --build-arg ROOT="$WS" -t localhost/waydroid-a17-build container`
(the build container mounts the workspace at its original path; Mesa cross-compilation uses
the tree's lld) → `scripts/sync.sh` → `apply-waydroid-patches` → `git am` in each repository →
`scripts/stage-product.sh` →
`scripts/build.sh lineage_nvidia_waydroid_x86_64-cp2a-userdebug vendorimage`.
Sources occupy about 100 GB.

## Preserved system-security sources

These series preserve ported sources, not a built, signed and deployed system image. They do not
represent the complete November 2026 ASB and do not raise the SPL.
At the restored upstream revision, the running system was still an ATV image with SPL `2026-10-01`.
The default local AOSP test platform certificate differs from the ATV platform certificate.
Before deploying a system image, resolve production signing and compatibility with existing data;
do not bypass signature checks or wipe data as an upgrade workaround.

| Directory | Source-tree path | Base | Patches |
|---|---|---|---|
| `.repo_manifests` | `.repo/manifests` | `b51a0c449a32` | 4 |
| `frameworks_av` | `frameworks/av` | `f18c3ac08a56` | 5 |
| `frameworks_base` | `frameworks/base` | `6e3f1fcdf5d2` | 45 |
| `frameworks_native` | `frameworks/native` | `95cdabea07cb` | 4 |
| `packages_apps_Settings` | `packages/apps/Settings` | `51beb5b15d0c` | 2 |
| `external_aac` | `external/aac` | `41f344ffc0ba` | 1 |
| `external_hplip` | `external/hplip` | `d37ce064e1e2` | 1 |
| `external_tremolo` | `external/tremolo` | `100623061b6d` | 1 |
| `external_libopenapv` | `external/libopenapv` | `1f7d75914d98` | 1 |
| `packages_apps_ManagedProvisioning` | `packages/apps/ManagedProvisioning` | `dcb981579cbb` | 1 |
| `packages_modules_IntentResolver` | `packages/modules/IntentResolver` | `514e2233f8c1` | 1 |
| `packages_modules_NeuralNetworks` | `packages/modules/NeuralNetworks` | `a44a9032ab9a` | 1 |
| `packages_modules_Profiling` | `packages/modules/Profiling` | `8b3abe8eebc0` | 1 |
| `packages_services_Iwlan` | `packages/services/Iwlan` | `ddf0eb7f277e` | 1 |
| `system_gsid` | `system/gsid` | `35a92d40f529` | 1 |
| `trusty_user_base` | `trusty/user/base` | `165d46c463bd` | 1 |

`.repo_manifests` contains Tsinghua mirror configuration and declarations for three Lineage security
forks. Apply patches to the corresponding bases first, then sync components and apply each series.
`container/system-security-revisions.json` records the actual full bases and patched local HEADs
for source verification, not as revisions guaranteed to be fetchable from remotes.
