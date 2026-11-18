---
name: waydroid-a17-test
description: Test this project's Waydroid Android 17 NVIDIA stack — restart the session, run guest commands, try a module through the vendor overlay, run NVDEC/NVENC Codec2 regressions and Chrome WebCodecs/WebRTC hardware-encode checks, inspect graphics/HWUI and capture Android windows. Use for Waydroid validation, regression testing, container access, logcat, overlay, screenshots or guest-side debugging.
---

# Test

Restored from `cagedbird043/waydroid-a17-nvidia` commit
`28955ede2c365c6822984e64c68b58dda673e285`, with English documentation and configurable host paths.
Upstream tested RTX 4060 Laptop, nvidia-open 615.78.08 and KDE Plasma Wayland.
Its NVIDIA render node was `/dev/dri/renderD129` (`renderD128` was AMD integrated graphics).
These are historical machine details, not assumptions or passing results for this fork.
Discover the actual GPU/render node on the current machine.

Scripts live in `.agents/skills/waydroid-a17-test/scripts/` (called `$T` below).
Scripts needing sudo honor `SUDO_ASKPASS`; interactive authentication must be available.

## Prerequisites and safe use

- A running Waydroid Android 17 NVIDIA installation and a working user Wayland session.
  Host tools: Bash, git, util-linux (`flock`, `setsid`), sudo, LXC, Python 3,
  and FFmpeg/ffprobe with libx264, libx265, libvpx-vp9 and libsvtav1 encoders.
  Build-dependent tests also need Make, Android toolchains and the complete source workspace.
- Set `WAYDROID_A17_WS` to the workspace containing `nvidia/waydroid-nvidia` and `src/`.
  The default is the release repository's parent, not this standalone checkout itself.
- `WAYDROID_DATA_DIR` overrides the host directory corresponding to guest `/data`
  (default `$HOME/.local/share/waydroid/data`).
  `WAYDROID_LXC_PATH` and `WAYDROID_LXC_NAME` override `/var/lib/waydroid/lxc` and `waydroid`.
- `WAYDROID_BRIDGE_HOST` overrides the private HTTP bridge address `192.168.240.1`;
  `WEB_ENCODE_PORT` overrides port `8765`. The page still opens on guest localhost via the
  guest loopback relay; do not bind the test server to all interfaces.
- Guest requirements include the Codec2 service, clients built from the matching sources,
  and standard Android shell tools. Seccomp tracing additionally needs guest `strace`,
  `timeout`, `lshal`, debug init controls, and host Python with `os.setns` when deploying a policy.
  The browser test requires guest Chrome, toybox netcat and the needed hardware codec support.
- These are integration tests, not dry runs: they copy fixtures/clients to guest storage,
  clear logcat, start a temporary server or restart/trace the media service as applicable.
  `session-restart.sh` stops the existing user session. Seccomp policy substitution is temporary,
  with an EXIT cleanup that attempts to restore service health and the original policy hash.
  Run only when those changes are acceptable, preserving any existing evidence.
  Choose fresh private evidence directories (`umask 077`) because logcat may contain sensitive data.
- Missing tools, workspace files or guest components must fail clearly. Syntax checks or synthetic
  report fixtures do not prove that GPU, media or NVIDIA 620 integration passes.
  Do not run live tests on a host without Waydroid or working sudo authentication.

Initial setup from the release repository root, followed by a read-only guest availability check:

```bash
export WAYDROID_A17_WS=/path/to/complete/workspace
WS=$WAYDROID_A17_WS
T=.agents/skills/waydroid-a17-test/scripts
umask 077
"$T/guest.sh" 'id'
```

## Session and container

```bash
"$T/session-restart.sh"   # Starts in the background and waits for ready; foreground session start never returns.
"$T/guest.sh" 'logcat -d -s nvc2 nvc2-enc | tail'   # Root shell in the container.
```

Initiate graphical authentication from a main terminal with `WAYLAND_DISPLAY`, `DISPLAY` and
`DBUS_SESSION_BUS_ADDRESS`, for example
`SUDO_ASKPASS=/usr/bin/ksshaskpass "$T/guest.sh" 'id'`.
Python evaluation subprocesses may not inherit these variables. If authentication fails, inspect
the display environment first; never obtain passwords from chat/history or rewrite an already
`-A`-capable helper as a workaround.

Upstream observed `lxc-attach` changing a log file's owner to root when given that regular file
as stdout. Save through an ordinary-user pipe, or restore ownership only for the current run's
logs after collection. Keep private logs mode `0600`; do not loosen permissions to fix read failures.
Starting the systemd container service alone does not start the user session. Wait for the user
session to be ready before guest deployment and version verification.

Check GPU load and free VRAM before regression testing. For RM `0x51` (`NV_ERR_NO_MEMORY`) or
gralloc `vkAllocateMemory` failures, inspect resource use first. Do not close other applications
without permission or classify resource exhaustion as a driver-version regression.
After the user frees resources, recreate the guest session and collect the new window's first error
and actual image. `ready`, `am start Status: ok` and Activity resumed are not first-frame validation.

- Guest `/data` maps to host `$WAYDROID_DATA_DIR` (default `~/.local/share/waydroid/data`);
  copy files to its `local/tmp` directory.
- Launch apps: `waydroid app launch <package>`;
  open pages: `waydroid app intent android.intent.action.VIEW <url>`.
- Inspect graphics: `"$T/guest.sh" 'dumpsys SurfaceFlinger | grep GLES:'` should show
  ANGLE → NVK on the actual NVIDIA GPU.
- `dmesg | grep -i xid` should show no new NVIDIA Xid errors.

## Try an individual module through the overlay

Use `sudo install` to place it in `/var/lib/waydroid/overlay/vendor/<same-path-as-in-vendor>`,
then run `session-restart.sh`. Services under `/vendor/odm` use
`overlay/vendor/odm/bin/hw/`, group 2000, mode 0755.
Record overlay contents after testing (`sudo find /var/lib/waydroid/overlay/vendor -type f`).
Inspect and remove test overrides before release; do not blindly delete unrelated user changes.
`media_codecs_c2.xml` is not in this overlay: it is mounted read-only from host
`/var/lib/waydroid-nvidia/vendor-image/`. Encoder-list changes require updating both its XML and
`media.xml_sha256`/`codecs` in `install.json`, otherwise service startup verification fails.

## Codec regression

```bash
make -C "$WS/nvidia/waydroid-nvidia/nvidia-prolapse/media" c2-smoke c2-enc-smoke
# Use a fresh evidence directory; this copies test clients and fixtures into the guest.
CODEC_SMOKE_OUT="$(mktemp -d /tmp/opencode/codec-evidence.XXXXXX)" "$T/codec-smoke.sh"
```

Expect 60 frames and zero bad buffers for each of four decoders; 60 pictures in / 60 out for each
of three encoders, with zero host FFmpeg decoding errors (H.264 Constrained Baseline).
Encoder/decoder switches are `persist.waydroid.nvidia_video_encode` and
`persist.waydroid.nvidia_video_decode` (`waydroid prop set`).
The script creates decoders by component name, retains client and FFmpeg/ffprobe exit statuses,
and strictly requires four decoders with 60 frames / 0 bad buffers, three encoders with 60 in / 60 out,
60 frames reported by host ffprobe, and error-free FFmpeg.
It also tests full replay after a running flush, destruction with outstanding work, and 128 bytes
of invalid `0xff` input (zero pictures, with EOS or an explicit error).
Negative gates: run separately with
`CODEC_SMOKE_FAULT=client-failure|wrong-name|truncated|bad-buffer`;
each must exit nonzero. `bad-buffer` injects an empty buffer for the client's first picture.
Evidence retains raw logs and exit codes.
For host C encoding timing, use `M/test/enc-benchmark.py OUT` where
`M="$WS/nvidia/waydroid-nvidia/nvidia-prolapse/media"`: 330 frames, discard the first 30,
five alternating-order runs, producing per-frame CSV and summary JSON.

VP9 multi-display-frame regression:
`make -C "$WS/nvidia/waydroid-nvidia/nvidia-prolapse/media" superframe-test`
generates `out/host/superframe/{vp9.mp4,pair.bin}`, checking 59 inputs, 60 frames and
incomplete/final events on the host. Copy both files and fresh clients into one guest directory:

```bash
./c2_smoke vp9.mp4 c2.nvprolapse.vp9.decoder superframe pair.bin
./c2_surface_smoke vp9.mp4 c2.nvprolapse.vp9.decoder pair.bin
```

Both must report `superframe: 2 outputs at shared PTS, total=60`.
Surface must additionally report 59 inputs, 60 outputs, 60 images, EOS and zero errors.

### Surface and seccomp windows

```bash
"$T/surface-smoke.sh" "$(mktemp -d /tmp/opencode/surface-evidence.XXXXXX)"
EVIDENCE=$(mktemp -d /tmp/opencode/seccomp-evidence.XXXXXX)
CODEC_SMOKE_OUT="$EVIDENCE/clients" \
  "$T/seccomp-check.sh" "$EVIDENCE" \
  "$WS/nvidia/waydroid-nvidia/nvidia-prolapse/media/odm/etc/seccomp_policy/android.hardware.media.c2@1.2-nvprolapse.policy"
```

Surface builds `c2_surface_smoke`; each of four named components asserts 60 inputs, 60 outputs,
60 PRIVATE Images, EOS and clean destruction. `exit-codes.tsv` retains all client exit codes.
Seccomp's second argument may be empty to use the current policy; following arguments specify
a custom steady-state workload, defaulting to `codec-smoke.sh`.
The cold window uses init `ctl.sigstop_on` to pause before exec, attaches, resumes and waits for
Store registration; the steady window attaches before running clients.
Using successful non-NULL `PR_SET_SECCOMP` as the boundary, recursively expand actual guest
includes and save pre/post-install syscall sets, per-call arguments and coverage conclusions.
Uncovered calls, unknown argument predicates or SIGSYS fail; absence of SIGSYS alone is not
a policy comparison.
An optional policy is temporarily read-only bind-mounted, with deployed SHA256 verification.
EXIT cleanup disables sigstop, stops the service, unmounts only its own bind, restarts the service
and checks the original SHA256.
Both scripts use `/tmp/wd-guest.lock`; a caller already holding it passes `WD_GUEST_LOCKED=1`
to avoid nested locking.

## Chrome hardware encoding

```bash
WEB_ENCODE_OUT="$(mktemp -d /tmp/opencode/web-evidence.XXXXXX)" "$T/web-encode-test.sh" 150
```

The page opens only in guest Chrome. Every case has a run UUID and independent ID.
Before a case starts, the page POSTs a request to clear host-collected guest logcat and waits
for acknowledgement. It POSTs JSON when done, and the host immediately archives that window's log.
All four WebCodecs cases require 60 outputs, a keyframe and no errors.
All three WebRTC cases require positive encoded-frame counts, dimensions at least 960×540,
and their own window's corresponding AVC/HEVC/AV1 component-open log.
Evidence includes per-case JSON, logcat, window-start timestamps and overall exit status.
Timeout, missing cases or any failed assertion produce a nonzero exit.

## Screenshots and desktop

- Use an available native-window tool to identify the actual `waydroid.<package>` window.
  If the environment provides `computer.window({app: "waydroid.<package>"})`, it can locate it.
  Use a fresh screenshot of the same window for screenshot/input coordinates. In multi-window mode,
  each Android app has its own KDE window. Use pixels when Android custom controls lack accessibility
  exposure; Activity resumed is not visual confirmation.
- Inspect screenshots before publishing: YouTube recommendations, notifications and account avatars
  may expose private content. Crop or change the scene.
- Temporary synthetic pages use `http.server.ThreadingHTTPServer`, bound only to the private guest
  bridge. Single-threaded `HTTPServer` blocks on connected clients that have not sent requests
  (reproduced with an idle TCP connection); do not misclassify connection failure as a rendering bug.
  Reuse `scripts/web-encode-server.py`'s guest loopback relay and
  `http://localhost:<port>/` entry point rather than creating a direct-bridge test route.
- Test clipboard directions only with unique synthetic markers. Preserve the original clipboard
  solely in memory and restore it afterward; never put it in logs or page reports.
- Before IME testing, confirm the current input method, full/double-pinyin scheme and actual trigger
  keys (including Rime internal bindings). Do not assume what `Ctrl+Space` means.
  With the same editor focused, type real keys and observe candidates and committed characters.
  Unicode injection or paste does not establish host-IME success.
  Fcitx single-group `State=1` cannot distinguish Rime's language modes; judge from its status panel,
  candidates and final committed text.

## Host Chrome/Firefox

Clear driver variables when launching:
`env -u LIBVA_DRIVERS_PATH -u LIBVA_DRIVER_NAME -u NVD_BACKEND -u NVD_LOG`.
Use a temporary experimental profile (`--user-data-dir=/tmp/...`), removing only that profile afterward.

## Debug switches

`setprop waydroid.dump_hal 1` prints layers, tasks and windows on the next frame.
Set `waydroid prop set persist.waydroid.clipboard_debug true` then restart the session
to inspect `hwcomposer` `clipboard:` lines in logcat.
After an intentional Waydroid-data reset, reinstall `/data/adb/ksud` and the KernelSU manager
(step 5 of `kernelsu/README.md`) and set
`waydroid prop set persist.waydroid.multi_windows true` again. Do not reset user data just to run tests.
