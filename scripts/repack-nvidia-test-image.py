#!/usr/bin/env python3
"""TEST ONLY: repack a duplicate ext4 vendor image; NOT a full vendorimage build.

Usage: repack-nvidia-test-image.py [--validate-only] SOURCE_CHECKOUT NEW_BUNDLE
                                 BASE_VENDOR_IMAGE NEW_OUTPUT_IMAGE

Run --validate-only without sudo first. Repacking requires root for loop mounting
ONLY the clone (rw,nosuid,nodev,noexec). No activation, package installation,
configuration edits, service restarts or publication are performed. All existing
A17 modules, the Codec2 service and build date are retained. This does not replace
the full Android build or GPU release gate.
The clone gains 128 MiB of temporary filesystem headroom before mounting;
after unmounting it is checked, minimized and truncated to its filesystem size.

The output parent must already exist outside system directories. Failed .partial
images and .repack.log files are retained; use a fresh output name to retry.
Do not modify the checkout, bundle, base or output directory concurrently.
"""

import argparse
import contextlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import traceback

VERSION = 'ro.vendor.nvidia_prolapse.version'
RECORD = 'ro.vendor.nvidia_prolapse.build_record'
SERVICE = 'payload/odm/bin/hw/android.hardware.media.c2@1.2-service-nvprolapse'
FORBIDDEN = ('/etc', '/var', '/usr', '/bin', '/sbin', '/lib', '/lib64',
             '/boot', '/dev', '/proc', '/sys', '/run')
CLONE_HEADROOM = 128 << 20


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def beneath(path, parent):
    return path == parent or parent in path.parents


def validate_paths(source, bundle, base, output):
    source, bundle, base = (Path(p).resolve(strict=True) for p in (source, bundle, base))
    output = Path(output).absolute()
    if output.is_symlink() or output.exists():
        raise ValueError('output must not exist (including symlinks)')
    output = output.parent.resolve(strict=True) / output.name
    if not output.parent.is_dir():
        raise ValueError('output parent must be an existing directory')
    # vendor_image.image_file uses an unquoted debugfs dump destination.
    if any(c.isspace() or c in '"\\' for c in str(output)):
        raise ValueError('output path must not contain whitespace, quotes or backslashes')
    if any(beneath(output, Path(p).resolve()) for p in FORBIDDEN):
        raise ValueError('output must be in a private workspace, not a system directory')
    if not source.is_dir() or not bundle.is_dir() or not base.is_file():
        raise ValueError('source/bundle must be directories and base must be a regular file')
    if output == base or beneath(output, source) or beneath(output, bundle):
        raise ValueError('output must not overlap the base, source checkout or bundle')
    for suffix in ('.partial', '.repack.log'):
        candidate = Path(str(output) + suffix)
        if candidate.exists() or candidate.is_symlink():
            raise ValueError(f'refusing existing output artifact: {candidate}')
    return source, bundle, base, output


def parse_identity(text):
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        key = key.strip()
        if sep and key in (VERSION, RECORD):
            if key in values:
                raise ValueError(f'duplicate property: {key}')
            values[key] = value.strip()
    if set(values) != {VERSION, RECORD}:
        raise ValueError('build.prop must contain exactly one version and build_record')
    return values


def update_identity(text, release, digest):
    parse_identity(text)
    if not isinstance(release, str) or not release or any(c in release for c in '\r\n'):
        raise ValueError('invalid release identity')
    replacements = {VERSION: release, RECORD: digest}
    lines = []
    for line in text.splitlines(keepends=True):
        key, sep, _ = line.partition('=')
        if sep and key.strip() in replacements:
            ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
            line = key + '=' + replacements[key.strip()] + ending
        lines.append(line)
    return ''.join(lines)


def check_base_identity(text, record):
    identity = parse_identity(text)
    previous = record.get('previous_release', {}).get('build_record_sha256')
    if not isinstance(previous, str) or not re.fullmatch(r'[0-9a-f]{64}', previous):
        raise ValueError('bundle needs previous_release.build_record_sha256')
    if identity[RECORD] != previous:
        raise ValueError('base image build_record does not match bundle previous_release')
    return identity


def regular_target(root, inside):
    relative = PurePosixPath(inside)
    if not relative.is_absolute() or '..' in relative.parts:
        raise ValueError(f'invalid image path: {inside}')
    target = root
    for part in relative.parts[1:]:
        target = target / part
        if target.is_symlink():
            raise ValueError(f'symlink in image target: {target}')
    if not beneath(target.resolve(strict=True), root.resolve(strict=True)):
        raise ValueError(f'image target escapes mount: {inside}')
    if not stat.S_ISREG(target.stat().st_mode) or target.stat().st_nlink != 1:
        raise ValueError(f'image target must be an existing, non-hardlinked regular file: {inside}')
    return target


def overwrite(target, source=None, data=None):
    """Never replace the inode: retain ownership, permissions and SELinux xattrs."""
    mode = stat.S_IMODE(target.stat().st_mode)
    with target.open('r+b') as dest:
        attrs = {name: os.getxattr(dest.fileno(), name) for name in os.listxattr(dest.fileno())}
        if source is not None:
            with source.open('rb') as src:
                shutil.copyfileobj(src, dest)
        else:
            dest.write(data)
        dest.truncate()
        dest.flush()
        # Linux can clear set-id bits on write. chmod does not replace xattrs.
        os.fchmod(dest.fileno(), mode)
        # Writes can also clear security.capability; restore all original xattrs.
        for name, value in attrs.items():
            os.setxattr(dest.fileno(), name, value)
        os.fsync(dest.fileno())


def read_props(image):
    result = subprocess.run(['debugfs', '-R', 'cat /build.prop', str(image)],
                            check=True, capture_output=True)
    text = result.stdout.decode('utf-8')
    parse_identity(text)
    return text


def ext4_size(superblock, image_size):
    """Parse audited ext4 superblock fields (little-endian, offsets relative to
    the 1024-byte superblock at image offset 1024): s_blocks_count_lo (0x04),
    s_log_block_size (0x18), s_magic (0x38), s_feature_incompat (0x60),
    s_blocks_count_hi (0x150, meaningful only with INCOMPAT_64BIT = 0x80).
    See kernel Documentation/filesystems/ext4/super.rst.
    """
    if len(superblock) != 1024 or superblock[0x38:0x3a] != b'\x53\xef':
        raise ValueError('missing or invalid ext4 superblock')
    low = struct.unpack_from('<I', superblock, 0x04)[0]
    log_size = struct.unpack_from('<I', superblock, 0x18)[0]
    features = struct.unpack_from('<I', superblock, 0x60)[0]
    high = struct.unpack_from('<I', superblock, 0x150)[0]
    if log_size > 6 or (high and not features & 0x80):
        raise ValueError('invalid ext4 block geometry')
    blocks = low | (high << 32 if features & 0x80 else 0)
    size = blocks * (1024 << log_size)
    if size < 2048 or size > image_size:
        raise ValueError('ext4 filesystem size is outside clone bounds')
    return size


def clone_size(image, base):
    """Reject aliases of the base and anything other than a private regular clone."""
    if (image.is_symlink() or not stat.S_ISREG(image.stat().st_mode)
            or image.stat().st_nlink != 1 or image.samefile(base)):
        raise ValueError('filesystem resizing requires a separate, non-hardlinked regular clone')
    with image.open('rb') as stream:
        stream.seek(1024)
        return ext4_size(stream.read(1024), os.fstat(stream.fileno()).st_size)


def repair_clone(image, run):
    # e2fsck exit status is a bitmask: 1 alone means errors corrected. In
    # particular, 2 (reboot required) or 1|4 (uncorrected errors) is NOT success.
    try:
        run(['e2fsck', '-f', '-p', str(image)])
    except subprocess.CalledProcessError as error:
        if error.returncode != 1:
            raise


def grow_clone(image, base, run):
    clone_size(image, base)
    with image.open('r+b') as stream:
        stream.truncate(os.fstat(stream.fileno()).st_size + CLONE_HEADROOM)
        os.fsync(stream.fileno())
    repair_clone(image, run)
    run(['resize2fs', str(image)])


def shrink_clone(image, base, run):
    clone_size(image, base)
    repair_clone(image, run)
    run(['resize2fs', '-M', str(image)])
    # Read the updated on-disk geometry, never resize2fs's human-readable output.
    size = clone_size(image, base)
    with image.open('r+b') as stream:
        stream.truncate(size)
        os.fsync(stream.fileno())


@contextlib.contextmanager
def mounted_clone(image, parent, run):
    temp = tempfile.TemporaryDirectory(prefix='.native-test-mount-', dir=parent)
    mount = Path(temp.name)
    mounted = False
    try:
        run(['mount', '-t', 'ext4', '-o', 'loop,rw,nosuid,nodev,noexec', str(image), str(mount)])
        mounted = True
        yield mount
    finally:
        try:
            # mount(8) can fail after the kernel has attached the filesystem.
            actually_mounted = os.path.ismount(mount)
            if mounted or actually_mounted:
                run(['umount', str(mount)])
                if os.path.ismount(mount):
                    raise RuntimeError('umount returned success but the directory is still mounted')
        except BaseException as error:
            # TemporaryDirectory otherwise recursively deletes a still-mounted
            # filesystem, even during interpreter shutdown. Retain it instead.
            temp._finalizer.detach()
            raise RuntimeError(f'UNMOUNT FAILED: clone and mount retained at {mount}; '
                               'do not delete this directory until manually unmounted') from error
        temp.cleanup()


def repack(source, bundle, base, output, validate_only=False):
    source, bundle, base, output = validate_paths(source, bundle, base, output)
    gate = load_module(source / 'packaging/native/release_gate.py', 'test_image_release_gate')
    vendor = load_module(source / 'packaging/native/vendor_image.py', 'test_image_vendor')
    record = gate.verify_bundle(bundle)
    digest = vendor.sha256(bundle / gate.RECORD)
    filesystem = subprocess.run(['blkid', '-p', '-s', 'TYPE', '-o', 'value', str(base)],
                                check=True, capture_output=True, text=True).stdout.strip()
    if filesystem != 'ext4':
        raise ValueError(f'base must be raw ext4, not {filesystem!r}')
    original_props = read_props(base)
    check_base_identity(original_props, record)
    new_props = update_identity(original_props, record.get('release'), digest)
    # Validate every mapped bundle path before acquiring privileges/mounting.
    for rel in vendor.IMAGE_PREBUILTS:
        payload = bundle / rel
        if (rel not in record['files'] or payload.is_symlink()
                or not beneath(payload.resolve(strict=True), bundle) or not payload.is_file()):
            raise ValueError(f'invalid bundle prebuilt: {rel}')
    with tempfile.TemporaryDirectory(prefix='native-test-validation-', dir=output.parent) as work:
        service = vendor.image_file(base, vendor.IMAGE_PREBUILTS[SERVICE], Path(work) / 'service')
        if vendor.sha256(service) != record['files'][SERVICE]:
            raise ValueError('Codec2 service differs: this repacker must retain the published A17 service')
    print('Validated bundle, ext4 base identity and unchanged Codec2 service.', flush=True)
    if validate_only:
        return
    if os.geteuid() != 0:
        raise PermissionError('validation passed; repacking needs root only for mounting the clone')
    partial = Path(str(output) + '.partial')
    log_path = Path(str(output) + '.repack.log')
    with log_path.open('x') as log:
        def run(argv):
            log.write(f'$ {argv!r}\n')
            log.flush()
            subprocess.run(argv, check=True, stdout=log, stderr=subprocess.STDOUT)

        try:
            with partial.open('xb') as dest, base.open('rb') as src:
                shutil.copyfileobj(src, dest, 16 << 20)
            # Never mount or write the base; all mutations below address the clone.
            grow_clone(partial, base, run)
            with mounted_clone(partial, output.parent, run) as mount:
                targets = {rel: regular_target(mount, inside)
                           for rel, inside in vendor.IMAGE_PREBUILTS.items()}
                props = regular_target(mount, '/build.prop')
                if props.read_bytes() != original_props.encode():
                    raise ValueError('clone build.prop differs from validated base')
                if vendor.sha256(targets[SERVICE]) != record['files'][SERVICE]:
                    raise ValueError('clone Codec2 service differs from validated base')
                for rel, target in targets.items():
                    if vendor.sha256(target) != record['files'][rel]:
                        overwrite(target, source=bundle / rel)
                overwrite(props, data=new_props.encode())
            shrink_clone(partial, base, run)
            run(['e2fsck', '-fn', str(partial)])
            with tempfile.TemporaryDirectory(prefix='.native-test-check-', dir=output.parent) as work:
                vendor.check_prebuilts(partial, record, Path(work))
            if read_props(partial) != new_props:
                raise ValueError('repacked build.prop readback differs')
            # Atomic no-clobber publication of this LOCAL TEST artifact only.
            os.link(partial, output)
            partial.unlink()
            log.write('SUCCESS: local test repack only; no image activated; no GPU gate run.\n')
        except BaseException:
            traceback.print_exc(file=log)
            print(f'Repack failed; artifacts retained: {partial}, {log_path}', file=sys.stderr)
            raise
    print(f'LOCAL TEST ONLY: {output}\nLog: {log_path}\n'
          'Not a full vendorimage rebuild. No activation or GPU validation performed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--validate-only', action='store_true', help='read-only validation; no root required')
    for name in ('source_checkout', 'new_bundle', 'base_vendor_image', 'new_output_image'):
        parser.add_argument(name)
    args = parser.parse_args()
    repack(args.source_checkout, args.new_bundle, args.base_vendor_image,
           args.new_output_image, args.validate_only)


if __name__ == '__main__':
    os.environ['LC_ALL'] = 'C'
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f'repack-nvidia-test-image: {error}')
