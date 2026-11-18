# Codec2 in Rust

All the real work of the guest Codec2 service `android.hardware.media.c2@1.2-service-nvprolapse` now lives in the Rust RM and has shipped since `a17-20261028-2`. The host VA-API driver rustnv uses the same RM video code.

## Current division of work

Path abbreviations: `M` = `nvidia-prolapse/media`, `N` = `nvidia-prolapse/driver-source/native` (both in `a17-local` of `nvidia/waydroid-nvidia`).

|Part|Location|Language|
|---|---|---|
|Codec2 component, parameters, Store, service entry|`M/c2/NvC2Component.cpp`, `NvC2Encoder.cpp`, `service.cpp`|C++|
|Encoder session thin layer|`M/core/nvc2_encoder.{h,cpp}` → `nv_venc_sess_*`|C++ shell, about 100 lines|
|Encoding: sessions, rate control, five input conversions, SSE2 chunking|`N/src/video/{venc,ffi_enc}.rs`, `enc/`, header `N/video/nv_venc.h`|Rust|
|Decode driver: queues, CSD replay, multi-frame output, flush/EOS, gralloc validation|`N/src/video/{c2_dec,ffi_dec,c2_layout}.rs`, header `N/video/nv_c2_dec.h`|Rust|
|Capability tables and `media_codecs` XML, `nvc2-xmlgen`|`N/src/video/{caps,ffi_caps}.rs`, header `N/video/nv_c2_caps.h`|Rust|

C++ keeps only what the Android Codec2 interface requires: component lifecycle, parameter reflection, reading and writing C2 buffers, and the outer validation of gralloc native handles.
Every Rust export has a panic boundary, and the ABI has layout assertions for 32/64-bit on both the C and Rust sides.

## Divergence from upstream Shiro836/waydroid-nvidia

Compared with upstream rc11 (`7670f54`), these files under `M` are deleted and replaced by the Rust code in the table above:

- `core/nvc2_decoder.{h,cpp}`: the decode driver.
- `core/nvc2_caps.cpp`, `tools/nvc2_xmlgen.cpp`: capability tables and XML generation.
- `test/core_test.cpp`, `test/xml_test.cpp`, `test/nv_video_stub.{h,cpp}`: the tests moved into the RM (fake backend, 30 decode/layout tests).

In addition, `c2/NvC2Component.cpp` and `service.cpp` now call the Rust ABI; the encoder (`NvC2Encoder`, `nvc2_encoder`) is new in this repository and does not exist upstream.

How upstream fixes are ported:

- If upstream changes `nvc2_decoder.cpp`, `nvc2_caps.cpp` or xmlgen: understand it and rewrite it in the corresponding Rust file; it cannot be cherry-picked.
- If upstream changes component code under `c2/`: merge it by hand against ours, noting that we call `nv_c2_dec_*` and `nv_c2_caps_*`.
- If upstream changes the rest of the RM (code in `N/src` outside video C2): merge as usual.

## Handling added during the rewrite

- When a single VP9 input contains several display frames (a superframe), they are delivered frame by frame: non-final frames are cloned with `FLAG_INCOMPLETE` and the final frame completes the original work.
- Each CSD (codec-specific data for startup and replay) segment is limited to 2 MiB; anything larger is rejected as a whole with `C2_BAD_VALUE`.
- gralloc handles first get their native handle outer layer validated in C++ (version, fd count, word count), then Rust checks format, geometry, stride, offset, plane ranges and overlap.
- MaxInputSize uses checked 64-bit arithmetic; on overflow it is rejected and the old value is kept.

## Performance

1280×720 NV12 at 30 fps, 330 frames per round with the first 30 dropped, old and new implementations run alternately for five rounds each, median reported (ms/frame). Timing includes submission and waiting, but not file I/O or encoder open/close.

|Codec|Rate control|C version|Rust version|Change|
|---|---|---:|---:|---:|
|H.264|CQP|0.591|0.597|+0.98%|
|H.264|CBR|0.637|0.609|−4.38%|
|HEVC|CQP|0.455|0.443|−2.51%|
|HEVC|CBR|0.461|0.455|−1.31%|
|AV1|CQP|0.481|0.479|−0.50%|
|AV1|CBR|0.497|0.500|+0.74%|

Four of the six are slightly faster, by up to 4.4%, and the other two are less than 1% slower, which is within measurement noise.
Quality: the lowest PSNR across five input formats × three codecs is 39.5 dB, the same as the C version.
Decoding was not benchmarked; it was accepted on function: 60 frames of each of the four decoders match frame by frame, and Chrome plays VP9 for 60 seconds with 0 dropped frames.

After moving the capability tables and XML to Rust, the four XML outputs (GNU/bionic, old and new) are byte-identical, and `media.xml_sha256` in the install record is unchanged.

## Regression tests

- Decoder and capability coverage is the RM's own test suite (fake backend, 30 decode/layout tests) described above.
- Encoding timings use `M/test/enc-benchmark.py`.
