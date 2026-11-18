<div align="center">

# Waydroid A17 NVIDIA

**Android 17 on your Linux desktop, accelerated by your NVIDIA GPU.**

[![Release](https://img.shields.io/github/v/release/zealous6389/waydroid-a17-nvidia?label=release&color=76b900)](https://github.com/zealous6389/waydroid-a17-nvidia/releases/latest)
![Android 17](https://img.shields.io/badge/Android-17-3ddc84?logo=android&logoColor=white)
![NVIDIA](https://img.shields.io/badge/NVIDIA-NVK%20%2B%20NVDEC%20%2B%20NVENC-76b900?logo=nvidia&logoColor=white)
![KDE Plasma](https://img.shields.io/badge/KDE%20Plasma-Wayland-1d99f3?logo=kde&logoColor=white)
![KernelSU](https://img.shields.io/badge/root-KernelSU-orange)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
![Built with Claude Opus 5.5](https://img.shields.io/badge/built%20with-Claude%20Opus%205.5-d97757?logo=claude&logoColor=white)
![Built with GPT 6.1 Sol](https://img.shields.io/badge/built%20with-GPT%206.1%20Sol-412991)

Blog: [English](https://cagedbird.cn/2026/10/31/%E6%8A%80%E6%9C%AF%E5%AE%9E%E8%B7%B5/%E7%B3%BB%E7%BB%9F%E5%B7%A5%E7%A8%8B/%E7%B3%BB%E7%BB%9F%E7%BC%96%E7%A8%8B/Android/Waydroid-A17-NVIDIA-hardware-accelerated-Android-17-on-NVIDIA-Linux/) · [Chinese](https://cagedbird.cn/2026/10/31/%E6%8A%80%E6%9C%AF%E5%AE%9E%E8%B7%B5/%E7%B3%BB%E7%BB%9F%E5%B7%A5%E7%A8%8B/%E7%B3%BB%E7%BB%9F%E7%BC%96%E7%A8%8B/Android/Waydroid-A17-NVIDIA%EF%BC%9AN%E5%8D%A1Linux%E6%A1%8C%E9%9D%A2%E4%B8%8A%E7%9A%84%E7%A1%AC%E4%BB%B6%E5%8A%A0%E9%80%9FAndroid17/)

![Android apps as KDE windows](docs/images/multiwindow.png)

</div>

---

## NVIDIA 620 fork

Fork of [cagedbird043/waydroid-a17-nvidia](https://github.com/cagedbird043/waydroid-a17-nvidia),
adding exact **NVIDIA open 620.70.06** support from
[Shiro836/nvidia-prolapse#1](https://github.com/Shiro836/nvidia-prolapse/pull/1).
Tested on an **RTX 4060 Ti (8 GiB), CachyOS and KDE Plasma Wayland**:
22 graphics/compute gate cases plus media checks, ANGLE → NVK renderer
identity, four Android hardware decoders, three hardware encoders and
four PRIVATE Surface decoder tests passed.

Release `20261117.1-1` uses a matching rebuilt RM/NVK/nvrm native
bundle and an ext4 vendor-image repack retaining the published A17
Codec2 service and other modules. It is **not a full Android vendorimage
rebuild** and does not replace the host NVIDIA driver.
Chrome WebCodecs/WebRTC, KernelSU and broader desktop integrations have
not been retested on this fork's machine. The feature overview and
screenshots below describe the original project; they are not new
620-machine test evidence.

LineageOS 24.0 (Android 17) in Waydroid, with the GPU, the video engines, root and the desktop all working together:
Vulkan and GLES on NVIDIA through NVK, hardware video decode **and encode**, KernelSU, and every Android app as its own
KDE window.

### ✨ Highlights

| | Feature | |
|---|---|---|
| 🎮 | **GPU acceleration** | ANGLE → NVK → NVIDIA kernel driver; HWUI renders with Vulkan. WebGL and WebGPU work in Chrome. |
| 🎬 | **Hardware video decode** | H.264, HEVC, VP9 and AV1 on NVDEC — YouTube, Chrome and players use it automatically. |
| 📡 | **Hardware video encode** | H.264, HEVC and AV1 on NVENC. Chrome WebCodecs and WebRTC (video calls) encode on the GPU. |
| 🪟 | **Apps as desktop windows** | Each Android app gets its own KDE window; KWin moves, resizes and closes it. Positions are remembered. |
| ⌨️ | **Host input method** | Type in Android with fcitx5 or ibus; the candidate window follows the cursor. |
| 📋 | **Clipboard and files** | Two-way clipboard. `~/Downloads` shows up in Android as `Download/Host`. |
| 🖱️ | **Mouse as touch** | Drags become finger swipes in apps that ignore the mouse (Play Store and other Compose UIs). |
| 🔓 | **Root** | KernelSU on the host kernel, with modules (Zygisk Next, LSPosed and friends). |
| 🛒 | **Google apps** | Use ATV's GAPPS system image; Play Store is certified. |

The maintenance build updates Mesa to **26.2.6**, retains the local graphics/compute queue support, and pairs the
current Rust RM encoding-parameter/RGB fixes with its Codec2 service. Codec2 decoding is also Rust: VP9 packets
with multiple displayed frames deliver every frame, CSD is capped at 2 MiB, and gralloc handles/layouts are validated.
The Codec2 sandbox permits its logging socket, including cold starts.

KernelSU **32713** keeps the container adaptations and the existing signing certificate, with targeted shell-escaping,
profile/template-path and file-reference fixes; see [`kernelsu/`](kernelsu/).
The ATV system image is unchanged (SPL **2026-10-01**). Saved system-security source patches are not a deployed
system update or a complete November ASB. The performance tables below are earlier measurements; this maintenance
update has no new FPS, CPU-use or latency A/B result.

### 📸 Screenshots

| Chrome: everything hardware accelerated | YouTube on NVDEC |
|---|---|
| ![chrome://gpu](docs/images/chrome-gpu.png) | ![YouTube](docs/images/youtube.png) |

| KernelSU working | |
|---|---|
| ![KernelSU](docs/images/kernelsu.png) | |

### 🚀 Performance

| Benchmark (4K, Vulkan) | Host, NVIDIA driver | Waydroid | |
|---|---|---|---|
| Basemark GPU, Medium, offscreen | 35657 | 29369 | 82 % |
| 3DMark Wild Life Extreme | — | 12300–13100 (≈ 74 FPS) | |

| Encode, 1080p, RTX 4060 Laptop | H.264 | HEVC | AV1 |
|---|---|---|---|
| GPU time per frame | 1.7–2.4 ms | 2.0 ms | 1.4 ms |

Basemark on Android only ships ETC2 textures, which NVK has to emulate, while the host uses BC7, so the comparison
favours the host.

### 📦 Install (Arch Linux)

```bash
git clone https://github.com/zealous6389/waydroid-a17-nvidia.git
cd waydroid-a17-nvidia
git checkout a17-20261117-1
cd aur/waydroid-a17-nvidia-bin
makepkg --verifysource
makepkg -si
```

Release tag: `a17-20261117-1`. No AUR account,
AUR helper or AUR publication is needed. The checksum-pinned PKGBUILD
downloads prebuilt assets; it does not compile Mesa, Rust or Android.
Review the PKGBUILD before running it. Arch build tools (`base-devel`
and `git`) are required, alongside the runtime dependencies it declares.

Then add the system image ([WayDroid-ATV `20261017`](https://github.com/WayDroid-ATV/waydroid-builds/releases/tag/20261017), GAPPS or VANILLA) and set up:

```bash
sudo mkdir -p /etc/waydroid-extra/images
sudo bsdtar -xf lineage-24.0-20261017-GAPPS-waydroid_x86_64-system.zip -C /etc/waydroid-extra/images system.img
sudo bsdtar -xf /usr/lib/waydroid-nvidia/vendor/waydroid-nvidia-vendor-x86_64-*.zip -C /etc/waydroid-extra/images vendor.img
sudo waydroid init -f
sudo waydroid-nvidia-setup      # tests the vendor image on your GPU, then installs it
waydroid prop set persist.waydroid.multi_windows true
waydroid session start
```

Needs the NVIDIA **open** kernel modules and binder (binderfs). Run `sudo waydroid-nvidia-setup` again after an
NVIDIA driver update. Root: [`kernelsu/`](kernelsu/).

> [!IMPORTANT]
> Original `20261111.1` binaries do not support NVIDIA **620.70.06**.
> Use the matching fork package/vendor pair, not an individual replacement library.
> Unknown driver versions still fail closed. After a driver update, setup may reject it
> until that exact version is supported; do not bypass the gate.

<details>
<summary>Other distributions</summary>

The fork's package is tested only on CachyOS/Arch. Other distributions
need equivalent host integration and are not validated by this release.
From the fork's [Releases](https://github.com/zealous6389/waydroid-a17-nvidia/releases),
use the single vendor ZIP and native bundle from the same tag; do not
combine original split-image assets with this fork's native libraries.

Install the host side of [waydroid-nvidia](https://github.com/Shiro836/waydroid-nvidia) with `patches/waydroid-nvidia/`
applied, extract the bundle into `/usr/lib/waydroid-nvidia/native/release/`, put `system.img` and `vendor.img` into
`/etc/waydroid-extra/images/` and run `waydroid-nvidia-setup`. The [PKGBUILD](aur/waydroid-a17-nvidia-bin/PKGBUILD)
shows the exact layout.
</details>

<details>
<summary>Handy switches</summary>

| Command | Effect |
|---|---|
| `waydroid prop set persist.waydroid.multi_windows true` | One KDE window per app |
| `waydroid show-full-ui` | The whole Android desktop in one window |
| `waydroid prop set persist.waydroid.fake_touch "com.android.vending"` | Mouse drags as touch in these apps (`*` = all) |
| `waydroid prop set persist.waydroid.nvidia_video_decode off` | Software video decoding |
| `waydroid prop set persist.waydroid.nvidia_video_encode off` | Software video encoding |

Folders shared into Android: `shared_folders` in the `[waydroid]` section of `/var/lib/waydroid/waydroid.cfg`, one
`host folder:storage path` per line. The KWin script that remembers window positions: System Settings → Window
Management → KWin Scripts → "Waydroid card placement".
</details>

> [!NOTE]
> The original project was tested on RTX 4060 Laptop, NVIDIA open 615.78.08, KDE Plasma 6 Wayland,
> Arch Linux. This fork's 620 test machine and limitations are listed above.
> Original performance tables and screenshots are not RTX 4060 Ti benchmarks.
> Widevine is L3, so streaming apps usually play SD. Issues and PRs are welcome; replies are not guaranteed.
> Developed together with Claude Opus 5.5 and GPT 6.1 Sol.

### 🙏 Acknowledgements

- [Shiro836/waydroid-nvidia](https://github.com/Shiro836/waydroid-nvidia) — the nvidia-prolapse mode, NVK and the Rust RM driver, ANGLE, the NVDEC Codec2 component and most hwcomposer fixes. This project would not exist without it.
- [WayDroid-ATV](https://github.com/WayDroid-ATV) (supechicken) — the Android 17 system image and device tree, and [KernelSU for Waydroid](https://github.com/supechicken/KernelSU).
- [mickys/nvenc](https://github.com/mickys/nvenc) — the NVENC encoder core; [NVIDIA/open-gpu-doc](https://github.com/NVIDIA/open-gpu-doc) — the NVENC class headers.
- [Waydroid](https://github.com/waydroid/waydroid), [LineageOS](https://lineageos.org), [KernelSU](https://github.com/tiann/KernelSU), [Mesa](https://mesa3d.org), [ANGLE](https://chromium.googlesource.com/angle/angle), and the authors of the wayland-protocols `text-input-v3` and `ext-data-control-v1`.

Original code here is [MIT](LICENSE). The patches under `patches/` keep their upstream licenses (Apache-2.0, BSD-3-Clause,
MIT/HPND, GPL-3.0 as appropriate) and `nvidia-product/` keeps waydroid-nvidia's; the vendor image contains these
projects under their own licenses.
