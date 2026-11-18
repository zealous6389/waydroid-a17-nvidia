# hwcomposer NVIDIA Patch Porting Report

## Results

- Repository: `nvidia/work/hardware_waydroid`, ATV `lineage-23.0` baseline `3af187c`, local branch `nvidia-a17`.
- Final commit: `a309b1c`. Of the 18 patches, 17 were imported independently and in order; 0009 was skipped because ATV already implements it equivalently. One additional commit, whose message is in Chinese, completes the connection/release lifecycle adaptation.
- Imported commits keep the original author and original message; commits with adaptations append a note in Chinese. Nothing was pushed, and the syncing `src/` was not touched.
- For patches 0014–0016 and 0018, `git am -3` cannot reconstruct an ancestor from the old blobs listed in the patch; the am session was kept, the adaptation was completed from the applicable hunks and the original patch content, and `git am --continue` was then run.

## Per-patch results

| Patch | Result / commit | Handling |
|---|---|---|
| 0001 baseline | Resolved, `a410dba` | Imported NVIDIA format/modifier admission, opaque RGB import, server-side decoration, client-target drawing fixes and clipboard fixes; protocol objects and input serials moved to `wl_conn`. Kept ATV task streams, task close/snapshot, geometry ownership and per-connection thread stop before reclaim; uses ATV's single-config resize path and does not introduce A13's fixed-physical-resolution mode ladder. |
| 0002 formats mutex | Resolved, `16aaf5f` | Each `wl_conn` holds its own formats, modifiers and mutex; the advertisement callback and import admission read and write the same connection's data. |
| 0003 NVIDIA EGL LINEAR | Resolved, `2eb7616` | Records per connection which formats carry an NVIDIA modifier, and rejects LINEAR only for those formats. |
| 0004 wl_buffer cache | Resolved, `8b80a68` | Kept ATV's `shared_ptr` and keep-alive for attached buffers; the ctl cache is pruned with the 8-frame unused policy, dma-buf inode identity was added, and the cache is not flushed wholesale on geometry changes/hotplug. |
| 0005 no abort | Resolved, `29cd2e6` | Frame errors return failure; the missing-shell-protocol check moved to `wl_conn_open`. ATV's reconnect after disconnect is kept. |
| 0006 named disconnect | Resolved, `ab097f7` | Imported protocol object/error-code logging and `waydroid.hwc.wayland_lost`. Kept ATV ctl reconnect and independent task connection reclaim, without terminating other tasks with process exit 75. |
| 0007 SIGPIPE | Resolved, `a043b2f` | Ignores SIGPIPE while keeping ATV's cleanup of stale window properties at startup. |
| 0008 cursor importability | Resolved, `e35458e` | Cursor admission checks on the ctl connection plus wl_shm fallback; kept ATV's existing acquire-fence handling. |
| 0009 HIDL threadpool | Dropped: equivalent patch | ATV `bb49e33` no longer shrinks the thread pool in the composer service configuration; its implementation is kept to avoid reconfiguring an already started thread pool. |
| 0010 SHM fallback | Resolved, `87cacbd` | Layers that cannot be imported directly use the current ctl's wl_shm, still with ATV's shared ownership. |
| 0011 acquire timeout | Resolved, `2623322` | Kept the `shared_ptr` parameters; after a failed 1-second fence wait the present geometry/feedback is still completed. In 0014 the wait is placed before the GPU copy and attach. |
| 0012 monotonic timestamps | Resolved, `5522f39` | The presentation clock is stored per connection; ctl feedback enters vsync only with CLOCK_MONOTONIC. Kept ATV's task-streams mode wakeup logic. |
| 0013 viewport clamp | Clean apply, `ecd4984` | The clip rectangle is clamped to the rotated buffer bounds. |
| 0014 cross-GPU PRIME | Resolved, `f079758` | dmabuf v4 feedback, present_path and the copy pool moved to `wl_conn`; FBT keeps the shared cache and fence ordering; copy source, copy pool and feedback are released when a connection is rebuilt/destroyed. This commit also carries the new task-stream adaptation described below. |
| 0015 YUV / planes | Resolved, `cc680d2` | Keeps the wl_conn API and passes all planes; YUV is left to SurfaceFlinger, and formats SHM does not support fail explicitly; the cros plane array checks the DRV_MAX_PLANES range before construction. |
| 0016 hotplug outside present | Resolved, `a3a579c` | Removed the primary-display hotplug and needHotplug from `hwc_set`; kept ATV's input pipe update and frame requests, and added a poison so the present/Wayland file cannot send hotplug directly. |
| 0017 Soong prime-copy | Clean apply, `741cd44` | Android.bp compiles prime-copy.cpp, adds Vulkan headers, and keeps the missing-field-initializer warning setting. |
| 0018 safe resize | Resolved, `50f55a6` | Reuses ATV window geometry ownership and the 250 ms settle; moves the resize worker into a separate display-resize.cpp. The primary-display reconnect is sent from that thread only when `ro.vendor.composer.safe_primary_reconnect=true`, calling the HAL without holding the module lock. Keeps a single config, with the physical size protected by modes_mutex; no second mode ladder/thread is introduced. Android.bp also compiles the new file. |

## Added adaptation: ATV task streams

ATV's `post_task_buffer` used to rely on android_wlegl unconditionally. The NVIDIA/KWin dmabuf graphics path cannot depend on that protocol alone, so:

- The original ATV path is kept when the current connection supports android_wlegl.
- Otherwise dmabufs are imported through the current task's `wl_conn`: direct import on the same GPU, PRIME copy into system-memory LINEAR across GPUs.
- Kept the slot inode/metadata reallocation decision, fence waits, staging before the first configure, keeping the newest frame on deactivation and the original slot release policy.
- `wl_buffer.release` for dmabufs uses the lifetime-stable connection as userdata and then looks up the slot by connection and wl_buffer, so a callback never references a buffer that has already been replaced.
- Copy pools are reclaimed with their connection; a primary connection reconnect does not discard other task connections.
- The release-callback stability, format-set locking on reconnect and compile cleanup described above were completed in commit `a309b1c`, whose message is in Chinese.

## Self-check evidence

- `git diff --check 3af187c`: passes, no output.
- `git status --short --branch`: only `## nvidia-a17`, working tree clean.
- Conflict-marker search across the hwcomposer sources: no matches; `.rej` / `.orig` search: no files.
- The relevant code was read, and the declarations/definitions/calls of the new PRIME, resize, task-stream release, displayable_buffer and set_crop code were searched; Android.bp lists both prime-copy.cpp and display-resize.cpp.
- Protocol dependency: PortComposerHal confirmed that the matching wayland-protocols branch update contains the xdg-decoration and dmabuf feedback interfaces, and that the existing `libwayland_extension_client_protocols` exports the generated headers; this slice adds no generation rules.
- Nothing was built, no project tests were run and Waydroid was not started. A static self-check is not equivalent to an Android 17 build or runtime validation.

## Requires runtime validation

1. **Same-GPU passthrough**: under NVIDIA/KWin, full UI, single window, classic multi-window and task streams all produce a picture; confirm ANGLE/NVK, block-linear modifiers and `waydroid.hwc.present_path=direct`; cursor/alpha/decoration/clipboard behave correctly.
2. **New task-stream path**: with task streams and with classic multi-window, repeatedly open/close/switch at least two apps; verify per-connection windows, focus, deactivation snapshot and restore, first configure and slot release, with no persistent EBUSY, black cards or fd growth.
3. **Cross-GPU**: under an iGPU compositor, validate the PRIME paths of FBT and task streams; check `cross-gpu-copy`, system-memory LINEAR pitch, buffer pool release, continuous animation and fast window switching/resize, including the case where a staged frame is replaced by a later one. Confirm that a failed copy never attaches the original NVIDIA VRAM buffer.
4. **Connection failure isolation**: restart/disconnect the compositor or close the host connection of a single task and check the named error property; ctl must reconnect, independent task connections must be reclaimed/reopened individually, other tasks must not be killed, and no stale wl_buffer/copy-pool proxy may be reused.
5. **Safe resize**: use the matching fixed composer HAL and test with the safe_primary_reconnect property on and off. With it on, dragging, maximizing, fractional scaling and fixed-size must change the Android size only after settle, must never call back re-entrantly from inside present, and must not deadlock or crash; with it off there must be no primary-display reconnect. In particular check that under ATV geometry ownership a single window and multiple tasks do not resize each other, and that viewport presentation matches touch coordinates while dragging.
6. **Video and formats**: YUV sub-layers from Chrome/ExoPlayer etc. are composed by SurfaceFlinger with correct color space/range and no Wayland invalid_wl_buffer; confirm the multi-plane parameters are complete and formats SHM does not support only fail without killing the connection.
7. **Caching and synchronization**: repeated geometry changes, reallocation of same-size buffers and cache aging after closing apps all behave normally; a 1-second acquire timeout, the cursor acquire fence, CLOCK_MONOTONIC and a non-monotonic presentation clock must cause no freeze or persistent fd leak.
