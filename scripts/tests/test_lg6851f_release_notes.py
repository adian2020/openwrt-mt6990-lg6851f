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
        end = workflow.index('\n      - name: Download firmware artifacts', start)
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
                       source_sha=SHA, SOURCE_RUN_ID='999', GITHUB_REPOSITORY='adian2020/openwrt-mt6990-lg6851f')
            result = subprocess.run(['bash', '-eu', '-o', 'pipefail', '-c', shell], cwd=root,
                                    env=env, capture_output=True, text=True)
            notes = root / 'RELEASE_NOTES.md'
            return result, notes.read_text() if notes.exists() else None, (root/'requests').read_text()

    def test_exact_build_summary_wins_over_cumulative_source_notes(self):
        result, notes, requests = self.select('本版本新增、修改、删除\n', '历史累计说明\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(notes.startswith('[固件更新历史](https://github.com/adian2020/openwrt-mt6990-lg6851f/blob/cloud-build/docs/FIRMWARE_HISTORY.md)\n\n本版本新增、修改、删除\n'))
        self.assertNotIn('历史累计说明', notes)
        self.assertEqual(len(requests.splitlines()), 1)
        self.assertIn(SHA+'.md?ref=cloud-build', requests)

    def test_missing_override_uses_exact_source_commit(self):
        result, notes, requests = self.select(None, '源码版本说明\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\n\n源码版本说明\n', notes)
        self.assertIn('RELEASE_NOTES.md?ref='+SHA, requests)
        self.assertNotIn('RELEASE_NOTES.md?ref=cloud-build', requests)

    def test_no_notes_or_empty_summary_prevents_publication(self):
        for override, source in [(None, None), ('', '历史累计说明')]:
            with self.subTest(override=override):
                result, _, _ = self.select(override, source)
                self.assertNotEqual(result.returncode, 0)


class FirmwareHistoryTest(unittest.TestCase):
    def publish(self, mode='normal'):
        text = WORKFLOW.read_text().split('      - name: Update published firmware history\n', 1)[1]
        script = text.split("          python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
        script = '\n'.join(line[10:] for line in script.splitlines())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = '# 固件更新历史\n\n<!-- firmware-history -->\n\n旧版记录\n'
            if mode == 'existing':
                initial += '<!-- release:v1.0.20 -->\n已有本版记录\n'
            (root/'history').write_text(initial)
            gh = root/'gh'
            gh.write_text('''#!/usr/bin/env python3
import base64,json,os,pathlib,sys
r=pathlib.Path(os.environ['FIXTURE']);args=sys.argv[1:];mode=os.environ['MODE']
repo='repos/adian2020/openwrt-mt6990-lg6851f/'
assert args[0]=='api'
if args[1:3]==['--method','PUT']:
 assert args[3:]==[repo+'contents/docs/FIRMWARE_HISTORY.md','--input','-']
 payload=json.load(sys.stdin)
 assert payload['branch']=='cloud-build' and payload['message']=='Record firmware history for v1.0.20'
 if mode=='conflict' and not (r/'conflicted').exists():
  (r/'conflicted').touch();(r/'history').write_text((r/'history').read_text()+'并发新增记录\\n')
  print('HTTP 409: file changed',file=sys.stderr);sys.exit(1)
 (r/'payload').write_text(json.dumps(payload))
 print(json.dumps({'commit':{'sha':'2'*40}}))
else:
 assert len(args)==2
 path=args[1]
 if path==repo+'releases/tags/v1.0.20':
  print(json.dumps(dict(tag_name='v1.0.20',draft=False,prerelease=False,published_at='2026-11-15T23:45:06Z',html_url='https://github.com/adian2020/openwrt-mt6990-lg6851f/releases/tag/v1.0.20',body='[固件更新历史](https://example.invalid/history)\\n\\n# 本版本更新\\n\\n## 修改\\n\\n- 修复切槽。\\n\\n## 构建信息\\n\\n- 不重复记录此段。')))
 elif path==repo+'git/ref/tags/v1.0.20':
  print(json.dumps({'object':{'type':'commit','sha':('3' if mode=='mismatch' else '1')*40}}))
 elif path==repo+'contents/docs/FIRMWARE_HISTORY.md?ref=cloud-build':
  print(json.dumps({'sha':'f'*40,'content':base64.b64encode((r/'history').read_bytes()).decode()}))
 else:raise AssertionError(path)
''')
            gh.chmod(0o755)
            env = dict(os.environ, PATH=str(root)+':'+os.environ['PATH'], FIXTURE=str(root), MODE=mode,
                       SOURCE_SHA=SHA, TAG_NAME='v1.0.20', GITHUB_REPOSITORY='adian2020/openwrt-mt6990-lg6851f')
            result = subprocess.run(['python3', '-c', script], env=env, cwd=root, capture_output=True, text=True)
            payload = json.loads((root/'payload').read_text()) if (root/'payload').exists() else None
            return result, payload

    def test_published_time_and_current_changes_are_recorded(self):
        result, payload = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        history = base64.b64decode(payload['content']).decode()
        self.assertIn('发布时间：2026-11-15 23:45:06 UTC', history)
        self.assertIn('### 修改\n\n- 修复切槽。', history)
        self.assertIn('旧版记录', history)
        self.assertNotIn('example.invalid', history)
        self.assertNotIn('不重复记录此段', history)
        self.assertLess(history.index('release:v1.0.20'), history.index('旧版记录'))

    def test_rerun_does_not_duplicate_or_overwrite_existing_history(self):
        result, payload = self.publish('existing')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(payload)

    def test_conflict_reloads_and_preserves_concurrent_changes(self):
        result, payload = self.publish('conflict')
        self.assertEqual(result.returncode, 0, result.stderr)
        history = base64.b64decode(payload['content']).decode()
        self.assertIn('并发新增记录', history)
        self.assertEqual(history.count('<!-- release:v1.0.20 -->'), 1)

    def test_wrong_source_tag_cannot_write_history(self):
        result, payload = self.publish('mismatch')
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(payload)


if __name__ == '__main__':
    unittest.main()
