"""Unprivileged repacker safety tests. No real mount or host changes."""
import importlib.util
from pathlib import Path
import subprocess
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/repack-nvidia-test-image.py'
SPEC = importlib.util.spec_from_file_location('repack_image', SCRIPT)
repack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repack)
OLD = 'a' * 64
NEW = 'b' * 64
PROPS = (f'{repack.VERSION}=baseline\n{repack.RECORD}={OLD}\n'
         'ro.vendor.build.date.utc=12345\n# retained\n')


def superblock(blocks=16, log_size=0, high=0, features=0):
    data = bytearray(1024)
    data[0x38:0x3a] = b'\x53\xef'
    for offset, value in ((0x04, blocks), (0x18, log_size),
                          (0x60, features), (0x150, high)):
        struct.pack_into('<I', data, offset, value)
    return data


class ResizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'base.img'
        data = bytearray(16 * 1024)
        data[1024:2048] = superblock()
        self.base.write_bytes(data)
        self.clone = self.root / 'clone.img.partial'
        self.clone.write_bytes(data)
        self.original = bytes(data)

    def test_geometry_and_64bit_blocks(self):
        self.assertEqual(repack.ext4_size(superblock(), 16384), 16384)
        self.assertEqual(repack.ext4_size(superblock(4, 2), 16384), 16384)
        size = ((1 << 32) + 16) * 4096
        self.assertEqual(repack.ext4_size(superblock(16, 2, 1, 0x80), size), size)

    def test_geometry_rejects_missing_fields_and_invalid_bounds(self):
        cases = [(b'', 16384), (superblock()[:0x100], 16384),
                 (bytes(1024), 16384), (superblock(0), 16384),
                 (superblock(1), 16384), (superblock(17), 16384),
                 (superblock(log_size=7), 1 << 40),
                 (superblock(high=1), 1 << 60),
                 (superblock(high=1, features=0x80), 16384)]
        for data, size in cases:
            with self.subTest(data_length=len(data), size=size), self.assertRaises(ValueError):
                repack.ext4_size(data, size)

    def test_fsck_accepts_only_zero_or_one(self):
        repack.repair_clone(self.clone, Mock())
        repack.repair_clone(self.clone, Mock(
            side_effect=subprocess.CalledProcessError(1, ['e2fsck'])))
        for code in (-9, 2, 3, 4, 5, 8, 16, 32, 128):
            with self.subTest(code=code), self.assertRaises(subprocess.CalledProcessError):
                repack.repair_clone(self.clone, Mock(
                    side_effect=subprocess.CalledProcessError(code, ['e2fsck'])))

    def test_growth_changes_only_clone_and_checks_before_resize(self):
        def run(argv):
            self.assertEqual(self.clone.stat().st_size, len(self.original) + repack.CLONE_HEADROOM)
            self.assertEqual(self.base.read_bytes(), self.original)

        runner = Mock(side_effect=run)
        repack.grow_clone(self.clone, self.base, runner)
        self.assertEqual(runner.call_args_list[0].args[0],
                         ['e2fsck', '-f', '-p', str(self.clone)])
        self.assertEqual(runner.call_args_list[1].args[0], ['resize2fs', str(self.clone)])
        with self.clone.open('rb') as stream:
            self.assertEqual(stream.read(len(self.original)), self.original)

    def test_growth_fsck_failure_retains_expanded_clone(self):
        runner = Mock(side_effect=subprocess.CalledProcessError(4, ['e2fsck']))
        with self.assertRaises(subprocess.CalledProcessError):
            repack.grow_clone(self.clone, self.base, runner)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(self.clone.stat().st_size, len(self.original) + repack.CLONE_HEADROOM)
        self.assertEqual(self.base.read_bytes(), self.original)

    def test_shrink_truncates_only_clone_to_updated_geometry(self):
        def run(argv):
            if argv[0] == 'resize2fs':
                # Simulate resize2fs shrinking the filesystem but not its file.
                with self.clone.open('r+b') as stream:
                    stream.seek(1024)
                    stream.write(superblock(blocks=4))

        runner = Mock(side_effect=run)
        repack.shrink_clone(self.clone, self.base, runner)
        self.assertEqual(runner.call_args_list[0].args[0],
                         ['e2fsck', '-f', '-p', str(self.clone)])
        self.assertEqual(runner.call_args_list[1].args[0], ['resize2fs', '-M', str(self.clone)])
        self.assertEqual(self.clone.stat().st_size, 4096)
        self.assertEqual(self.base.read_bytes(), self.original)

    def test_bad_post_shrink_geometry_never_truncates(self):
        def run(argv):
            if argv[0] == 'resize2fs':
                with self.clone.open('r+b') as stream:
                    stream.seek(1024)
                    stream.write(superblock(blocks=17))

        with self.assertRaisesRegex(ValueError, 'bounds'):
            repack.shrink_clone(self.clone, self.base, run)
        self.assertEqual(self.clone.stat().st_size, len(self.original))
        self.assertEqual(self.base.read_bytes(), self.original)

    def test_resize_refuses_base_symlink_and_hardlink_aliases(self):
        symlink = self.root / 'symlink'
        symlink.symlink_to(self.base)
        hardlink = self.root / 'hardlink'
        hardlink.hardlink_to(self.base)
        for helper in (repack.grow_clone, repack.shrink_clone):
            for image in (self.base, symlink, hardlink):
                runner = Mock()
                with self.subTest(helper=helper.__name__, image=image), self.assertRaises(ValueError):
                    helper(image, self.base, runner)
                runner.assert_not_called()
        self.assertEqual(self.base.read_bytes(), self.original)


class IdentityTests(unittest.TestCase):
    def test_only_identity_changed(self):
        got = repack.update_identity(PROPS, 'local-native-test', NEW)
        self.assertEqual(got, PROPS.replace('=baseline', '=local-native-test').replace(OLD, NEW))

    def test_missing_and_duplicate_properties(self):
        for text in ('', PROPS.replace(f'{repack.RECORD}={OLD}\n', ''),
                     PROPS + f'{repack.VERSION}=again\n',
                     PROPS + f'{repack.RECORD}={OLD}\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                repack.update_identity(text, 'test', NEW)

    def test_mismatched_or_missing_base(self):
        for record in ({}, {'previous_release': {'build_record_sha256': NEW}}):
            with self.assertRaises(ValueError):
                repack.check_base_identity(PROPS, record)
        self.assertEqual(repack.check_base_identity(
            PROPS, {'previous_release': {'build_record_sha256': OLD}})[repack.RECORD], OLD)


class PathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.bundle = self.root / 'bundle'
        self.source.mkdir()
        self.bundle.mkdir()
        self.base = self.root / 'base.img'
        self.base.write_bytes(b'base')
        self.output = self.root / 'test.img'

    def validate(self, output):
        return repack.validate_paths(self.source, self.bundle, self.base, output)

    def test_safe_output(self):
        self.assertEqual(self.validate(self.output)[3], self.output)

    def test_existing_symlink_overlap_and_system_outputs(self):
        dangling = self.root / 'dangling'
        dangling.symlink_to(self.root / 'absent')
        for output in (self.base, dangling, self.source / 'out.img',
                       self.bundle / 'out.img', Path('/etc/test-native-image.img')):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.validate(output)

    def test_symlinked_parent_and_partial_are_rejected(self):
        link = self.root / 'system'
        link.symlink_to('/etc', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.validate(link / 'native-test.img')
        Path(str(self.output) + '.partial').write_bytes(b'failed')
        with self.assertRaises(ValueError):
            self.validate(self.output)

    def test_targets_reject_symlinks_traversal_and_hardlinks(self):
        target = self.root / 'regular'
        target.write_bytes(b'old')
        self.assertEqual(repack.regular_target(self.root, '/regular'), target)
        (self.root / 'escape').symlink_to('/etc')
        (self.root / 'alias').symlink_to(target)
        for path in ('/escape/passwd', '/alias', '/../outside', 'regular', '/missing'):
            with self.subTest(path=path), self.assertRaises((ValueError, FileNotFoundError)):
                repack.regular_target(self.root, path)
        (self.root / 'hardlink').hardlink_to(target)
        with self.assertRaises(ValueError):
            repack.regular_target(self.root, '/regular')

    def test_overwrite_retains_inode_mode_and_xattrs(self):
        target = self.root / 'regular'
        target.write_bytes(b'long original')
        target.chmod(0o640)
        before = target.stat()
        import os
        try:
            os.setxattr(target, 'user.repack-test', b'preserve')
        except OSError:
            pass
        repack.overwrite(target, data=b'new')
        self.assertEqual(target.read_bytes(), b'new')
        self.assertEqual(target.stat().st_ino, before.st_ino)
        self.assertEqual(target.stat().st_mode, before.st_mode)
        if 'user.repack-test' in os.listxattr(target):
            self.assertEqual(os.getxattr(target, 'user.repack-test'), b'preserve')

    def test_unmount_on_body_failure(self):
        run = Mock()
        with self.assertRaisesRegex(ValueError, 'body'):
            with repack.mounted_clone(self.output, self.root, run):
                raise ValueError('body')
        self.assertEqual(run.call_args_list[-1].args[0][0], 'umount')
        self.assertFalse(list(self.root.glob('.native-test-mount-*')))

    def test_mount_failure_cleans_empty_directory(self):
        run = Mock(side_effect=subprocess.CalledProcessError(1, ['mount']))
        with self.assertRaises(subprocess.CalledProcessError):
            with repack.mounted_clone(self.output, self.root, run):
                self.fail('mount failed but body ran')
        self.assertEqual(run.call_count, 1)
        self.assertFalse(list(self.root.glob('.native-test-mount-*')))

    def test_unmount_failure_retains_directory_without_cleanup(self):
        run = Mock(side_effect=[None, subprocess.CalledProcessError(1, ['umount'])])
        with patch.object(repack.tempfile.TemporaryDirectory, 'cleanup') as cleanup:
            with self.assertRaisesRegex(RuntimeError, 'UNMOUNT FAILED'):
                with repack.mounted_clone(self.output, self.root, run):
                    pass
            cleanup.assert_not_called()
        self.assertEqual(len(list(self.root.glob('.native-test-mount-*'))), 1)

    def test_mount_nonzero_after_kernel_mount_still_unmounts(self):
        error = subprocess.CalledProcessError(1, ['mount'])
        run = Mock(side_effect=[error, None])
        with patch.object(repack.os.path, 'ismount', side_effect=[True, False]) as ismount:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                with repack.mounted_clone(self.output, self.root, run):
                    self.fail('mount failed but body ran')
        self.assertIs(caught.exception, error)
        self.assertEqual(run.call_args_list[-1].args[0][0], 'umount')
        self.assertEqual(ismount.call_count, 2)
        self.assertFalse(list(self.root.glob('.native-test-mount-*')))

    def test_umount_success_but_still_mounted_retains_directory(self):
        run = Mock()
        with patch.object(repack.os.path, 'ismount', return_value=True) as ismount, \
                patch.object(repack.tempfile.TemporaryDirectory, 'cleanup') as cleanup:
            with self.assertRaisesRegex(RuntimeError, 'UNMOUNT FAILED') as caught:
                with repack.mounted_clone(self.output, self.root, run):
                    pass
            cleanup.assert_not_called()
        self.assertIn('still mounted', str(caught.exception.__cause__))
        self.assertEqual(run.call_args_list[-1].args[0][0], 'umount')
        self.assertEqual(ismount.call_count, 2)
        self.assertEqual(len(list(self.root.glob('.native-test-mount-*'))), 1)

    def test_mount_inspection_failure_retains_directory(self):
        run = Mock()
        with patch.object(repack.os.path, 'ismount', side_effect=OSError('inspection failed')), \
                patch.object(repack.tempfile.TemporaryDirectory, 'cleanup') as cleanup:
            with self.assertRaisesRegex(RuntimeError, 'UNMOUNT FAILED'):
                with repack.mounted_clone(self.output, self.root, run):
                    pass
            cleanup.assert_not_called()
        self.assertEqual(len(list(self.root.glob('.native-test-mount-*'))), 1)

    def setup_validation(self):
        (self.bundle / 'BUILD-RECORD.json').write_text('{}')
        payload = self.bundle / repack.SERVICE
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b'codec')
        record = {'release': 'test', 'previous_release': {'build_record_sha256': OLD},
                  'files': {repack.SERVICE: 'codec-hash'}}
        gate = SimpleNamespace(RECORD='BUILD-RECORD.json', verify_bundle=Mock(return_value=record))

        def image_file(image, inside, destination):
            self.assertEqual(destination.parent.parent, self.output.parent)
            destination.write_bytes(b'codec')
            return destination

        vendor = SimpleNamespace(IMAGE_PREBUILTS={repack.SERVICE: '/service'},
                                 image_file=Mock(side_effect=image_file),
                                 sha256=lambda path: NEW if path.name == 'BUILD-RECORD.json' else 'codec-hash')
        return gate, vendor

    def test_validate_only_never_checks_root_or_mounts(self):
        modules = self.setup_validation()
        with patch.object(repack, 'load_module', side_effect=modules), \
                patch.object(repack, 'read_props', return_value=PROPS), \
                patch.object(repack.subprocess, 'run',
                             return_value=SimpleNamespace(stdout='ext4\n')) as run, \
                patch.object(repack.os, 'geteuid') as uid, \
                patch.object(repack, 'mounted_clone') as mount:
            repack.repack(self.source, self.bundle, self.base, self.output, validate_only=True)
        uid.assert_not_called()
        mount.assert_not_called()
        self.assertEqual(run.call_count, 1)
        self.assertFalse(self.output.exists())
        self.assertFalse(Path(str(self.output) + '.partial').exists())

    def test_non_ext4_rejected_before_root_or_clone(self):
        modules = self.setup_validation()
        with patch.object(repack, 'load_module', side_effect=modules), \
                patch.object(repack.subprocess, 'run',
                             return_value=SimpleNamespace(stdout='squashfs\n')), \
                patch.object(repack.os, 'geteuid') as uid:
            with self.assertRaisesRegex(ValueError, 'raw ext4'):
                repack.repack(self.source, self.bundle, self.base, self.output)
        uid.assert_not_called()
        self.assertFalse(Path(str(self.output) + '.partial').exists())


if __name__ == '__main__':
    unittest.main()
