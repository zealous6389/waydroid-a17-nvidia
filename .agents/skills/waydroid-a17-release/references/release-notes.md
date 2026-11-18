# Release-notes format

English only. Adapted from upstream commit `28955ede2c365c6822984e64c68b58dda673e285`.
Use a previous **fork** release as a structural reference, not as evidence for new test results:

```bash
gh release view <previous-tag> --repo zealous6389/waydroid-a17-nvidia --json body -q .body
```

Replace every placeholder with verified data before publication.
Do not copy the upstream author's machine, AUR ownership, kernel version or passing gate claim.

```markdown
LineageOS 24.0 (Android 17) Waydroid vendor image, nvidia-prolapse mode.
Fork: zealous6389/waydroid-a17-nvidia.

- Pairs with <exact verified system-image revision and variant>.
- NVIDIA host driver actually tested: <version and module flavor>; GPU: <model>.
- Binary package: <fork repository/release PKGBUILD URL and required install file; no AUR account needed>.
- Packaging installs the prebuilt native/vendor payload; it does not rebuild Android/Mesa/Rust.

Changes since `<previous-tag>`:
- <User-visible change; identify upstream provenance where applicable.>

Validation:
- Release gate: <actual passed/total cases and media result, or explicit blocker>.
- Codec2 decode/encode: <actual counts and failures>.
- Surface/seccomp/Chrome/graphics: <actual results and explicitly skipped tests>.
- Existing system.img: <verified unchanged SHA-256>.
- Host NVIDIA kernel module: unchanged by this release.
- Image provenance: <full vendor build, or fully documented controlled repack and retained service hash>.

Assets:
- `vendor.img.zst.partNN`: numbered compressed image parts.
- `vendor.img.zst.sha256`: part, joined archive and decompressed image SHA-256 values.
- `waydroid-a17-nvidia-native-x86_64.tar.zst`: matching native bundle `<exact identity>`.
- <Immutable source bundle/build records/validation report and their hashes, if included>.

Reassembly in an empty directory containing exactly this release's parts:

    sha256sum --ignore-missing -c vendor.img.zst.sha256
    cat vendor.img.zst.part[0-9][0-9] > vendor.img.zst
    sha256sum --ignore-missing -c vendor.img.zst.sha256
    zstd -d vendor.img.zst
    sha256sum -c vendor.img.zst.sha256

Verify that every expected part is present in sequence before joining; --ignore-missing alone
does not establish completeness. Do not mix parts from different releases.

Installation and rollback:
- <Exact instructions for the validated checksum-pinned binary package>.
- <Required existing Waydroid/system-image configuration>.
- <Rollback steps preserving user data and prior package/vendor/configuration>.

Known limitations:
- <Unverified hardware, skipped tests and outstanding issues>.
```

Write user-visible effects rather than unexplained implementation details. Credit ported fixes
(for example, waydroid-nvidia rc11) and preserve source/license attribution.
Do not claim a complete security bulletin, raised SPL, AUR availability or NVIDIA 620 compatibility
unless the corresponding evidence actually exists.
