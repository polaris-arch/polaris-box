import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import polaris_ci_impact as impact

ROOT = Path(__file__).resolve().parents[1]
BASE = 'a635e5345b0f44e716c20ddf95e5d2eba9db3159'
INHERITED_SHA256 = {'build.yml': 'd8b360327678fc83e42623259ddd61837b48bb05888ff1cfcd4aeb21d6f79797', 'docker.yml': 'd3885bf24d8963d083a9af5616947b86e1210e10ba36082ad5e89a8b6fb833f3', 'lint.yml': '9b64db877204005136a387cb27efa91946bee5a19f47cc2e50685348cd3ebbc0', 'linux.yml': '3cffc76d7e92229757a3832b38ba7154810dc59a68c7e36eaeafd919dd0aaf2e', 'stale.yml': 'bc7400aff64735578e663d255ac576185dd35599d9e5711b907428af3be24e48', 'test.yml': '4280bfd5da874a8119a44aad5cff3bd9ed700e636dd2bf391efb943ae08fd5b5'}
INHERITED = ('build.yml', 'docker.yml', 'linux.yml', 'lint.yml', 'test.yml', 'stale.yml')
WORKFLOWS = set(INHERITED) | {'polaris-selfcheck.yml', 'polaris-production-native.yml',
    'polaris-production-release.yml', 'polaris-native-candidate.yml', 'polaris-dns-native-candidate.yml'}


class ImpactTests(unittest.TestCase):
    def test_exact_allowlist_and_all_protected_negative_paths(self):
        guide = next(iter(impact.PROSE))
        def row(name, old='100644', new='100644', status='M'):
            return {'path': name, 'oldMode': old, 'newMode': new, 'status': status}
        self.assertTrue(impact.classify_changes([row(guide)]))
        self.assertFalse(impact.classify_changes([]))
        for name in ('README.md', 'LICENSE', 'NOTICE', 'docs/configuration/dns/index.md',
            'docs/schema.json', 'docs/install.sh', 'release/POLARIS_ASSETS.md',
            'release/POLARIS_OPENWRT.md', 'release/licenses/license.md', 'release/NOTICE.md',
            'release/polaris-production-release.json', 'go.mod', 'go.sum',
            'third_party/sing-tun/go.sum', 'scripts/polaris_ci_impact.py',
            '.github/workflows/polaris-selfcheck.yml', 'unexpected.md', 'box.go'):
            with self.subTest(path=name):
                self.assertFalse(impact.classify_changes([row(guide), row(name)]))
        for mode in ('100755', '120000', '160000'):
            self.assertFalse(impact.classify_changes([row(guide, new=mode)]))
        self.assertFalse(impact.classify_changes([row(guide, status='T')]))

    def test_raw_diff_control_unicode_and_malformed(self):
        sha = 'a' * 40
        raw = (':100644 100644 ' + sha + ' ' + sha + ' M\0' + next(iter(impact.PROSE)) + '\0').encode()
        self.assertTrue(impact.classify_changes(impact.parse_raw(raw)))
        for broken in (b'incomplete', raw[:-1], b':wrong\0name\0', b'X' * (impact.LIMIT + 1)):
            with self.assertRaises(ValueError):
                impact.parse_raw(broken)

    def test_real_git_doc_push_full_audits_and_embed_negative(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()
            git('init', '-q'); git('config', 'user.name', 'fixture'); git('config', 'user.email', 'fixture@example.invalid')
            guide = repo / next(iter(impact.PROSE)); guide.parent.mkdir(); guide.write_text('pure instructions\n')
            (repo / 'box.go').write_text('package box\n')
            git('add', '.'); git('commit', '-qm', 'base'); before = git('rev-parse', 'HEAD')
            guide.write_text('revised instructions\n'); git('add', '.'); git('commit', '-qm', 'docs'); head = git('rev-parse', 'HEAD')
            event = {'repository': {'full_name': 'polaris-arch/polaris-box'}, 'before': before,
                     'after': head, 'deleted': False, 'forced': False}
            def run(event=event, name='push', ref='refs/heads/polaris-main', sha=head):
                return impact.classify(repo, event, name, ref, sha)
            self.assertFalse(run()['runFull'])
            for name, ref in [('workflow_dispatch', 'refs/heads/polaris-main'), ('push', 'refs/tags/polaris-fixed'),
                               ('pull_request', 'refs/pull/1/merge')]:
                self.assertTrue(run(name=name, ref=ref)['runFull'])
            for change in ({'forced': True}, {'deleted': True}, {'before': '0' * 40},
                           {'after': 'a' * 40}, {'repository': None}, {'repository': {'full_name': 'other/repo'}}):
                self.assertTrue(run(event={**event, **change})['runFull'])
            with patch.object(impact, 'git', side_effect=OSError('unavailable')):
                self.assertTrue(run()['runFull'])
            (repo / 'box.go').write_text('package box\n//go:embed all:release/*\n')
            git('add', '.'); git('commit', '-qm', 'embed'); before = git('rev-parse', 'HEAD')
            guide.write_text('still prose but now compiled input\n'); git('add', '.'); git('commit', '-qm', 'doc'); head = git('rev-parse', 'HEAD')
            self.assertTrue(impact.classify(repo, {**event, 'before': before, 'after': head}, 'push', 'refs/heads/polaris-main', head)['runFull'])

    def test_complete_workflow_coverage_and_frozen_inherited_sources(self):
        self.assertEqual({p.name for p in (ROOT / '.github/workflows').glob('*.yml')}, WORKFLOWS)
        for name in INHERITED:
            self.assertEqual(hashlib.sha256((ROOT / '.github/workflows' / name).read_bytes()).hexdigest(), INHERITED_SHA256[name])
        for name in ('polaris-production-release.yml', 'polaris-native-candidate.yml', 'polaris-dns-native-candidate.yml'):
            text = (ROOT / '.github/workflows' / name).read_text()
            self.assertIn('  queue: max\n', text)
            self.assertIn('  cancel-in-progress: false\n', text)
        text = (ROOT / '.github/workflows/polaris-selfcheck.yml').read_text()
        self.assertNotIn('  queue: max', text)
        self.assertIn("format('audit-{0}', github.run_id)", text)
        self.assertIn("needs.classify.outputs.run_full == 'true'", text)
        for name, pin in [('polaris-native-candidate.yml', 'a01da7a942b3a0dbbfdfda2bba5bd63d5bd9d932'),
                          ('polaris-dns-native-candidate.yml', 'aafc521b745e0d1a8f50a6a3f41169433f1c2194')]:
            self.assertIn('ref: ' + pin, (ROOT / '.github/workflows' / name).read_text())


if __name__ == '__main__':
    unittest.main()
