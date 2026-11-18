#!/usr/bin/env bash
# Cold/warm native-only rebuild in a disposable rootless container.
# Keeps the baseline vendor modules; this is not a complete vendorimage build.
# Rebuilds Waydroid's userspace libraries, NOT NVIDIA's host/kernel driver.
# Usage: build-waydroid-native.sh SOURCE [IMAGES_DIR]
set -euo pipefail
SOURCE=$(realpath "${1:?provide the committed patched waydroid-nvidia checkout}")
IMAGES=$(realpath "${2:-/etc/waydroid-extra/images}")
IMAGE=${WAYDROID_NATIVE_IMAGE:-localhost/waydroid-nvidia-620-build}
JOBS=${WAYDROID_NATIVE_JOBS:-4}
MEMORY=${WAYDROID_NATIVE_MEMORY:-8g}
CPUSET=${WAYDROID_NATIVE_CPUSET:-$(python3 -c 'import os,sys; print(",".join(map(str, sorted(os.sched_getaffinity(0))[-int(sys.argv[1]):])))' "$JOBS")}
[ -f "$SOURCE/nvidia-prolapse/driver-source/native/Cargo.toml" ] ||
    { echo "Not a waydroid-nvidia source checkout" >&2; exit 1; }
[ -z "$(git -C "$SOURCE" status --porcelain --untracked-files=no)" ] ||
    { echo "Commit tracked source changes before building" >&2; exit 1; }
for part in system vendor; do
    [ -r "$IMAGES/$part.img" ] || { echo "Missing $IMAGES/$part.img" >&2; exit 1; }
done
command -v podman >/dev/null
podman image exists "$IMAGE" ||
    { echo "Build the pinned packaging/native/Containerfile as $IMAGE first" >&2; exit 1; }
LOGS=$SOURCE/build/nvidia-620-logs/$(date +%Y%m%d-%H%M%S)
mkdir -p "$LOGS" "$SOURCE/build/.buildenv-home" "$SOURCE/build/nvidia-620-apex"
printf 'Native rebuild logs: %s\n' "$LOGS"
# Android 17 uses EROFS and packed APEXes. The old hwcomposer imagelibs
# stage and prepare-runtime32.py use debugfs only; reuse the release gate's
# tested image reader rather than mounting images or duplicating extraction.
TMPDIR="$SOURCE/build/nvidia-620-apex" python3 - "$SOURCE" "$IMAGES" <<'PY' | tee "$LOGS/runtime.log"
from pathlib import Path
import sys

source, images = map(Path, sys.argv[1:])
sys.path.insert(0, str(source / "packaging/native"))
import release_gate

roots = ["libcutils.so", "libhardware.so", "liblog.so", "libsync.so",
         "libnativewindow.so", "libz.so"]
for sub, out in [
    ("lib64", source / "build/hwcomposer-work/deps/image-rootfs/system/lib64"),
    ("lib", source / "build/nvk-android32/runtime"),
]:
    origin = release_gate.extract_runtime(images / "system.img", out, sub, roots, {"libdrm.so.2"})
    for name, path in sorted(origin.items()):
        print(f"{sub}: {name} <- {path}")
PY
podman run --rm --name "waydroid-nvidia-620-build-$$" --userns=keep-id \
    --cpus="$JOBS" --memory="$MEMORY" --memory-swap="$MEMORY" \
    -v "$SOURCE:/work" -v "$IMAGES:/images:ro" -w /work \
    -e HOME=/work/build/.buildenv-home -e CARGO_HOME=/work/build/.buildenv-home/cargo \
    -e HWC_IMAGES=/images -e PROLAPSE_ROOT=/work -e NATIVE_JOBS="$JOBS" \
    -e NINJA_LOAD="$JOBS" "$IMAGE" \
    taskset -c "$CPUSET" nice -n 10 ionice -c 3 bash -euo pipefail -c '
        B=nvidia-prolapse/driver-source/native
        # These are pinned source/dependency downloads, not host package installs.
        hwcomposer/provision.sh ndk clones
        NDK_ROOT=/work/build/hwcomposer-work/ndk/android-ndk-r29
        for arch in x86_64 x86; do
            make -C nvidia-prolapse/libdrm ARCH="$arch" NDK="$NDK_ROOT" \
                NO_BLOB_CENSUS="Native NVK/nvrm build; no proprietary userspace"
        done
        ln -sfn /work/build/libdrm/build-android33-x86/libdrm.so \
            build/nvk-android32/runtime/libdrm.so.2
        # Mesa intentionally invokes Cargo offline; seed the pinned RM crates
        # in this container-specific cache before those build commands.
        cargo fetch --locked --manifest-path "$B/Cargo.toml"
        python3 "$B/compiler/build.py" --tools-only --download-deps
        python3 "$B/compiler/build.py" --target host --download-deps -j "$NATIVE_JOBS"
        python3 "$B/mesa/build.py" --target host --rust-profile release --download-deps -j "$NATIVE_JOBS"
        for target in android android32; do
            python3 "$B/mesa/build.py" --target "$target" --rust-profile release --download-deps -j "$NATIVE_JOBS"
        done
        python3 "$B/mesa/build.py" --gl --prepare-only --rust-profile release --download-deps
        for target in android android32; do
            python3 "$B/mesa/build.py" --gl --target "$target" --skip-prepare \
                --rust-profile release --download-deps -j "$NATIVE_JOBS"
        done
        NDK=/work/build/hwcomposer-work/ndk/android-ndk-r29/toolchains/llvm/prebuilt/linux-x86_64/bin
        make -C nvidia-prolapse/media xmlgen-android RUST_PROFILE=release \
            NV_C2_RM_LIB_DIR=/work/build/nv-rm-rust/x86_64-linux-android/release \
            CARGO_TARGET_DIR=/work/build/nv-rm-rust \
            RUST_LINKER="$NDK/x86_64-linux-android33-clang"
        cc -O2 -Wall -Wextra -Werror tools/native-vulkan-multiqueue.c \
            -ldl -pthread -o build/native-vulkan-multiqueue-host
    ' 2>&1 | tee "$LOGS/build.log"
echo "Native libraries built; assemble and gate a separate bundle before activation."
