# Android 17 HWUI: NVK dual graphics queues

## Results

- The dual-ABI native NVK and the vendor image built successfully; this task did not stop, start or modify the running Waydroid.
- Independent public Vulkan probes on real Android 17 bionic x86_64 / i686 both report `graphics_family=0 queueCount=2` and pass concurrent two-thread submission, GPU fill and CPU readback.
- The final combination is **the new local NVK + rc10's original Rust RM backend/HAL/libdrm/nvrm/Codec2**, and the probe tested exactly that combination.
- All 19 bundle prebuilts inside vendor.img are byte-identical to the new bundle; the image's build_record property equals the SHA256 of the new BUILD-RECORD.json.

|Item|Path / identity|
|---|---|
|Source commit (`a17-local`, not pushed)|`eec39aa`: expose two independent NVK graphics queues for Android 17 HWUI|
|product commit|`c5aaf35`: pin the native package identity for the Android 17 HWUI dual-queue NVK|
|New complete native bundle|`nvidia/build/native-multiqueue/` (contains payload, original gates, new BUILD-RECORD, SHA256SUMS.native)|
|New bundle release|`v0.2.0-rc10-a17-multiqueue`|
|BUILD-RECORD SHA256|`684a32a51133fe326904a67bc2a905e95cce52c0da5949dbd5bbeff0992c3565`|
|vendor image|`src/out/target/product/waydroid_nvidia_x86_64/vendor.img`|
|vendor image size / SHA256|898494464 bytes / `65f00c4df7d2d454ebc183b22c646ddadb27768885646e55e88b8f80ea1e44d4`|
|Patched native build log|`logs/nvk-multiqueue-native-build.log`|
|vendor build log|`logs/nvk-multiqueue-vendorimage.log` (`build completed successfully (01:36)`)|
|Read-only image verification record|`nvidia/waydroid-nvidia/build/nvk-multiqueue-probe/image-check/result.json`|

## Why the queues must be genuinely independent

A17 `frameworks/base/libs/hwui/renderthread/VulkanManager.cpp:232-244` requires two queues on the first graphics family; `:441-442` obtains queue 0 and queue 1; `:543-544` binds the RenderThread context to queue 0 and the upload context to queue 1.

The second queue is not a spare handle: `HardwareBitmapUploader.cpp:108-117` creates **GrallocUploadThread**; `:239-261` creates the `kUploadThread` Ganesh context on that thread, uploads bitmaps into AHardwareBuffers and calls `submit(GrSyncCpu::kYes)`. Its `mVkLock` does not serialize RenderThread's submissions, so both threads can enter the driver concurrently.

The native README, Mesa README, RM-ADAPTER, SYNCHRONIZATION, ASYNC-SUBMISSION, nvkmd_rm.c, rm-integration.patch and the queue-family/queue creation code of the pinned Mesa were read. The Mesa pin is `ddaf85e353442d9d7f192fdcf1823e652e3f2ee3` (26.2.5).

### The existing implementation already has an independent submission context per VkQueue

1. Mesa `nvk_device.c:370-374` calls `nvk_queue_create` for every queue index.
2. Mesa `nvk_queue.c:409-447` allocates a new queue, `exec_ctx`, draw constant buffer and push stream each time, and initializes the graphics/compute state.
3. `nvkmd_rm.c:1238-1263` allocates a new C context each time and calls `nv_rm_context_create`; pending pushes, waits and last token are all private to the context.
4. Rust `src/mesa.rs:1357-1385` creates a new `Queue` each time and appends it to a dynamic `Vec<Option<Queue>>`, with no limit on the number of graphics queues.
5. `src/gpu.rs:1350-1544` creates an independent notifier, GPFIFO, tail, TSG (0xa06c), context-share (0x9067), channel, USERD, completion surface and retirement slot each time. `subcontext=0` of each TSG is an index within that TSG, not a single graphics channel shared by the whole device.
6. The `Bridge.inner` mutex protects the shared Rc graph, allocators, sync payload and scratch; submission operates on the ring of the specified context inside the lock, and the ring-pressure CPU wait lives in the C adapter retry loop without holding that mutex. Synchronization and reclamation are tracked by context id/token.

The minimal change is therefore just `native/mesa/nvk-rm-graphics-multiqueue.patch` setting the graphics family `queue_count` to 2. `build.py` wires the patch into the NVK patch stack and `native_rust_profile.py` adds it to the source hash snapshot; the README documents ownership and the probe. There is no need to rewrite the Rust backend, map both VkQueues onto the same ring, or add workers.

## Build environment and faithful rebuild of the original

Reproduced inside rootless Podman with the official `packaging/native/Containerfile`; no toolchain was installed on the host and no driver was modified. Base image digest `fe6972d4dc1f660c0c10f4c41b2de8986bab89e7e2955378f8beadb8ebcd7433`, Arch archive snapshot `2026/10/15`. The final local build image is `localhost/nvk-native-a17`, ID `ce24d8fb2965454c17907d0097c32fa59fe7ac76dbd4966ff16103e5d045e072`.

Tool versions: Rust 1.95.0 (59807616e), Cargo 1.95.0, Android x86_64/i686 targets, Meson 1.12.1, Ninja 1.13.2, host GCC 16.2.1, LLVM/Clang 23.1.1, NDK r29 `29.0.14206865` API33 (NDK Clang 21), bindgen 0.72.1, cbindgen 0.29.2, libdrm 2.4.134, Android static libelf 0.8.13, and the checksum-pinned libclc/SPIR-V translator from `host-build-deps.json`. The complete container package versions are written to `nvk_build_environment` in the new record.

Network: the default Arch network timed out while host networking succeeded; the official Rust site returned a TLS EOF, so rsproxy was used to fetch the same Rust version pin. The completed system-dependency layer was kept, then Rust was installed and the container image saved. `hwcomposer/provision.sh ndk clones imagelibs` provides pinned AOSP headers and Android13 link-time libs; the dual-ABI libdrm is built with the repository's original Makefile. For the probe runtime the real bionic closure is extracted read-only from the current ATV **Android17** `ref/system.img`. The host already had `dump.erofs`, so no package was added.

The host, Android x86_64 and Android i686 builds first succeeded on sources **without the dual-queue patch**. All native source hashes listed in the rc10 BUILD-RECORD match the sources before building. The baseline is kept in `nvidia/waydroid-nvidia/build/nvk-baseline/{host,android,android32}/`; the full comparison is in `comparison.json` and `sections.json`.

|ABI / file|Local baseline SHA256|rc10 SHA256|
|---|---|---|
|x86_64 NVK|`e15bc94d85325849ec20d62781442e1e3e5452f8418552244fad024c12540c28`|`560d18fb2c6207fcb2b022663788bea46e5eaab06f05ff9083f9acb00b9ad2cb`|
|i686 NVK|`ba0e19d3061e93cca4f476bd0e05b9c755f9f6da764dcb11d2341ce69985c89f`|`c31ea568ace09ade5c87bf018ffaaaf18655690853372eba7e455ad1ed5bc09a`|
|x86_64 Rust RM|`8ec8824b776eed4fec5fdfa845629cdf6101af1eb81fcaf6b5f64f0cbfaff4b4`|`3ef545204f8f4ea9f9df9ae258ddf233600cdb2fab307d348b05e1a3d793eea3`|
|i686 Rust RM|`f33bcf628ba828be90d92fd70a31cb6cd0a668b0a65e44308717ed45c5ed6ca3`|`3ddde70d7f4c7abeab0f74474329377453c1883415d3a29792c3edf9af72cd60`|

The ELF is not byte-identical as a whole: the local prefix `/work` differs from the author's `/home/forsen/native-ci/waydroid-nvidia`. pyelftools compared every SHF_ALLOC, non-NOBITS section: **all runtime sections of both Rust RM files are identical**; for both NVKs the code/constant sections such as `.text` and `.rodata` are identical, with differences limited to dynamic strings, link addresses/relocations, data pointer tables and the build-id. `readelf -d` confirms rc10 itself carries the author's absolute-path RUNPATH, while the local build with the same recipe uses a `/work` path, which affects string-table length and link layout. [INFERENCE] This explains the NVK layout difference; no claim is made that a semantic normalization has proven every relocation equivalent.

## Patched artifacts and the probe

|ABI|Final `libvulkan_nouveau.so` SHA256|
|---|---|
|x86_64|`fbc2cd2d3ea44f5b29bbcb36113ca3fd6ac3f8ddf0eb952e1c10f3752f3f4bb3`|
|i686|`54cd8dccafcfbf5e85f814945542fa8002259b773341560880bb1d8ad2f01b0f`|

The build outputs are in `nvidia/waydroid-nvidia/build/nvk-{android,android32}/src/nouveau/vulkan/libvulkan_nouveau.so`, and the deployed copies are in the new bundle's `payload/vendor_extra/{lib64,lib}/`. The HAL `hw/vulkan.nvidia.so` is the original rc10 wrapper, whose queue-family queries are forwarded to NVK; the wrapper needs no change or rebuild.

The final bundle replaces only these two NVK libraries and keeps the original Rust backend bytes. `nv_rm.h` is unchanged and the baseline comparison of the Rust runtime sections matches; keeping the original bytes means nvrm's original build provenance and `nvrm_rust_sha256` stay truthful. The new record clearly separates `base_release`, the kept backend's `rust_builds`, the local NVK's `nvk_builds` with its build-time backend metadata, and the final actual backend hash; it does not pretend the whole stack was rebuilt locally.

The new probe `tools/native-vulkan-multiqueue.c` is compiled with NDK r29/API33, selects NVIDIA/Mesa NVK, prints the first graphics family and creates two distinct VkQueues on that family. Each thread owns its command pool/buffer/fence; each round a pthread barrier releases both submitters at once, and the GPU fill is verified word by word afterwards. Per ABI: 512 submissions, 524288 words.

Real output (identical for both ABIs):

```text
device=NVIDIA GeForce RTX 4060 Laptop GPU (NVK NV197) driver=NVK Mesa 26.2.5 (git-ddaf85e353)
graphics_family=0 queueCount=2
PASS: two concurrent graphics queues, 512 submissions, 524288 words checked
```

Evidence directory `nvidia/waydroid-nvidia/build/nvk-multiqueue-probe/`:

- `logs/android-multiqueue.log`, `logs/android32-multiqueue.log`; exit 0 for both.
- `results.json`, `runtime-origin.json`; the 32-bit run uses the release gate's user/PID namespace runner to avoid bionic's host high-PID limitation.
- `runtime/{lib64,lib}` are read-only extracted copies of the A17 system; nothing was written to the guest.

The dual-ABI build of the patched native code used `build.py --target android/--target android32 --rust-profile release -j 12` and completed offline. The upstream 64-bit atomics alignment warning is kept for 32-bit rather than suppressed; this probe passing does not mean all upstream warnings or Vulkan conformance are resolved.

## Product, vendor and host gate

The product `vendor/nvidia-prolapse/native-bundle.json` pins the project-root-relative bundle path and the record hash. `scripts/stage-product.sh` reads it, verifies the record hash and payload hashes first, then copies the payload to `src/vendor/nvidia-prolapse/prebuilts/native/payload` and generates `identity.mk`. The OTA wrapper in `scripts/reinstall-vendor.sh` reads the same pin, avoiding accidental use of the rc10 record. These two project-root scripts are not part of the product git; the product commit tracks the pin itself.

Run:

```sh
scripts/stage-product.sh
scripts/build.sh lineage_nvidia_waydroid_x86_64-cp2a-userdebug vendorimage
```

`vendor_image.check_prebuilts` extracted and verified the 19 prebuilts in the image read-only: all match the new bundle. Reading the vendor build.prop confirms:

```text
ro.vendor.nvidia_prolapse.version=v0.2.0-rc10-a17-multiqueue
ro.vendor.nvidia_prolapse.build_record=684a32a51133fe326904a67bc2a905e95cce52c0da5949dbd5bbeff0992c3565
```

`release_gate.verify_bundle` passes and the new record covers exactly 68 payload/gate files. The install gate still requires the full Vulkan/GL/Codec2 cases on the target GPU/kernel tuple; this task ran only the dual-queue specific probe and the read-only image/bundle verification, not the install gate.

### Exact host install steps for the main agent (not executed by this task)

1. If host tools need reinstalling, run the host installer first. Its wrapper currently pins the rc10 release and would write the original native bundle, so this must be done **before** the new bundle cutover below.
2. The main agent performs a safe Waydroid stop and confirms the stopped state that setup requires.
3. From the project root, sync the **complete new bundle** to the host's fixed directory:

   ```sh
   sudo rsync -rlp --checksum --delete \
     nvidia/build/native-multiqueue/ \
     /usr/lib/waydroid-nvidia/native/release/
   sha256sum /usr/lib/waydroid-nvidia/native/release/BUILD-RECORD.json
   # should be 684a32a51133fe326904a67bc2a905e95cce52c0da5949dbd5bbeff0992c3565
   ```

4. Use the project scripts, already modified to read the product pin, to package and install the matching vendor:

   ```sh
   scripts/reinstall-vendor.sh
   ```

   It calls `packaging/vendor-ota.py` to generate `out-ota/`, installs the OTA zip/channel into `/usr/lib/waydroid-nvidia/vendor/`, then runs `sudo env LC_ALL=C waydroid-nvidia-setup`. setup verifies the new bundle, zip/channel, image prebuilts and build_record, runs the full release gate on the GPU/loaded kernel, and on success updates the install record and the codec XML.
5. The main agent starts it, sets/verifies `debug.hwui.renderer=skiavk`, and checks the HWUI/RenderThread/GrallocUploadThread logs, the picture and NVIDIA Xid. The specific probe does not replace this step.

Gate rationale: `release_gate.py:73-92` validates the bundle file set and hashes; `vendor_image.py:151-162,240-259` validates the image bytes, record digest and GPU gate. `/usr/lib/waydroid/tools/helpers/nvidia_native.py:1620-1677` checks the image identity, install record, installed package record, image hash, kernel version and codec XML at startup. Overwriting only vendor.img or hand-editing build.prop cannot bypass the gate; the host bundle, the image and the setup install record must all agree.

## Open risks and boundaries

- Real Android `skiavk` startup, hardware bitmap upload and the visible picture are verified by the main agent after installation; this task makes no claim that Android UI acceptance is complete.
- An independent TSG/channel is not an independent physical graphics engine; the GPU may time-slice, and Vulkan does not guarantee physical concurrent execution.
- The existing foreign sync-file, device-loss, reclamation and GPU semaphore constraints are unchanged; see `SYNCHRONIZATION.md`.
- The development RUNPATH of the original recipe is carried over (the new artifacts use `/work/...`); Android's real library lookup relies on the vendor namespace/SONAME, and the probe explicitly uses the bundle LD_LIBRARY_PATH. No extra RUNPATH cleanup or rewriting of unrelated runtime logic was added in this task.
- The host NVIDIA driver, kernel packages and boot configuration were not changed; there was no reboot and no Waydroid lifecycle operation.
