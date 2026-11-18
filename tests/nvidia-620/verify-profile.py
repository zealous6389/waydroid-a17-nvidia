#!/usr/bin/env python3
"""Verify the complete 620.70.06 Rust profile against independently compiled C.

Usage: python tests/nvidia-620/verify-profile.py --data PATH/compat_data.rs
       --ogkm PATH/open-gpu-kernel-modules --output /tmp/opencode/620-proof

Requires cc, objcopy, libdrm development headers and m32/m64 C headers.
Does not link executables, load drivers, skip constants, or modify inputs.
The output retains C, ELF objects, decoded values and header provenance.
"""
import argparse
import functools
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess


COMMIT = "e6a2e01579fbbd1ca2ed43fef2ee2589e9bd8bd9"
INCLUDES = [
    "src/common/sdk/nvidia/inc", "src/common/inc",
    "src/nvidia/arch/nvalloc/unix/include", "kernel-open/common/inc",
    "kernel-open/nvidia-drm", "src/nvidia-modeset/kapi/interface",
    "src/nvidia-modeset/interface", "src/common/unix/common/inc",
]
# Metadata names are sometimes logical aliases, not C identifiers. Every
# exception is explicit and computed from public definitions, never Rust values.
EXPRESSIONS = {
    "ADDR_SPACE_TYPE_SYSMEM": "NV0000_CTRL_CMD_CLIENT_GET_ADDR_SPACE_TYPE_SYSMEM",
    "ADDR_SPACE_TYPE_VIDMEM": "NV0000_CTRL_CMD_CLIENT_GET_ADDR_SPACE_TYPE_VIDMEM",
    "LAYOUT_CAPS_64BIT_SEMAPHORES_SUPPORTED":
        "NV2080_CTRL_FB_GET_SEMAPHORE_SURFACE_LAYOUT_CAPS_64BIT_SEMAPHORES_SUPPORTED",
    "LAYOUT_CAPS_MONITORED_FENCE_SUPPORTED":
        "NV2080_CTRL_FB_GET_SEMAPHORE_SURFACE_LAYOUT_CAPS_MONITORED_FENCE_SUPPORTED",
    "NVOS33_FLAGS_MAPPING_MASK": "DRF_SHIFTMASK(NVOS33_FLAGS_MAPPING)",
    "NVOS33_FLAGS_MAPPING_REFLECTED_ENCODED":
        "(NVOS33_FLAGS_MAPPING_REFLECTED << DRF_SHIFT(NVOS33_FLAGS_MAPPING))",
    "NV_CHANNELGPFIFO_NOTIFICATION_STATUS_IN_PROGRESS_bit":
        "DRF_SHIFT(NV_CHANNELGPFIFO_NOTIFICATION_STATUS_IN_PROGRESS)",
    "NV_CTXSHARE_SUBCONTEXT_ASYNC": "NV_CTXSHARE_ALLOCATION_FLAGS_SUBCONTEXT_ASYNC",
    "NV_CTXSHARE_SUBCONTEXT_SYNC": "NV_CTXSHARE_ALLOCATION_FLAGS_SUBCONTEXT_SYNC",
    "PERF_BOOST_ASYNC_FLAG": "DRF_DEF(2080, _CTRL_PERF_BOOST_FLAGS, _ASYNC, _YES)",
}
for _name in [
    "NVC96F_GP_ENTRY1_LENGTH", "NVC96F_GP_ENTRY1_LEVEL", "NVC96F_GP_ENTRY1_SYNC",
    "NVC96F_MEM_OP_D_OPERATION", "NVC96F_SEM_EXECUTE_PAYLOAD_SIZE",
    "NVC96F_SEM_EXECUTE_RELEASE_WFI",
]:
    EXPRESSIONS[_name + "_shift"] = "DRF_SHIFT(" + _name + ")"
for _name, _field in [
    ("NVOS32_ATTR2_GPU_CACHEABLE_NO", "NVOS32_ATTR2_GPU_CACHEABLE"),
    ("NVOS32_ATTR2_GPU_CACHEABLE_YES", "NVOS32_ATTR2_GPU_CACHEABLE"),
    ("NVOS32_ATTR_COHERENCY_CACHED", "NVOS32_ATTR_COHERENCY"),
    ("NVOS32_ATTR_LOCATION_PCI", "NVOS32_ATTR_LOCATION"),
    ("NVOS32_ATTR_PHYSICALITY_ALLOW_NONCONTIGUOUS", "NVOS32_ATTR_PHYSICALITY"),
    ("NVOS32_ATTR_PHYSICALITY_CONTIGUOUS", "NVOS32_ATTR_PHYSICALITY"),
    ("NVOS46_FLAGS_CACHE_SNOOP_ENABLE", "NVOS46_FLAGS_CACHE_SNOOP"),
    ("NVOS46_FLAGS_DMA_OFFSET_FIXED_TRUE", "NVOS46_FLAGS_DMA_OFFSET_FIXED"),
    ("NVOS46_FLAGS_PAGE_KIND_OVERRIDE_YES", "NVOS46_FLAGS_PAGE_KIND_OVERRIDE"),
    ("NVOS46_FLAGS_PAGE_SIZE_4KB", "NVOS46_FLAGS_PAGE_SIZE"),
]:
    EXPRESSIONS[_name] = "(" + _name + " << DRF_SHIFT(" + _field + "))"
for _name, _escape, _type in [
    ("card_info_64", "NV_ESC_CARD_INFO", "64 * sizeof(nv_ioctl_card_info_t)"),
    ("check_version", "NV_ESC_CHECK_VERSION_STR", "sizeof(nv_ioctl_rm_api_version_t)"),
    ("register_fd", "NV_ESC_REGISTER_FD", "sizeof(nv_ioctl_register_fd_t)"),
    ("rm_alloc", "NV_ESC_RM_ALLOC", "sizeof(NVOS21_PARAMETERS)"),
    ("rm_control", "NV_ESC_RM_CONTROL", "sizeof(NVOS54_PARAMETERS)"),
    ("rm_free", "NV_ESC_RM_FREE", "sizeof(NVOS00_PARAMETERS)"),
    ("rm_map_memory", "NV_ESC_RM_MAP_MEMORY", "sizeof(nv_ioctl_nvos33_parameters_with_fd)"),
    ("rm_map_memory_dma", "NV_ESC_RM_MAP_MEMORY_DMA", "sizeof(NVOS46_PARAMETERS)"),
    ("rm_unmap_memory", "NV_ESC_RM_UNMAP_MEMORY", "sizeof(NVOS34_PARAMETERS)"),
    ("rm_unmap_memory_dma", "NV_ESC_RM_UNMAP_MEMORY_DMA", "sizeof(NVOS47_PARAMETERS)"),
]:
    EXPRESSIONS["ioctl_" + _name] = (
        "_IOC(_IOC_READ | _IOC_WRITE, NV_IOCTL_MAGIC, " + _escape + ", " + _type + ")"
    )


def run(command, **kwargs):
    return subprocess.check_output(command, text=True, **kwargs).strip()


def parse(data):
    def exact_matches(pattern, text):
        matches = re.findall(pattern, text)
        if re.sub(pattern, "", text).strip(" \t\r\n,"):
            raise ValueError("unparsed profile content: " + text[:120])
        return matches

    layouts = {}
    for match in re.finditer(
        r'static (L\d+): Layout = Layout \{ name: "([^"]+)", size: (\d+), fields: &\[(.*?)\] \};',
        data, re.S,
    ):
        fields = exact_matches(r'Field \{ name: "([^"]+)", offset: (\d+), len: (\d+) \}', match[4])
        if len({field[0] for field in fields}) != len(fields):
            raise ValueError("duplicate layout fields")
        layouts[match[1]] = (match[2], int(match[3]), fields)
    profiles = {}
    for match in re.finditer(
        r'static (P\d+): Profile = Profile \{ layouts: &\[(.*?)\]\s*, constants: (.*?) \};',
        data, re.S,
    ):
        profiles[match[1]] = (exact_matches(r'\("([^"]+)", &(L\d+)\)', match[2]), match[3])
    membership = re.findall(r'\("620\.70\.06", &(P\d+)\)', data)
    if len(membership) != 1:
        raise ValueError("expected exactly one 620.70.06 membership entry")
    profile = membership[0]

    def constants(name, seen=()):
        if name in seen:
            raise ValueError("cyclic constant-table reference")
        text = profiles[name][1]
        if re.fullmatch(r'P\d+\.constants', text):
            return constants(text.split(".")[0], (*seen, name))
        if not (text.startswith("&[") and text.endswith("]")):
            raise ValueError("unrecognized constants syntax: " + text[:80])
        return [(name, int(value)) for name, value in exact_matches(r'\("([^"]+)", (\d+)\)', text[2:-1])]

    entries, _ = profiles[profile]
    cc = constants(profile)
    if not entries or not cc:
        raise ValueError("empty profile")
    if len({name for name, _ in entries}) != len(entries) or len({name for name, _ in cc}) != len(cc):
        raise ValueError("duplicate profile keys")
    return profile, [(name, layouts[lid]) for name, lid in entries], cc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--ogkm", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    tree = args.ogkm.resolve()
    commit = run(["git", "-C", str(tree), "rev-parse", "HEAD"])
    if commit != COMMIT:
        raise ValueError("OGKM checkout is not the pinned 620.70.06 commit: " + commit)
    subprocess.run(["git", "-C", str(tree), "diff", "--quiet", "HEAD", "--", *INCLUDES], check=True)
    source = args.data.read_text()
    profile, entries, constants = parse(source)
    if (len(entries), len(constants)) != (76, 203):
        raise ValueError("incomplete 620.70.06 profile: expected 76 layouts and 203 constants")
    headers = []
    for directory in INCLUDES:
        for header in sorted((tree / directory).rglob("*.h")):
            headers.append((str(header.relative_to(tree / directory)), header.read_text(errors="replace")))

    @functools.cache
    def find_header(symbol):
        escaped = re.escape(symbol)
        declaration = re.compile(
            r'#\s*define\s+' + escaped + r'\b|'
            r'\}\s*' + escaped + r'\s*;|'
            r'struct\s+' + escaped + r'\s*\{|'
            r'\b' + escaped + r'\s*(?:=|,)|'
            r'typedef\s+[\w\s]+\b' + escaped + r'\s*;'
        )
        return next((path for path, text in headers if symbol in text and declaration.search(text)), None)

    selected = [
        "nvtypes.h", "nvmisc.h", "nvstatus.h", "nvos.h", "class/clc96f.h",
        "ctrl/ctrl2080/ctrl2080perf.h",
    ]
    symbols = [name for name, _ in entries]
    symbols += [EXPRESSIONS.get(name, name) for name, _ in constants]
    for symbol in symbols:
        # Derived expressions contain references to public constants/types.
        for token in re.findall(r'\b[A-Za-z_]\w*\b', symbol):
            header = find_header(token)
            if header and header not in selected:
                selected.append(header)
    queries = []

    def add(key, expression, expected):
        queries.append((key, expression, expected))

    for name, (declared_name, size, fields) in entries:
        if name != declared_name:
            raise ValueError("layout name mismatch: " + name)
        typ = ("struct " if name.startswith(("drm_", "NvKmsKapiPriv")) else "") + name
        add(name + ".sizeof", "sizeof(" + typ + ")", size)
        for field, offset, width in fields:
            add(name + "." + field + ".offset", "offsetof(" + typ + ", " + field + ")", int(offset))
            add(name + "." + field + ".width", "sizeof(((" + typ + " *)0)->" + field + ")", int(width))
    for name, value in constants:
        add(name, EXPRESSIONS.get(name, name), value)
    # Deliberately omitted from logical Rust fields; verify their real storage.
    for typ, field, offset in [
        ("NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS", "reserved2", 24),
        ("NV_CTXSHARE_ALLOCATION_PARAMETERS", "reserved", 12),
    ]:
        add(typ + "." + field + ".offset", "offsetof(" + typ + ", " + field + ")", offset)
        add(typ + "." + field + ".width", "sizeof(((" + typ + " *)0)->" + field + ")", 4)
    code = "#include <stddef.h>\n#include <stdint.h>\n#include <sys/ioctl.h>\n"
    code += "#include <drm.h>\n#include <linux/sync_file.h>\n"
    code += "".join("#include <" + h + ">\n" for h in selected)
    code += 'const uint64_t probe[] __attribute__((section(".abi620"), used)) = {\n'
    code += "".join("    (uint64_t)(" + expression + "),\n" for _, expression, _ in queries)
    code += "};\n"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    c_file = out / "probe.c"
    c_file.write_text(code)
    drm_flags = shlex.split(run(["pkg-config", "--cflags", "libdrm"]))
    outputs = {}
    commands = []
    dependencies = set()
    for abi in ["m32", "m64"]:
        obj, binary, deps = out / (abi + ".o"), out / (abi + ".bin"), out / (abi + ".d")
        command = [
            args.cc, "-" + abi, "-std=gnu11", "-Wall", "-Werror",
            *["-I" + str(tree / p) for p in INCLUDES], *drm_flags,
            "-MD", "-MF", str(deps), "-c", str(c_file), "-o", str(obj),
        ]
        commands.append(command)
        subprocess.run(command, check=True)
        subprocess.run(["objcopy", "--dump-section", ".abi620=" + str(binary), str(obj)], check=True)
        raw = binary.read_bytes()
        if len(raw) != 8 * len(queries):
            raise ValueError("unexpected ELF section size")
        values = struct.unpack("<" + "Q" * len(queries), raw)
        outputs[abi] = {key: value for (key, _, _), value in zip(queries, values)}
        (out / ("probe-" + abi + ".json")).write_text(json.dumps(outputs[abi], indent=2) + "\n")
        dependencies.update(shlex.split(deps.read_text().replace("\\\n", " ").split(":", 1)[1]))
        mismatches = [
            f"{key}: C={value:#x}, profile={expected:#x}"
            for (key, _, expected), value in zip(queries, values) if value != expected
        ]
        if mismatches:
            raise ValueError(abi + " mismatches:\n" + "\n".join(mismatches))
    if outputs["m32"] != outputs["m64"]:
        raise ValueError("m32/m64 differ")
    # An untracked or locally edited header must not masquerade as pinned
    # upstream evidence, even if it happened to produce the expected values.
    for path in sorted(dependencies):
        header = Path(path).resolve()
        if header.is_relative_to(tree):
            relative = str(header.relative_to(tree))
            expected_blob = run(["git", "-C", str(tree), "rev-parse", COMMIT + ":" + relative])
            actual_blob = run(["git", "-C", str(tree), "hash-object", str(header)])
            if actual_blob != expected_blob:
                raise ValueError("header differs from pinned commit: " + relative)
    proof = {
        "ogkm_commit": commit, "profile": profile, "layouts": len(entries),
        "constants": len(constants), "checks_per_abi": len(queries),
        "compiler": run([args.cc, "--version"]).splitlines()[0], "commands": commands,
        "profile_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "probe_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "headers_sha256": {
            str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in sorted(dependencies) if Path(path).resolve() != c_file
        },
        "method": "Compile exact public C headers into m32/m64 ELF data; no executable or GPU",
    }
    (out / "provenance.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(f"PASS {profile}: {len(entries)} layouts, {len(constants)} constants, "
          f"{len(queries)} checks per ABI (m32/m64); evidence: {out}")


if __name__ == "__main__":
    main()
