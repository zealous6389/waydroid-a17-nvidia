# Published release verification and cleanup

Release: https://github.com/zealous6389/waydroid-a17-nvidia/releases/tag/a17-20261117-1

Release source commit: `43a548eb4d19956e9928bab6b4f3f2fe83eb4cc0`.
The commit and annotated tag `a17-20261117-1` have verified SSH signatures.
The native source fix commit's SSH signature was also verified.

## Remote acceptance

- All **14 uploaded assets** matched local SHA-256 and size against
  GitHub's upload digests.
- The tag's PKGBUILD and install file were downloaded afresh.
  All nine sources were downloaded independently, checksum-verified and
  built from the uploaded draft assets.
- After publication, a second fresh staging directory downloaded the
  PKGBUILD/install file from their public release URLs. Unmodified
  `makepkg --verifysource --noconfirm` downloaded and verified all nine
  sources; `makepkg --noconfirm` passed runtime/build dependency checks
  and built the package.
- Both fresh builds matched the tested package's **269 payload entries**:
  file contents, types, permissions and symlink destinations. Package
  build timestamps/metadata are not claimed byte-reproducible.
- A fresh public download of the prebuilt package matched the exact
  tested archive:
  `c25d152bbf1bb58f43d2694d9f0ef2e02b5fe37d7785d6ba610524a5006780ad`.
- All 68 installed native bundle files and the build record matched the
  release bundle. The installed vendor image was byte-identical to the
  repacked release image before disposable copies were removed.

## Scoped cleanup

After upload and public-download/build acceptance:

- Removed task-created generated build outputs, isolated toolchain/Cargo
  caches, Rust targets, media outputs, baseline/new bundle staging,
  disposable package builds/downloads, copied system ZIP, header oracle,
  ABI/Clippy comparison staging, duplicate release archives, raw candidate
  image and failed image copy.
- Preserved tracked build recipes inside the source checkout's `build/`
  directory; that directory is not wholly disposable.
- Removed the named native-build Podman image, its six stopped Buildah
  storage containers and corresponding task-created intermediate/base
  images by exact IDs. No global prune was used.
- Kept both source checkouts, signed source history, patches, product
  sources, small evidence and rollback files. The prior package was moved
  into the rollback checkpoint and its manifest updated.
- Installed runtime, configured system/vendor images, Android app data
  and the running session were not removed. The active vendor loop
  device points to `/etc/waydroid-extra/images/vendor.img`, not build staging.
- Host package dependencies/build tools were not indiscriminately removed.

Private local evidence remains under
`~/Projects/waydroid-a17-nvidia-work/evidence/`, including
`public-release-verification.json`, `github-upload-verification.json`,
`cleanup.json` and `scaffold-before/`. Raw private logs and Android data
were not published.

The remaining administrator-only cleanup is to restore the saved
temporary `/dev/dma_heap/system` ACL and remove the explicitly named
guest codec fixtures/clients. No installed vendor/runtime or app data
should be deleted as part of that cleanup.
