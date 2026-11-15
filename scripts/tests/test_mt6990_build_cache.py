#!/usr/bin/env python3
"""Check opt-in build caching and exercise the real staged compiler cache."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/mt6990-build-and-record.sh'
WORKFLOW = ROOT / '.github/workflows/lg6851f-cloud-build.yml'


class CacheConfigTest(unittest.TestCase):
    def option(self, mode, sloppy=''):
        text = SCRIPT.read_text()
        function = text[text.index('lg6851f_cache_option() {'):text.index('\nlg6851f_cache_option\n')]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'Makefile').write_text('CONFIG_CCACHE:=disabled\nall:\n\t@echo value=$(CONFIG_CCACHE)\n')
            env = dict(os.environ, LG6851F_CCACHE=mode, CCACHE_SLOPPINESS=sloppy)
            return subprocess.run(['sh', '-ec', function + '\nlg6851f_cache_option\n'
                'make -s ${cache_option:+"$cache_option"}\n'
                'printf "check=%s max=%s\\n" "${CCACHE_COMPILERCHECK:-}" "${CCACHE_MAXSIZE:-}"'],
                cwd=root, env=env, text=True, capture_output=True)

    def test_opt_in_overrides_make_without_changing_firmware_configuration(self):
        result = self.option('1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('value=y', result.stdout)
        self.assertIn('check=content max=2G', result.stdout)
        result = self.option('0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('value=disabled', result.stdout)

    def test_invalid_or_relaxed_cache_settings_fail(self):
        for mode, sloppy in [('yes', ''), ('1', 'time_macros'), ('1', 'file_stat_matches')]:
            with self.subTest(mode=mode, sloppy=sloppy):
                result = self.option(mode, sloppy)
                self.assertEqual(result.returncode, 22, result.stderr)
                self.assertNotIn('value=', result.stdout)

    def test_all_build_phases_keep_the_same_option_and_real_cache_check(self):
        lines = [line for line in SCRIPT.read_text().splitlines() if line.lstrip().startswith('make -C ')]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertIn('${cache_option:+"$cache_option"}', line)
        self.assertIn('staging_dir/host/bin/ccache" python3', SCRIPT.read_text())
        self.assertIn('NativeCacheTest', SCRIPT.read_text())
        self.assertIn('set -- -j4 V=s', SCRIPT.read_text())

    def test_cache_only_downloads_and_compiler_objects_with_fresh_snapshot_keys(self):
        text = WORKFLOW.read_text()
        blocks = text.split('      - name: ')
        caches = [block for block in blocks if 'uses: actions/cache' in block]
        self.assertEqual(len(caches), 3)
        paths = [next(line.strip() for line in block.splitlines() if line.strip().startswith('path:')) for block in caches]
        self.assertEqual(paths, ['path: dl', 'path: .ccache', 'path: .ccache'])
        for block in caches[:2]:
            self.assertIn('${{ github.run_id }}-${{ github.run_attempt }}', block)
        self.assertIn('${{ steps.ccache.outputs.cache-primary-key }}', caches[2])
        self.assertIn("steps.build.outcome == 'failure'", caches[2])
        self.assertIn("LG6851F_CCACHE: '1'", text)
        self.assertIn('CCACHE_DIR="$GITHUB_WORKSPACE/.ccache" staging_dir/host/bin/ccache --show-stats', text)
        self.assertIn('python3 scripts/tests/test_mt6990_build_cache.py CacheConfigTest', text)
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('schedule:', text)
        self.assertIn('./scripts/mt6990-build-apk-repository.sh', text)
        self.assertIn('python3 scripts/lg6851f-check-cpe-package.py', text)


class NativeCacheTest(unittest.TestCase):
    def test_real_cache_hits_and_header_or_flag_changes_invalidate(self):
        cache = os.environ.get('CCACHE')
        self.assertTrue(cache and Path(cache).is_file(), 'CCACHE must name the real staged executable')
        compiler = shutil.which('cc')
        self.assertTrue(compiler, 'native C compiler is required')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = {key: value for key, value in os.environ.items() if not key.startswith('CCACHE_')}
            env.update(CCACHE_DIR=str(root/'cache'), CCACHE_CONFIGPATH=str(root/'ccache.conf'),
                       CCACHE_COMPILERCHECK='content', CCACHE_MAXSIZE='16M')
            (root/'ccache.conf').write_text('')
            (root/'value.h').write_text('#define VALUE 17\n')
            (root/'main.c').write_text('#include "value.h"\n#ifndef EXTRA\n#define EXTRA 0\n#endif\nint main(void) { return VALUE + EXTRA; }\n')

            def run(*args):
                return subprocess.run(args, cwd=root, env=env, text=True, capture_output=True, check=True)

            def stats():
                return {key: int(value) for key, value in (line.split() for line in run(cache, '--print-stats').stdout.splitlines())}

            def compile_value(*flags):
                (root/'main.o').unlink(missing_ok=True)
                run(cache, compiler, *flags, '-c', 'main.c', '-o', 'main.o')
                run(compiler, 'main.o', '-o', str(root/'example'))
                return subprocess.run([str(root/'example')], env=env).returncode

            run(cache, '--zero-stats')
            self.assertEqual(compile_value(), 17)
            first = stats()
            self.assertEqual(compile_value(), 17)
            second = stats()
            self.assertGreater(second['direct_cache_hit'] + second['preprocessed_cache_hit'],
                               first['direct_cache_hit'] + first['preprocessed_cache_hit'])
            # Different flags and an included header must never reuse the old result.
            self.assertEqual(compile_value('-DEXTRA=2'), 19)
            (root/'value.h').write_text('#define VALUE 23\n')
            self.assertEqual(compile_value('-DEXTRA=2'), 25)
            self.assertGreaterEqual(stats()['cache_miss'] - second['cache_miss'], 2)


if __name__ == '__main__':
    unittest.main()
