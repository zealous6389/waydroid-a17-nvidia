# Composer HAL and Wayland protocols Porting Report

## Deliverables

Only the standalone clones under `nvidia/work/` were touched; the syncing `src/` was not accessed and nothing was pushed.
Both repositories are on branch `nvidia-a17` with a clean working tree.

|Repository|Baseline|Porting commit|
|---|---|---|
|`nvidia/work/hardware_interfaces`|WayDroid-ATV/android_hardware_interfaces, lineage-24.0, `1b0bcde9a85bd3e6c5866ae83aaab9af9b5efd29` (depth 200)|`7c6466bcb5ab93c039bd69db084e9c961610acc1`|
|`nvidia/work/wayland-protocols`|TUNA AOSP platform/external/wayland-protocols, android-17.0.0_r1, `2dabfe6879b25981e0340823eb1b6d037d21577f` (depth 1)|`782480c88f3b8682cf88b63144f9b7220a963f06`|

## Per-patch results

### hardware/interfaces/0001: applied cleanly at the original paths, with A17 semantic adaptation added

Imported with `git am -3`, keeping Shiro836's original authorship and original English commit message and appending a note in Chinese; no patch was dropped.

- A17 still has `graphics/composer/2.1/utils/hwc2on1adapter/HWC2On1Adapter.cpp` and the 2.1 `ComposerClient.h`, so the original patch needs no path changes.
- During a primary reconnect the adapter releases `mStateMutex` when calling `populateConfigs()` and keeps the object alive with a `shared_ptr<Display>`, avoiding an inverted lock order against validate/present.
- The layer/client-target handle caches are kept across a reconnect; setting the same non-zero client-target slot count again returns success. The declarations, implementations and the display shared_ptr container were all confirmed to exist.
- **Required for A17:** ATV packages both the 2.1 and 2.4 services. The 2.4 `ComposerClient` inherits through 2.3→2.2→2.1 but overrides `HalEventCallback::onHotplug` itself, so patching 2.1 alone does not protect that callback. As confirmed with the main agent, the same cache-retention semantics were extended to 2.4 in the same porting commit; the slot-count method still inherits from 2.1. ATV's service selection and the other 2.4 callbacks were not changed.

### external/wayland-protocols/0001: needed, baseline conflict resolved

ATV's `hardware_waydroid/hwcomposer/Android.bp:43-47` statically links `libwayland_extension_client_protocols`. That module is defined by AOSP `external/wayland-protocols/Android.bp`, whose scanner inputs come from the freedesktop.org XML filegroup there; it is not the 1.49 copy bundled with the hwcomposer repository. That filegroup already lists the seven required XMLs, so no build-rule change is needed.

PortHwcomposer's generated-header dependencies for its 0001/0014 were confirmed: the protocol Android.bp lists the linux-dmabuf and xdg-decoration XMLs on lines 58 and 67; `wayland_extension_client_protocol_headers` uses `wayland_scanner client-header` with the `$(in:base)-client-protocol.h` output rule, and `libwayland_extension_client_protocols` exports the result through `export_generated_headers`. The build rules will therefore produce `xdg-decoration-unstable-v1-client-protocol.h` and a `linux-dmabuf-unstable-v1-client-protocol.h` containing the v4 feedback interface. No further changes to the hwcomposer or protocol Android.bp files are needed; this conclusion comes from a static check of the rules and XMLs, and the scanner/build has not been run.

All seven files exist in the Android 17 tag, but their versions/content are insufficient, and dmabuf feedback in particular is missing:

|XML|AOSP android-17.0.0_r1|After porting (1.49 content from the original patch)|
|---|---|---|
|presentation-time|presentation/feedback v1|v2|
|viewporter|v1|v1, spec text updated|
|xdg-shell|v3|v7|
|linux-dmabuf-unstable-v1|v3, no feedback interface|dmabuf/params/feedback v5, including the v4 feedback that hwcomposer needs|
|pointer-constraints-unstable-v1|v1|v1, spec text updated|
|tablet-unstable-v2|interface version v1|interface version v1, spec text updated|
|xdg-decoration-unstable-v1|v1|v2|

`git am -3` was run first, but the old objects are not in the shallow clone and some context differs, so no three-way ancestor could be established; the applicable hunks were then applied, the remaining context merged by hand, and `git am --continue` run. The original author (waydroid-nvidia project) and the original English message are kept, with a note in Chinese appended.

What the resolution covers: A17 already has dmabuf hotplug tolerance, implicit-modifier documentation and split presentation enum entries, so those were not added twice; the xdg_surface role-check descriptions were merged, and the modifier v4 deprecation notes, the destruction semantics of presentation `presented` and terminology updates were completed. The git blob SHA-1 of all seven XMLs now matches the original patch's target index exactly (not merely the same interface version), and all XMLs parse. Other protocols and ATV features were not changed.

## init / VINTF service check

The static source shows that **init tries to start both composer services**, so this cannot be used to claim that only one of them starts at runtime:

- `device_waydroid/device.mk:78-79` packages `android.hardware.graphics.composer@2.1-service` and `@2.4-service`.
- Both modules' Android.bp files install their init rc; the rcs define `vendor.hwcomposer-2-1` and `vendor.hwcomposer-2-4` respectively, both `class hal animation`, with no `disabled` or `oneshot`; 2.1 additionally declares `interface android.hardware.graphics.composer@2.1::IComposer default`.
- `device_waydroid/manifest.xml:80-85` declares both `@2.1::IComposer/default` and `@2.4::IComposer/default`. The VINTF declaration itself does not choose which process starts.
- Both service.cpp files attempt `HwcLoader::load()` and `registerAsService()`, returning 1 on failure. Which process actually registers, which version SurfaceFlinger binds and whether restarts or registration stealing occur must be observed at runtime; speculation was not substituted for measurement, and the existing service policy was not changed.

## Self-checks performed

- `git diff --check HEAD^ HEAD` produced no output in either repository; `git status --porcelain=v1` produced no output.
- The modified Composer 2.1/2.4 files and the protocol XMLs contain no conflict markers.
- The relevant lock, callback and inheritance code was read; symbol searches confirmed that `populateConfigs()`, `getDisplayClientTargetCacheSize()` and the `mDisplays` shared_ptr container all exist.
- All seven XMLs parse and match the original patch's target blobs exactly.
- No build, project tests or on-device tests were run (the source tree was not ready yet).

## Pending runtime validation

1. Use `getprop init.svc.vendor.hwcomposer-2-1`, `getprop init.svc.vendor.hwcomposer-2-4`, the process list, `lshal` and the boot log to confirm the actual service registration and the SurfaceFlinger binding, and check for repeated restarts or registration replacement.
2. Under NVIDIA/KWin, resize repeatedly and maximize/restore while playing or rendering; confirm the primary-display reconnect updates the size, with no deadlock, BAD_LAYER, use-after-free or SurfaceFlinger/HAL crash.
3. Confirm that the client-target slot count of a new display can be set repeatedly; old layer caches are released with destroyLayer, client-target handles are released when slots change, and long resizing does not accumulate resources.
4. Validate device and format/modifier parsing for dmabuf v4 feedback, and that both same-GPU direct presentation and cross-GPU PRIME copy are correct; the new XMLs must negotiate with older versions on the host.
5. Validate presentation timing, viewporter cropping, xdg-shell resize/decoration, pointer constraints and tablet input; ATV task streams, multi-window and touchpad behavior must be preserved.
