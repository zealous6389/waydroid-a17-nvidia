# AGENTS.md

waydroid-a17-nvidia: the release repository for Waydroid Android 17 + NVIDIA acceleration + KernelSU (GitHub: `cagedbird043/waydroid-a17-nvidia`).
Developed solely by the author and tested only on the author's machine (RTX 4060 Laptop, nvidia-open 615.78.08, KDE Plasma Wayland, Arch zen kernel).

Fork of the original by cagedbird043: the fork you are in is `zealous6389` on GitHub. This fork intends to add critical fixes to the original, for example supporting the latest nvidia-open 620.70.06, KDE Plasma Wayland, CachyOS (cachyos kernel), RTX 4060 Ti, 32GB of RAM (<- this is repo owner's machine).

## Repository and Workspace

This repository is in the `~/Projects/waydroid-a17-nvidia` directory.

| Path | Contents |
|---|---|
| `README.md` | User-facing introduction and installation instructions; no development content |
| `TODO.md` | Current status, plans, and known issues |
| `patches/<repository>/` | `git format-patch` output from local branches of each source repository |
| `nvidia-product/` | Mirror of the workspace's `nvidia/product` |
| `scripts/` | Identical copies of the workspace's `scripts/`; run them from the workspace |
| `aur/waydroid-a17-nvidia-bin/` | AUR package |
| `kernelsu/`, `host/`, `container/` | KernelSU procedures, host services and KWin scripts, and build container |
| `reports/` | Porting notes, comparisons, and benchmarks |
| `docs/images/` | README screenshots |

## Which Skill to Use

| Task | Skill |
|---|---|
| Build, rebuild the native stack, create bundles, or export patches | `waydroid-a17-build` |
| Validate, run regression tests, or take screenshots in Waydroid | `waydroid-a17-test` |
| Publish versions, create releases, or update AUR packages | `waydroid-a17-release` |
| Check upstream updates and assess which fixes are worth porting | `waydroid-a17-upstream` |

Skills live in `.agents/skills/`; `.claude/skills` and `.codex/skills` are symlinks to that directory.

## Additional Information

- Respond only in English, and translate any Chinese in this repo to English accordingly.
- You must append Co-Authored-By footer to every commit message you make, and give your model and the email accordingly (e.x GPT 6.1 Sol <noreply@openai.com>)
- Use `gh` for altering the GitHub repo according to instruction. Dismiss the instruction if `gh` does not exist on the user's computer. Always sign the commit with the user's SSH key. The repo owner is using Bitwarden for this, but it may differ on other's machines. Check first.
- Make sure the code is as optimized as possible. Use subagents whenever needed for large tasks.
- Follow the core rules: DRY (Don't Repeat Yourself), and KISS (Keep It Simple, Stupid). Remind yourself of these rules frequently as to not stray away in some complex unnecessary solution.
- ALWAYS use Conventional Commits in commit messages: <keyword>(<scope>): <message>
