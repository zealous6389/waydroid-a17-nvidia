# KernelSU (LKM, host DKMS)

Waydroid shares the host kernel, so KernelSU is installed on the host as a kernel module. The maintained source is based on supechicken's `waydroid-experimental` branch; when the container starts, Android's init runs `/data/adb/ksud`.

The kernel module trusts only one manager signature. The pre-signed Manager and the matching DKMS package use the
maintainer's public certificate; when signing yourself, you must replace `_ksu_expected_size` / `_ksu_expected_hash` in
`kernelsu-dkms/PKGBUILD` with your own certificate length and SHA-256.
The version counters of the Manager, ksud and the module must match as well.

The commands below run from the workspace root (the parent of `publish/`) and need podman, an existing `localhost/ksu-manager-build` build image, and the full source bundle of the same maintained version. The build image definition is in `publish/kernelsu/manager/Containerfile`.

## 1. Manager source

```bash
mkdir -p ksu
cp publish/kernelsu/manager/* ksu/
# After placing the maintained KernelSU-4e752f94.bundle into ksu/out/:
git clone ksu/out/KernelSU-4e752f94.bundle ksu/KernelSU
git -C ksu/KernelSU checkout 4e752f941797dfe203788d618e026abf5a1088b5
```

The versionCode of the Manager, ksud and the module is `30000 + git rev-list --count HEAD`. All three must come from the same complete (non-shallow) source commit; `sign-manager.sh` checks the versionCode of the APK about to be signed against the current source count and refuses to sign on a mismatch.

The maintained `v3.3.1-33-g4e752f94` (count `2713`, versionCode `32713`) keeps the seven container/LKM adaptations from b42ad459 and backports only three official fixes — Manager shell argument escaping, ksud profile/template path validation, and the wrapped-file reopen reference balance — plus path-boundary tests and a fix for three dangling bitflags version references in the lock file; the upstream branch as a whole is not upgraded.

The maintained Manager APK, DKMS package and full source `KernelSU-4e752f94.bundle` ship with
[`a17-20261111-1`](https://github.com/cagedbird043/waydroid-a17-nvidia/releases/tag/a17-20261111-1).
Source bundle SHA-256: `012f19894b81ae606f17bcec0673e16ce3d810bdf1c881abc888cfdd8c81632a`.

## 2. Generate your own signing key

```bash
mkdir -p ksu/keystore && chmod 700 ksu/keystore
cat > ksu/keystore/README <<'EOF'
KEYSTORE_FILE=/work/keystore/ksu-local.jks
KEY_ALIAS=ksu-local
KEYSTORE_PASSWORD=<your choice>
KEY_PASSWORD=<your choice>
EOF
chmod 600 ksu/keystore/README
podman build -t localhost/ksu-manager-build -f ksu/Containerfile ksu
podman run --rm -v "$PWD/ksu:/work" localhost/ksu-manager-build bash /work/generate-key.sh
```

`ksu/keystore/` holds the private key of your root manager; never commit or expose it.

## 3. Build and sign the Manager

```bash
podman run --rm --cpus=4 -v "$PWD/ksu/KernelSU:/work/KernelSU" \
  -v "$PWD/ksu/build-manager.sh:/work/build-manager.sh:ro" \
  -v "$PWD/ksu/x86_64.init.gradle:/work/x86_64.init.gradle:ro" \
  -v ksu-gradle-cache:/root/.gradle -v ksu-cargo-cache:/root/.cargo/registry \
  -v ksu-cargo-git:/root/.cargo/git \
  localhost/ksu-manager-build bash /work/build-manager.sh
podman run --rm -v "$PWD/ksu:/work" localhost/ksu-manager-build bash /work/sign-manager.sh
APK=ksu/out/KernelSU_v3.3.1-33-g4e752f94_32713-local.apk
python3 ksu/apk_certificate.py "$APK"
```


Path validation uses a shared module that is independent of Android, so the host unit test must run `cargo test --locked --jobs 4 --manifest-path userspace/ksud/Cargo.toml profile_path::tests` and see two tests execute. The `profile` module is only built for Android, so filtering on `profile::tests` on the host yields zero tests and does not count as validation. The container keeps using the three KSU-specific caches above and `--cpus=4`; the Manager unit-test command is `./gradlew --no-daemon --max-workers=4 -I /work/x86_64.init.gradle :app:testDebugUnitTest`, since this tree registers no release unit-test task. The build mounts do not include the private key directory.
The last command prints `KSU_EXPECTED_SIZE` and `KSU_EXPECTED_HASH`. Only v2 signing is used (the kernel does not accept v3 or other signature blocks).

## 4. Build and install the kernel module

```bash
# The PKGBUILD fetches the complete source bundle with a pinned SHA-256 from the same Release.
# When it is already downloaded to ksu/out/, reuse that cache instead of touching the yay cache:
(cd publish/kernelsu/kernelsu-dkms && \
  SRCDEST="$(realpath ../../../ksu/out)" makepkg --cleanbuild --noconfirm)
# Installation must be run separately by the deployer; it may trigger a DKMS build, so confirm the kernel headers are installed first.
sudo pacman -U publish/kernelsu/kernelsu-dkms/kernelsu-dkms-3.3.1+33+g4e752f94-1-any.pkg.tar.zst
sudo install -m 644 publish/host/kernelsu-load.service /etc/systemd/system/
sudo systemctl enable --now kernelsu-load.service
```

`kernelsu-load.service` loads the module before `waydroid-container`.

## 5. Install into Android

`ksud` already ships inside the Manager APK (`lib/x86_64/libksud.so`):

```bash
APK=ksu/out/KernelSU_v3.3.1-33-g4e752f94_32713-local.apk
unzip -p "$APK" lib/x86_64/libksud.so > /tmp/ksud &&
  sudo install -D -m 755 -o root -g root /tmp/ksud ~/.local/share/waydroid/data/adb/ksud
# Start the desktop user's Waydroid session first and wait until Android is ready; starting only the container service is not enough.
waydroid session stop >/dev/null 2>&1; sleep 3
setsid -f bash -c 'exec waydroid session start > /tmp/wd-session.log 2>&1' </dev/null >/dev/null 2>&1
for _ in $(seq 1 90); do
  grep -q 'ready' /tmp/wd-session.log && break
  sleep 2
done
if grep -q 'ready' /tmp/wd-session.log; then
  # Run ksud as root inside the guest container; sudo prompts in the terminal.
  sudo lxc-attach -P /var/lib/waydroid/lxc -n waydroid \
    --clear-env -v PATH=/system/bin:/vendor/bin -- /system/bin/sh -c '/data/adb/ksud install' &&
    waydroid app install "$APK" &&
    waydroid app launch me.weishu.kernelsu
else
  printf '%s\n' 'Session not ready. Stop and resolve the failure in /tmp/wd-session.log before installing or launching.' >&2
fi
```

If `ready` is absent after the wait, stop and resolve the session failure before running any installation or launch commands. `OSError` is an error, not readiness.

The Manager home screen should show Working (LKM). After wiping Waydroid's data, redo step 5.

## Deployment boundaries

Manager/ksud can be rebuilt; only the deployer signs, running the existing signing script with the original key. The build does not need `keystore/` mounted; do not read or record its contents. The recorded public certificate length is `0x02ec`, and its SHA-256 is `d77ee93d9af4c1dbf8b89cf50fd9953db3a61b9142e009a9effeeedb5693eb4f`.

Installing the DKMS package does not mean the running module has been updated. The wrapped-file-reference fix only takes effect once the new module is actually loaded; do not force-unload a module that is currently providing root. Before deploying, confirm that Waydroid is stopped, that nothing else uses the module, that the module unloads cleanly, and that the new module has been built successfully for the current kernel. Only after Waydroid is stopped and the old module has been successfully unloaded, run `sudo systemctl restart kernelsu-load.service` to load the new module, and confirm that it loaded successfully before starting Waydroid. If the old module cannot be unloaded safely, keep it running and mark the kernel fix as pending activation — do not restart the service, reboot the host or disturb RustDesk. Protect `/data` and the original key before updating, and do not wipe the Android data.
