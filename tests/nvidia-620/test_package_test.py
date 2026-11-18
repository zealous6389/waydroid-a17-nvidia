"""Pure helper tests; no image builds, downloads, makepkg or installation."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    'package_test', Path(__file__).resolve().parents[2] / 'scripts/package-nvidia-test.py')
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class PackageTest(unittest.TestCase):
    def metadata(self):
        return helper.parse_metadata(
            f'pkgname = {helper.PKGNAME}\npkgver = {helper.BASE_VERSION}\narch = x86_64\n'
            'license = MIT\ndepend = python>=3\nprovides = waydroid\nconflict = waydroid\n'
            'optdepend = foo: helpful tool\n')

    def test_metadata_and_recipe(self):
        metadata = self.metadata()
        text = helper.render_pkgbuild(metadata, {'baseline.pkg.tar.zst': 'a' * 64},
                                     helper.VENDOR + '/old.zip', helper.VENDOR + '/old.json')
        self.assertIn("depends=('python>=3')", text)
        self.assertIn("optdepends=('foo: helpful tool')", text)
        self.assertIn("provides=(waydroid)", text)
        self.assertIn("conflicts=(waydroid)", text)
        self.assertIn('pkgver=20261117.1', text)
        self.assertIn('install=local.install', text)
        self.assertIn('--exclude=.INSTALL', text)
        self.assertIn('noextract=', text)
        self.assertNotIn('https://', text)

    def test_baseline_identity_required(self):
        for text in ('', 'pkgname = wrong\n', 'pkgname = waydroid-a17-nvidia-bin\npkgver = 1\n'):
            with self.assertRaises(ValueError):
                helper.parse_metadata(text)

    def test_output_overlap_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            link = root / 'link'
            link.symlink_to(source, target_is_directory=True)
            for output in (source, source / 'child', link / 'child', root):
                with self.assertRaises(ValueError):
                    helper.output_path([source], output)
            self.assertEqual(helper.output_path([source], root / 'new'), root / 'new')

    def test_archive_paths_and_vendor_files(self):
        for name in ('../bad', '/bad', './a/../../bad', 'a\na'):
            with self.assertRaises(ValueError):
                helper.archive_names(name)
        names = helper.archive_names(f'./{helper.VENDOR}/\n{helper.VENDOR}/v.zip\n{helper.VENDOR}/v.json\n')
        self.assertEqual(helper.vendor_names(names), (helper.VENDOR + '/v.zip', helper.VENDOR + '/v.json'))
        with self.assertRaises(ValueError):
            helper.vendor_names(names + [helper.VENDOR + '/extra.zip'])
        with self.assertRaises(ValueError):
            helper.vendor_names([helper.VENDOR + '/$(bad).zip', helper.VENDOR + '/v.json'])

    def test_records(self):
        old = {'release': 'old', 'files': {helper.SERVICE: 'same', 'gate/a': 'a'}}
        new = {'files': {helper.SERVICE: 'same', 'gate/a': 'new'},
               'previous_release': {'release': 'old', 'build_record_sha256': 'hash'}}
        helper.check_records(old, new, 'hash')
        for changed in (
                {**new, 'previous_release': {}},
                {**new, 'files': {**new['files'], 'extra': 'x'}},
                {**new, 'files': {**new['files'], helper.SERVICE: 'changed'}}):
            with self.assertRaises(ValueError):
                helper.check_records(old, changed, 'hash')

    def test_channel_installed_file_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'vendor.zip'
            path.write_bytes(b'zip')
            entry = helper.channel_entry(path, 'baseline-name.zip',
                                         {'ro.vendor.build.date.utc': '123'})['response'][0]
            self.assertEqual(entry['id'], hashlib.sha256(b'zip').hexdigest())
            self.assertEqual(entry['size'], 3)
            self.assertEqual(entry['datetime'], 123)
            self.assertEqual(entry['url'], 'file:///usr/lib/waydroid-nvidia/vendor/baseline-name.zip')

    def test_refuse_root_before_work(self):
        with patch.object(helper.os, 'geteuid', return_value=0):
            with self.assertRaisesRegex(ValueError, 'non-root'):
                helper.generate(*(Path('/unused') for _ in range(5)))

    def test_bad_image_identity_creates_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            bundle = root / 'bundle'
            source.mkdir()
            bundle.mkdir()
            base = root / 'base'
            image = root / 'image'
            base.touch()
            image.touch()
            record = {'release': 'old', 'files': {helper.SERVICE: 'unchanged'}}
            old_bytes = helper.json.dumps(record).encode()
            new = {'files': record['files'], 'previous_release': {
                'release': 'old', 'build_record_sha256': hashlib.sha256(old_bytes).hexdigest()}}
            (bundle / 'BUILD-RECORD.json').write_text('{}')
            metadata = (f'pkgname = {helper.PKGNAME}\npkgver = {helper.BASE_VERSION}\n'
                        'arch = x86_64\n').encode()
            listing = (f'{helper.NATIVE}/BUILD-RECORD.json\n{helper.VENDOR}/v.zip\n'
                       f'{helper.VENDOR}/v.json\n')
            native = SimpleNamespace(
                image_build_props=lambda _: {}, BUILD_RECORD_PROP='record', VERSION_PROP='version')
            with patch.object(helper.os, 'geteuid', return_value=1000), \
                    patch.object(helper, 'load', side_effect=[
                        SimpleNamespace(verify_bundle=lambda _: new), SimpleNamespace(), native]), \
                    patch.object(helper.subprocess, 'check_output', return_value=listing), \
                    patch.object(helper, 'member', side_effect=[metadata, old_bytes]):
                with self.assertRaisesRegex(ValueError, 'identity differs'):
                    helper.generate(source, base, bundle, image, root / 'output')
            self.assertFalse((root / 'output').exists())


if __name__ == '__main__':
    unittest.main()
