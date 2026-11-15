#!/usr/bin/env python3
"""Execute the real notes selection shell with isolated API responses."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = Path(os.environ.get('RELEASE_NOTES_WORKFLOW', ROOT / '.github/workflows/publish-release.yml'))
SHA = '1' * 40


class ReleaseNotesTest(unittest.TestCase):
    def select(self, override, source):
        workflow = WORKFLOW.read_text()
        start = workflow.index('          # Prefer a reviewed per-build summary')
        end = workflow.index('          {\n', start)
        shell = '\n'.join(line[10:] for line in workflow[start:end].splitlines())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'responses.json').write_text(json.dumps({'override': override, 'source': source}))
            gh = root / 'gh'
            gh.write_text('''#!/usr/bin/env python3
import base64,json,os,pathlib,sys
r=pathlib.Path(os.environ['FIXTURE']);url=sys.argv[2]
with (r/'requests').open('a') as f:f.write(url+'\\n')
assert sys.argv[1]=='api'
sha=os.environ['source_sha']
if url=='repos/adian2020/openwrt-mt6990-lg6851f/contents/docs/releases/'+sha+'.md?ref=cloud-build':key='override'
elif url=='repos/adian2020/openwrt-mt6990-lg6851f/contents/RELEASE_NOTES.md?ref='+sha:key='source'
else:raise AssertionError(url)
text=json.loads((r/'responses.json').read_text())[key]
if text is None:sys.exit(1)
print(json.dumps({'content':base64.b64encode(text.encode()).decode()}))
''')
            gh.chmod(0o755)
            env = dict(os.environ, PATH=str(root)+':'+os.environ['PATH'], FIXTURE=str(root),
                       source_sha=SHA, GITHUB_REPOSITORY='adian2020/openwrt-mt6990-lg6851f')
            result = subprocess.run(['bash', '-eu', '-o', 'pipefail', '-c', shell], cwd=root,
                                    env=env, capture_output=True, text=True)
            notes = root / 'RELEASE_NOTES.md'
            return result, notes.read_text() if notes.exists() else None, (root/'requests').read_text()

    def test_exact_build_summary_wins_over_cumulative_source_notes(self):
        result, notes, requests = self.select('本版本新增、修改、删除\n', '历史累计说明\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(notes, '本版本新增、修改、删除\n')
        self.assertEqual(len(requests.splitlines()), 1)
        self.assertIn(SHA+'.md?ref=cloud-build', requests)

    def test_missing_override_uses_exact_source_commit(self):
        result, notes, requests = self.select(None, '源码版本说明\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(notes, '源码版本说明\n')
        self.assertIn('RELEASE_NOTES.md?ref='+SHA, requests)
        self.assertNotIn('RELEASE_NOTES.md?ref=cloud-build', requests)

    def test_no_notes_or_empty_summary_prevents_publication(self):
        for override, source in [(None, None), ('', '历史累计说明')]:
            with self.subTest(override=override):
                result, _, _ = self.select(override, source)
                self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
