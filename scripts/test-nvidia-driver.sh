#!/usr/bin/env bash
# Test a prepared source tree without installing files or changing host services.
# Usage: test-nvidia-driver.sh SOURCE NEW_RESULTS_DIR [OGKM_620_CHECKOUT]
set -euo pipefail
export LC_ALL=C
umask 077
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SOURCE=$(realpath "${1:?provide the patched waydroid-nvidia checkout}")
OUT=$(realpath -m "${2:?provide a new results directory}")
NATIVE=$SOURCE/nvidia-prolapse/driver-source/native
[ -f "$NATIVE/Cargo.toml" ] || { echo "Missing native source: $NATIVE" >&2; exit 1; }
mkdir "$OUT" # Never overwrite evidence from an earlier run.
exec > >(tee "$OUT/run.log") 2>&1
trap 'rc=$?; printf "%s\n" "$rc" > "$OUT/exit-status"; exit "$rc"' EXIT
run() {
    local name=$1 status
    shift
    printf '\n== %s\n' "$name"
    if "$@" 2>&1 | tee "$OUT/$name.log"; then
        status=0
    else
        status=$?
    fi
    printf '%s\t%s\n' "$name" "$status" >> "$OUT/results.tsv"
    return "$status"
}
{
    date -Iseconds
    uname -a
    cat /proc/driver/nvidia/version
    nvidia-smi --query-gpu=name,pci.bus_id,driver_version --format=csv
    git -C "$SOURCE" rev-parse HEAD
    git -C "$SOURCE" status --short
    rustc --version
    cargo --version
} | tee "$OUT/environment.txt"
git -C "$SOURCE" diff --binary HEAD > "$OUT/source.diff"
sha256sum "$NATIVE/src/compat_data.rs" "$NATIVE/src/compat.rs" > "$OUT/source.sha256"

if [ -n "${3:-}" ]; then
    HEADERS=$(realpath "$3")
    # Check the actual tag, not just a directory labelled with a version.
    [ "$(git -C "$HEADERS" rev-parse HEAD)" = e6a2e01579fbbd1ca2ed43fef2ee2589e9bd8bd9 ] ||
        { echo "Expected the public OGKM 620.70.06 commit" >&2; exit 1; }
    [ -z "$(git -C "$HEADERS" status --porcelain --untracked-files=no)" ] ||
        { echo "Public header checkout has modifications" >&2; exit 1; }
    for abi in 32 64; do
        run "c-abi-$abi-build" cc "-m$abi" -std=c11 -Wall -Werror \
            -I"$HEADERS/src/common/sdk/nvidia/inc" \
            "$ROOT/tests/nvidia-620/abi-profile.c" -o "$OUT/c-abi-$abi"
        run "c-abi-$abi" "$OUT/c-abi-$abi"
    done
    run full-profile python3 "$ROOT/tests/nvidia-620/verify-profile.py" \
        --data "$NATIVE/src/compat_data.rs" --ogkm "$HEADERS" --output "$OUT/full-profile"
fi

cd "$NATIVE"
run unit cargo test --locked --no-default-features --lib
run gpu-map timeout 120s cargo run --locked --no-default-features --bin nv-native-check -- --gpu-map

# The old nv-native-check --copy/--compute path and standalone shared-TSG
# shader fixture hardcode Blackwell. Use selected-device RM/queue/video
# fixtures on Ada; test Vulkan multiqueue through the matching Mesa driver.
hardware_tests=(
    events::tests::host_trigger_cached_ownership_and_fd_cleanup
    external::tests::sysmem_opaque_fd_independent_clients
    fences::tests::pending_fence_and_kernel_wait
    gpu::compression_tests::typed_va_kind_sweep
    rm::budget_tests::repeated_cpu_maps_release_rm_on_selected_nvidia
    rm::budget_tests::block_linear_memory_records_the_generic_kind_on_selected_nvidia
    rm::pool_block_tests::pool_block_has_the_requested_attributes
    mesa::hardware_tests::clean_exporter_close_publishes_gpu_completion
    mesa::hardware_tests::ring_full_leaves_payloads_untouched
    mesa::hardware_tests::slot_lifetime_recycles_under_gpu_retirement
    mesa::hardware_tests::unsignaled_owned_gate_has_bounded_context_teardown
    video::enc::ingest::tests::rgb_to_nv12_matches_cpu
    video::tests::engine0_bsp_caps_live
)
for test in "${hardware_tests[@]}"; do
    name=${test//::/-}
    run "$name" timeout 120s cargo test --locked --no-default-features --lib "$test" \
        -- --ignored --exact --test-threads=1 --nocapture
    grep -q 'test result: ok. 1 passed;' "$OUT/$name.log" ||
        { echo "Expected exactly one executed hardware test: $test" >&2; exit 1; }
done
run clippy cargo clippy --locked --no-default-features --lib -- -D warnings
echo "PASS: host RM checks only; Android, Vulkan rendering and media playback still require the release/guest gates."
