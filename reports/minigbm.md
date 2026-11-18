# minigbm: Android 17 NVIDIA patch port

Target: `nvidia/work/minigbm`, ATV `lineage-24.0` baseline `5f5797c`, local branch `nvidia-a17`; final commit `de6759b`. The syncing `src/` was not modified and nothing was pushed.

## Per-patch results

|Patch|Result|Commit and adaptation|
|---|---|---|
|0001 CPU usage does not force LINEAR on GPU render targets|Conflict resolved|`1d44e03`: reuses ATV's `unmask64` usage-flag consumption, keeps parameter declaration order, scanout/cursor, camera and RPI4/VAAPI alignment; CPU+render keeps a non-linear layout and accepts FRONT_RENDERING.|
|0002 pass the lock's access flags to the wrapper|Conflict resolved|`b46cadf`: keeps ATV's check that returns EINVAL for an invalid unmap state and, once it passes, calls the extension with READ/WRITE flags; keeps flag widening for a repeated lock and the fallback to old wrappers.|
|0003 FP16 and 1010102 render targets from the wrapper|Conflict resolved|`3219d85`: ATV already removed the static format-combination table, so this adds to `supported_formats` and keeps probing through `gbm_mesa_bo_create2`; the wrapper is required to allocate FP16/1010102 directly, and R8 stand-ins are rejected.|
|0004 P010 and a GPU-writable NV12/P010 layout for decoder output|Conflict resolved|`5d6cc2b`: P010 is wired into dynamic probing; adapted to the new `drv_bo_from_format(..., stride_align, ...)` signature. The NVIDIA wrapper's layout extension provides a 256-byte pitch, even height and plane positions/sizes; wrappers that do not export this optional extension keep the ATV layout, preserving the other GPU/RPI4 paths.|
|0005 import into the wrapper on the first CPU map|Conflict resolved|`c34f6de`: ATV already imports on the first map and has a 4096-wide R8 carrier, so the existing functions are reused; the map/unmap restriction requiring SW in the allocation usage is removed, the plane-less interface is kept, and a check for map initialization failure was added.|
|0006 YV12 for hardware decoders, carrier sized to the whole YV12 layout|Dropped (already covered)|ATV's dynamic probing already accepts YVU420_ANDROID with the hardware-decode flag; its carrier uses `4096 × ceil(total_size/4096)` and holds a full YV12, no longer using the half-width reshaping that the patch fixes. Restoring the old static combination table/reshaping would break ATV. Skipped with `git am --skip`; no separate commit.|
|0007 CPU-cached memory for buffers the CPU reads often|Conflict resolved|`3e6f2b4`: reads the original `use_flags_copy` to detect CPU_READ_OFTEN, so ATV's flag consumption cannot invalidate the cache request; keeps test_only non-allocation and the scanout failure retry, and uses the extension entry point on retry.|

There is also a local commit `de6759b` (commit message in Chinese): extension queries are used only for dynamic wrappers, keeping the compile path for ATV's embedded wrapper; without the layout extension the format byte stride is used as well, preventing P010 from being allocated at half width.

All six imported original patches were brought in with `git am -3`, keeping author and original message, with a note in Chinese appended to the message body.

## Static self-check

- `git diff --check 5f5797c..HEAD` passes; `git status --short --branch` prints only `## nvidia-a17`, working tree clean.
- A conflict-marker scan of the whole clone finds no matches.
- With comments/whitespace stripped, the declarations in the four wrapper ABI headers match the prebuilt wrapper sources exactly: base `alloc_args/gbm_ops`, map flags, layout, alloc flags. Neither the prebuilt library nor its headers were modified.
- The wrapper was confirmed to export the four corresponding `get_gbm_*` symbols, and the usage/map flags, format layout functions and their signatures were confirmed to exist in the resulting source.
- `gbm_mesa_driver/Android.bp` already builds internals/backend into `libminigbm_gralloc_gbm_mesa`, which allocator/mapper@4.0 keeps linking against; the additions are headers only with no new `.cpp/.c`, so the source list needs no change. `Android.mk` still builds only the plain Mesa wrapper; NVIDIA products replace that module with a prebuilt wrapper through the established product layer.
- No build or project tests were run; a complete Android tree was not available yet.

## Pending runtime validation

1. A17 allocator/mapper@4.0 loads the prebuilt wrapper and the three versioned extensions in both 32- and 64-bit processes, and allocation, cross-process import and release behave normally.
2. CPU+GPU rendering (screenshots, screen recording) keeps block-linear layouts, and the staging copy direction is correct for READ/WRITE/repeated lock; CPU-only buffers can still be mapped linearly.
3. FP16/1010102 windows, wide color gamut, and pitches for odd/unaligned widths match the Android plane layout.
4. The 256-byte pitch and plane alignment/sizes of NV12/P010 are consistent for NVDEC, NVK, ANGLE and host Wayland import; 10-bit video and ByteBuffer decoding without a Surface work.
5. Decoded output for YV12 1920×816/1080 and wider fits entirely with no overflow; the first CPU lock can map decode output that has no SW allocation usage.
6. Decoded output with CPU_READ_OFTEN and no original scanout really lands in cached memory, with correct performance and synchronization; the scanout allocation retry does not change NVIDIA's intent.
7. The plain non-NVIDIA wrapper, RPI4 camera/hardware decode and the ATV VAAPI paths show no regression on the branches kept; the actual A17 Soong build still needs a complete tree to verify.
