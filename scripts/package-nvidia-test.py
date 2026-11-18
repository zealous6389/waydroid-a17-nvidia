#!/usr/bin/env python3
"""Generate an offline local-test PKGBUILD, without installing or changing the host.

Usage: package-nvidia-test.py SOURCE_CHECKOUT BASE_PACKAGE NEW_BUNDLE NEW_VENDOR_IMAGE NEW_OUTPUT_DIR

Experimental native-only image repack, NOT a full Android 17 Soong build.
After inspecting the generated files, run `makepkg --nodeps` in NEW_OUTPUT_DIR.
Never install, publish, download, or invoke privileged operations here.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tempfile
import zipfile


PKGNAME = 'waydroid-a17-nvidia-bin'
BASE_VERSION = '20261111.1-1'
VERSION = '20261117.1'
NATIVE = 'usr/lib/waydroid-nvidia/native/release'
VENDOR = 'usr/lib/waydroid-nvidia/vendor'
CONTROL = ('.PKGINFO', '.BUILDINFO', '.MTREE', '.INSTALL')
SERVICE = 'payload/odm/bin/hw/android.hardware.media.c2@1.2-service-nvprolapse'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def output_path(inputs, output):
    """Resolve symlinked parents too; never let an output contain/modify an input."""
    if output.exists() or output.is_symlink():
        raise ValueError('output must not exist')
    resolved = output.resolve()
    for path in inputs:
        path = path.resolve(strict=True)
        if resolved == path or resolved in path.parents or path in resolved.parents:
            raise ValueError(f'output overlaps input: {path}')
    return resolved


def parse_metadata(text):
    result = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition(' = ')
        if not sep:
            raise ValueError(f'invalid .PKGINFO line: {line!r}')
        result.setdefault(key, []).append(value)
    for key, expected in (('pkgname', PKGNAME), ('pkgver', BASE_VERSION), ('arch', 'x86_64')):
        if result.get(key) != [expected]:
            raise ValueError(f'baseline {key} must be {expected!r}')
    return result


def archive_names(text):
    names = []
    for name in text.splitlines():
        name = name.removeprefix('./').rstrip('/')
        if name in ('', '.'):
            continue
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\n' in name:
            raise ValueError(f'unsafe archive path: {name!r}')
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError('duplicate archive paths')
    return names


def vendor_names(names):
    children = [n for n in names if n.startswith(VENDOR + '/')]
    zips = [n for n in children if n.endswith('.zip')]
    channels = [n for n in children if n.endswith('.json')]
    if len(zips) != 1 or len(channels) != 1 or len(children) != 2:
        raise ValueError('baseline vendor directory must contain exactly one ZIP and one channel JSON')
    if any(not re.fullmatch(r'[A-Za-z0-9_.+-]+', n[len(VENDOR) + 1:]) for n in children):
        raise ValueError('unsafe baseline vendor filename')
    return zips[0], channels[0]


def check_records(old, new, old_sha):
    if set(old['files']) != set(new['files']):
        raise ValueError('native file set differs from the baseline (stale inherited files are unsafe)')
    if new.get('previous_release') != {
            'release': old['release'], 'build_record_sha256': old_sha}:
        raise ValueError('new bundle must record the baseline as previous_release')
    if new['files'].get(SERVICE) != old['files'].get(SERVICE) or SERVICE not in new['files']:
        raise ValueError('native-only test must keep the baseline Codec2 service')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def channel_entry(zip_path, installed_name, props):
    stamp = int(props['ro.vendor.build.date.utc'])
    if stamp <= 0:
        raise ValueError('invalid vendor image timestamp')
    return {'response': [{
        'datetime': stamp, 'filename': installed_name,
        'id': sha256(zip_path), 'size': zip_path.stat().st_size,
        'romtype': 'MAINLINE', 'version': '20.0',
        'url': Path('/', VENDOR, installed_name).as_uri(),
    }]}


def render_pkgbuild(metadata, sums, installed_zip, installed_channel):
    q = shlex.quote
    lines = [
        '# LOCAL EXPERIMENT ONLY: native-only ext4 repack; NOT a full A17 Soong build.',
        '# Offline inputs; inherits baseline host integration and uninstall hooks.',
        f'pkgname={PKGNAME}', f'pkgver={VERSION}', 'pkgrel=1',
        "pkgdesc='EXPERIMENTAL LOCAL NVIDIA 620 native-only repack (not a full Soong build)'",
        "arch=('x86_64')",
    ]
    for source, target in (
            ('url', 'url'), ('license', 'license'), ('depend', 'depends'),
            ('makedepend', 'makedepends'), ('checkdepend', 'checkdepends'),
            ('optdepend', 'optdepends'), ('provides', 'provides'),
            ('conflict', 'conflicts'), ('backup', 'backup'), ('replaces', 'replaces')):
        values = metadata.get(source, [])
        if source == 'url':
            if values:
                lines.append(f'url={q(values[0])}')
        else:
            lines.append(f'{target}=({" ".join(q(v) for v in values)})')
    lines += [
        "options=('!strip' '!debug' '!lto')",
        'install=local.install',
        'source=(' + ' '.join(q(n) for n in sums) + ')',
        'sha256sums=(' + ' '.join(q(s) for s in sums.values()) + ')',
        "noextract=('baseline.pkg.tar.zst' 'native.tar.zst' 'vendor.zip')",
        '',
        'package() {',
        '  bsdtar -xf "$srcdir/baseline.pkg.tar.zst" -C "$pkgdir" \\',
        '    --exclude=.PKGINFO --exclude=.BUILDINFO --exclude=.MTREE --exclude=.INSTALL',
        f'  bsdtar -xf "$srcdir/native.tar.zst" -C "$pkgdir/{NATIVE}"',
        f'  install -m644 "$srcdir/vendor.zip" "$pkgdir/{installed_zip}"',
        f'  install -m644 "$srcdir/channel.json" "$pkgdir/{installed_channel}"',
        '}',
        '',
    ]
    return '\n'.join(lines)


def member(package, name):
    return subprocess.check_output(['bsdtar', '-xOf', str(package), name])


def generate(source, base, bundle, image, output):
    if os.geteuid() == 0:
        raise ValueError('run as a non-root user')
    output = output_path((source, base, bundle, image), output)
    source, base, bundle, image = (p.resolve(strict=True) for p in (source, base, bundle, image))
    gate = load(source / 'packaging/native/release_gate.py', 'local_test_release_gate')
    vi = load(source / 'packaging/native/vendor_image.py', 'local_test_vendor_image')
    native = load(source / 'waydroid/nvidia_native.py', 'local_test_nvidia_native')
    record = gate.verify_bundle(bundle)
    names = archive_names(subprocess.check_output(['bsdtar', '-tf', str(base)], text=True))
    zip_name, channel_name = vendor_names(names)
    metadata = parse_metadata(member(base, '.PKGINFO').decode())
    old_bytes = member(base, NATIVE + '/BUILD-RECORD.json')
    old = json.loads(old_bytes)
    check_records(old, record, hashlib.sha256(old_bytes).hexdigest())
    # Require the complete staged release tree to match too, not just record['files'].
    actual = {str(p.relative_to(bundle)) for p in bundle.rglob('*') if not p.is_dir()}
    expected = {n[len(NATIVE) + 1:] for n in names if n.startswith(NATIVE + '/')
                and not any(m.startswith(n + '/') for m in names)}
    if actual != expected or any(p.is_symlink() for p in bundle.rglob('*')):
        raise ValueError('new native release tree differs from baseline or contains symlinks')
    props = native.image_build_props(str(image))
    if props.get(native.BUILD_RECORD_PROP) != sha256(bundle / 'BUILD-RECORD.json'):
        raise ValueError('vendor image BUILD-RECORD identity differs from new bundle')
    if props.get(native.VERSION_PROP) != record.get('release') or not props.get('ro.vendor.build.fingerprint'):
        raise ValueError('vendor image NVIDIA version/fingerprint identity differs from the bundle')
    with tempfile.TemporaryDirectory(prefix='package-check-', dir='/tmp/opencode') as work:
        vi.check_prebuilts(image, record, Path(work))
    # Fail all validation before reserving a new output. Partial output is retained on I/O errors.
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(base, output / 'baseline.pkg.tar.zst')
    (output / 'local.install').write_bytes(member(base, '.INSTALL'))
    subprocess.run(['tar', '--zstd', '-cf', str(output / 'native.tar.zst'),
                    '-C', str(bundle), '.'], check=True)
    info = zipfile.ZipInfo('vendor.img', date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    with zipfile.ZipFile(output / 'vendor.zip', 'w', allowZip64=True) as archive:
        with image.open('rb') as src, archive.open(info, 'w', force_zip64=True) as dst:
            shutil.copyfileobj(src, dst, 16 << 20)
    channel = channel_entry(output / 'vendor.zip', Path(zip_name).name, props)
    (output / 'channel.json').write_text(json.dumps(channel, indent=2) + '\n')
    sums = {n: sha256(output / n) for n in (
        'baseline.pkg.tar.zst', 'native.tar.zst', 'vendor.zip', 'channel.json', 'local.install')}
    (output / 'PKGBUILD').write_text(render_pkgbuild(metadata, sums, zip_name, channel_name))
    (output / 'LOCAL-TEST.txt').write_text(
        'EXPERIMENTAL LOCAL TEST ONLY: native-only ext4 image repack, NOT a full Android 17 Soong build.\n'
        'Baseline host files, integration and uninstall hooks are inherited unchanged.\n'
        'Only native/release and the existing vendor ZIP/channel are replaced.\n'
        'No installation, GPU/runtime validation or publication has been performed.\n'
        f'Baseline: {base}\nBaseline SHA256: {sums["baseline.pkg.tar.zst"]}\n'
        f'Bundle: {bundle}\nImage: {image}\nImage SHA256: {sha256(image)}\n'
        'Inspect PKGBUILD, then run: makepkg --nodeps\n'
        '--nodeps skips dependency checking only; it does not install dependencies or the package.\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('source_checkout', 'base_package', 'new_bundle', 'new_vendor_image', 'new_output_dir'):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    try:
        out = generate(args.source_checkout, args.base_package, args.new_bundle,
                       args.new_vendor_image, args.new_output_dir)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'package-nvidia-test: {error}\n')
    print(f'Generated offline local test package recipe: {out}\n'
          f'Next: cd {shlex.quote(str(out))} && makepkg --nodeps\n'
          'EXPERIMENTAL native-only repack; NOT a full Soong build. Nothing installed.')


if __name__ == '__main__':
    main()
