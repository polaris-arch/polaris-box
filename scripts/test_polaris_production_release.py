import copy
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from polaris_native_candidate import package
from polaris_native_distribution import encode, file_info, read_archive
import polaris_production_release as production

REPO = Path(__file__).resolve().parents[1]
HEAD = 'a' * 40
BUILD_ID = 'polaris.' + 'b' * 64


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.config = production.plan(REPO)

    def fixture(self, base, key='linux/amd64'):
        row = production.target(self.config, key)
        root = base / production.basename(self.config, key)
        root.mkdir()
        core = root / row['executable']
        core.write_bytes(b'inert-core-fixture')
        core.chmod(0o755)
        if row['sidecar']:
            (root / row['sidecar']).write_bytes(b'inert-library-fixture')
        (root / 'provenance.json').write_bytes(b'{}')
        (root / 'SHA256SUMS').write_bytes(b'old checksum')
        archive = base / (root.name + row['suffix'])
        members = package(root, archive, key.split('/')[0])
        index, notice = production.material(REPO, self.config)
        module = next(d for d in index['modules'] if d['sourceBundleMember'])
        pins = json.loads((REPO / self.config['inputPinsPath']).read_bytes())
        smoke = {'os': key.split('/')[0], 'arch': key.split('/')[1], 'version': pins['cronetVersion'],
                 'gvisorCompiled': True, 'linkage': row['cronetLinkage'], 'go': 'go1.25.5'}
        preset = (REPO / 'release' / ('DEFAULT_BUILD_TAGS_WINDOWS' if key.startswith('windows/') else 'DEFAULT_BUILD_TAGS')).read_text().strip()
        tags = preset + (',with_purego' if key.startswith('linux/') else '')
        receipt = {'sourceCommit': HEAD, 'sourceTree': 'c' * 40,
                   'archive': {**file_info(archive), 'members': {n: production.sha(d) for n, d in members.items()}},
                   'archivePath': str(archive), 'payloadHashes': {row['executable']: production.sha(core.read_bytes())},
                   'tags': tags, 'nativeCronetSmoke': smoke,
                   'extractedNativeCronetSmoke': copy.deepcopy(smoke),
                   'coreNative': {'format': 'inert-fixture', 'signatureTrustValidated': False},
                   'cronetNative': {'format': 'inert-fixture', 'signatureTrustValidated': False},
                   'cronet': {'sha256': production.sha(b'inert-library-fixture')}}
        fp = {'sourceCommit': HEAD, 'sourceTree': 'c' * 40}
        graph = {'normalModules': [{k: module[k] for k in ('module', 'version', 'h1')}], 'settings': {'-tags': tags},
                 'prebuiltAcquisitionModules': []}
        return receipt, fp, graph

    def repack(self, base, key, mutate=None, version=None):
        receipt, fp, graph = self.fixture(base, key)
        if mutate:
            mutate(receipt, fp, graph)
        output = base / 'final'
        output.mkdir()
        return production.repackage(REPO, self.config, key, receipt, fp, graph,
            version or 'sing-box version ' + self.config['version'] + '\n', output), receipt

    def test_all_six_layouts_keep_actual_bytes_and_include_root_license(self):
        for row in self.config['desktop']:
            with self.subTest(target=row['target']), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                final, old = self.repack(base, row['target'])
                members = read_archive(base / 'final' / final['archive']['name'], final['archive'])
                root = production.basename(self.config, row['target'])
                self.assertEqual(members[root + '/LICENSE'][0], (REPO / 'LICENSE').read_bytes())
                self.assertEqual(members[root + '/' + row['executable']], (b'inert-core-fixture', 0o755))
                self.assertFalse(final['publicationEligible'])
                self.assertFalse(final['publicUploadPerformed'])
                self.assertEqual(final['archive']['name'], root + row['suffix'])
                self.assertEqual(final['sidecar'] is None, row['sidecar'] is None)

    def test_old_candidate_version_cannot_be_promoted_by_renaming(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, 'actual kernel version'):
            self.repack(Path(directory), 'linux/amd64', version='sing-box version 1.15.0-alpha.11.polaris.candidate-a01da7a9')

    def test_wrong_source_hash_library_and_capabilities_fail_before_output(self):
        mutations = [
            lambda r, f, g: r.update(sourceCommit='d' * 40),
            lambda r, f, g: r['payloadHashes'].update({'sing-box': '0' * 64}),
            lambda r, f, g: r['cronet'].update(sha256='0' * 64),
            lambda r, f, g: r.update(tags='with_naive_outbound'),
            lambda r, f, g: r['extractedNativeCronetSmoke'].update(arch='arm64'),
            lambda r, f, g: g['normalModules'].append({'module': 'new/unreviewed', 'version': 'v1.0.0', 'h1': 'h1:AAAA='}),
        ]
        for mutate in mutations:
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
                self.repack(Path(directory), 'linux/amd64', mutate=mutate)

    def test_member_digest_drift_and_missing_library_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt, fp, graph = self.fixture(base)
            archive = Path(receipt['archivePath'])
            data = archive.read_bytes()
            archive.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, 'fixed bytes/hash'):
                production.repackage(REPO, self.config, 'linux/amd64', receipt, fp, graph,
                    'sing-box version ' + self.config['version'], base)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt, fp, graph = self.fixture(base)
            root = base / production.basename(self.config, 'linux/amd64')
            (root / 'libcronet.so').unlink()
            members = package(root, Path(receipt['archivePath']), 'linux')
            receipt['archive'] = {**file_info(Path(receipt['archivePath'])),
                                   'members': {n: production.sha(d) for n, d in members.items()}}
            with self.assertRaisesRegex(ValueError, 'sidecar absent'):
                production.repackage(REPO, self.config, 'linux/amd64', receipt, fp, graph,
                    'sing-box version ' + self.config['version'], base)

    def actual_info(self, key='linux/amd64'):
        os_name, arch = key.split('/')
        tags = (REPO / 'release' / ('DEFAULT_BUILD_TAGS_WINDOWS' if os_name == 'windows' else 'DEFAULT_BUILD_TAGS')).read_text().strip()
        if os_name == 'linux':
            tags += ',with_purego'
        return '\n'.join(['file: go1.25.5', '\tdep\tfilippo.io/edwards25519\tv1.2.0\th1:AAAA=',
            '\tdep\t' + production.MODULE + '\t' + production.VERSION,
            '\t=>\t' + production.REPLACEMENT + '\t(devel)',
            '\tbuild\tvcs.revision=' + HEAD, '\tbuild\tvcs.modified=false', '\tbuild\tGOOS=' + os_name,
            '\tbuild\tGOARCH=' + arch, '\tbuild\tCGO_ENABLED=' + ('1' if os_name == 'darwin' else '0'),
            '\tbuild\t-tags=' + tags, '\tbuild\t-ldflags=-buildid=' + BUILD_ID])

    def test_real_buildinfo_replacement_without_h1_is_supported(self):
        graph = production.build_info(self.actual_info(), HEAD, BUILD_ID, 'linux/amd64')
        self.assertEqual(graph['localReplacement']['module'], production.MODULE)
        self.assertEqual(len(graph['normalModules']), 1)

    def test_buildinfo_rejects_dirty_wrong_vcs_arch_cgo_and_replacement(self):
        for old, new in [('vcs.modified=false', 'vcs.modified=true'), (HEAD, 'd' * 40),
                         ('GOARCH=amd64', 'GOARCH=arm64'), ('CGO_ENABLED=0', 'CGO_ENABLED=1'),
                         (production.REPLACEMENT, '/tmp/external-replacement'), (BUILD_ID, 'wrong')]:
            with self.subTest(field=old), self.assertRaises(ValueError):
                production.build_info(self.actual_info().replace(old, new), HEAD, BUILD_ID, 'linux/amd64')

    def test_binary_acquisition_modules_remain_separate_from_go_source_zips(self):
        info = self.actual_info() + '\n\tdep\tgithub.com/sagernet/cronet-go/lib/darwin_amd64\tv1.0.0\th1:BBBB='
        graph = production.build_info(info, HEAD, BUILD_ID, 'linux/amd64')
        self.assertEqual(len(graph['normalModules']), 1)
        self.assertEqual(len(graph['prebuiltAcquisitionModules']), 1)

    def test_native_header_rejects_foreign_or_truncated_binary(self):
        elf = bytearray(20)
        elf[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', elf, 18, 62)
        production.native_header(elf, 'linux/amd64')
        for key in ['linux/arm64', 'windows/amd64', 'darwin/amd64']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                production.native_header(elf, key)

    def test_final_load_path_is_checked_but_relocation_is_allowed(self):
        expected = {'os': 'linux', 'version': '154', 'library': '/old/libcronet.so', 'sha256': 'a' * 64}
        actual = {**expected, 'library': '/new/libcronet.so'}
        production.validate_smoke(actual, expected, Path('/new/libcronet.so'))
        for wrong in [{**actual, 'sha256': 'b' * 64}, {**actual, 'library': '/foreign/libcronet.so'}]:
            with self.assertRaises(ValueError):
                production.validate_smoke(wrong, expected, Path('/new/libcronet.so'))

    def test_static_smoke_rejects_any_sidecar(self):
        with self.assertRaises(ValueError):
            production.validate_smoke({'library': '/tmp/x'}, {'library': '/tmp/x'})

    def test_assembly_rejects_partial_or_mixed_run_before_source_assembly(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            old = base / 'old.tar.gz'
            old.write_bytes(b'old')
            config = copy.deepcopy(self.config)
            config['reusedSource'] = file_info(old)
            inputs = base / 'inputs'
            inputs.mkdir()
            with patch.object(production, 'frozen_source', return_value=(config, 'c' * 40)):
                with self.assertRaisesRegex(ValueError, 'six-target'):
                    production.assemble(REPO, HEAD, inputs, old, base / 'out')

    def test_standalone_source_replay_needs_no_legacy_release_download(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = copy.deepcopy(self.config)
            nested = b'inert-exact-retained-input'
            config['reusedSource'].update(bytes=len(nested), sha256=production.sha(nested))
            source = base / 'new-source.tar.gz'
            root = 'polaris-box-' + config['version'] + '-source'
            with tarfile.open(source, 'w:gz') as writer:
                for name, data in [('core-source.tar', b'inert-source'), ('README.md', b'replay'),
                    ('SOURCE-INDEX.json', encode({'version': config['version'], 'sourceCommit': HEAD})),
                    ('reused-inputs.tar.gz', nested)]:
                    entry = tarfile.TarInfo(root + '/' + name)
                    entry.size = len(data)
                    writer.addfile(entry, io.BytesIO(data))
            with patch.object(production.urllib.request, 'urlopen', side_effect=AssertionError('network forbidden')):
                production.recover_source(config, source, production.digest(source), HEAD, base / 'recovered')
            self.assertEqual((base / 'recovered').read_bytes(), nested)
            with self.assertRaises(ValueError):
                production.recover_source(config, source, '0' * 64, HEAD, base / 'bad')
            with self.assertRaises(ValueError):
                production.recover_source(config, source, production.digest(source), 'd' * 40, base / 'bad')

    def test_complete_same_run_assembly_and_standalone_replay_preserve_all_pins(self):
        # Inert binary-shaped fixtures only: mocks return static Go metadata, never execute kernels.
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            inputs = base / 'inputs'
            inputs.mkdir()
            graphs, binary_keys, ids = {}, {}, {}
            for spec in self.config['desktop']:
                key = spec['target']
                platform = inputs / key.replace('/', '-')
                platform.mkdir()
                receipt, fp, graph = self.fixture(platform, key)
                fp['replacement'] = {'replacementTree': 'd' * 40}
                root = platform / production.basename(self.config, key)
                core = root / spec['executable']
                data = bytearray(128)
                os_name, arch = key.split('/')
                if os_name == 'linux':
                    data[:6] = b'\x7fELF\x02\x01'
                    struct.pack_into('<H', data, 18, 62 if arch == 'amd64' else 183)
                elif os_name == 'darwin':
                    data[:4] = b'\xcf\xfa\xed\xfe'
                    struct.pack_into('<I', data, 4, 0x1000007 if arch == 'amd64' else 0x100000c)
                else:
                    data[:2] = b'MZ'
                    struct.pack_into('<I', data, 60, 64)
                    data[64:68] = b'PE\0\0'
                    struct.pack_into('<H', data, 68, 0x8664 if arch == 'amd64' else 0xaa64)
                core.write_bytes(data)
                core.chmod(0o755)
                if spec['sidecar']:
                    (root / spec['sidecar']).write_bytes(data)
                    receipt['cronet']['sha256'] = production.sha(data)
                binary_keys[bytes(data)] = key
                members = package(root, Path(receipt['archivePath']), os_name)
                receipt['archive'] = {**file_info(Path(receipt['archivePath'])),
                                      'members': {n: production.sha(d) for n, d in members.items()}}
                receipt['payloadHashes'][spec['executable']] = production.sha(data)
                receipt.update(workflowCommit=HEAD, workflowRun='20', workflowAttempt='1')
                bid = production.build_identity(fp, key, self.config['version'])
                ids[key] = bid
                info = self.actual_info(key).replace('h1:AAAA=', graph['normalModules'][0]['h1']).replace(BUILD_ID, bid)
                graph = production.build_info(info, HEAD, bid, key)
                graphs[key] = info
                out = platform / 'final'
                out.mkdir()
                final = production.repackage(REPO, self.config, key, receipt, fp, graph,
                    'sing-box version ' + self.config['version'] + '\n', out)
                final.update(buildID=bid, finalPackageCronetSmoke=receipt['nativeCronetSmoke'])
                if spec['sidecar']:
                    final['nativeCronetSmoke']['library'] = '/fixture/' + spec['sidecar']
                    final['finalPackageCronetSmoke'] = dict(final['nativeCronetSmoke'])
                # Keep only the actual final archive in the aggregate input set.
                Path(receipt['archivePath']).unlink()
                (out / 'production-receipt.json').write_bytes(encode(final))
            module = final['buildGraph']['normalModules'][0]
            zip_bytes = b'inert-verified-module-source'
            component = b'inert-component-source'
            old = base / 'old.tar.gz'
            original_index = {'modules': [{**module, 'sourceBundleMember': 'modules/module.zip',
                'zipBytes': len(zip_bytes), 'zipSha256': production.sha(zip_bytes)}],
                'sourceArchiveInputs': [{'filename': 'component.tar.gz', 'bytes': len(component),
                                        'sha256': production.sha(component)}]}
            with tarfile.open(old, 'w:gz') as writer:
                for name, data in [('SOURCE-INDEX.json', encode(original_index)),
                                   ('modules/module.zip', zip_bytes), ('sources/component.tar.gz', component)]:
                    entry = tarfile.TarInfo(name)
                    entry.size = len(data)
                    writer.addfile(entry, io.BytesIO(data))
            config = copy.deepcopy(self.config)
            config['reusedSource'] = file_info(old)
            def static_read(args, *unused):
                path = Path(args[-1])
                if args[:3] == ['go', 'version', '-m']:
                    return graphs[binary_keys[path.read_bytes()]]
                if args[:3] == ['go', 'tool', 'buildid']:
                    return ids[binary_keys[path.read_bytes()]]
                raise AssertionError('unexpected execution: ' + repr(args))
            with patch.object(production, 'frozen_source', return_value=(config, 'c' * 40)), \
                 patch.object(production, 'verify_source'), patch.object(production, 'run', side_effect=static_read), \
                 patch.object(production.subprocess, 'check_output', return_value=b'inert-new-source-tar'), \
                 patch.dict(production.os.environ, {'GITHUB_RUN_ID': '20', 'GITHUB_RUN_ATTEMPT': '1'}):
                result = production.assemble(REPO, HEAD, inputs, old, base / 'final')
                self.assertEqual(result['assetCount'], 9)
                index = json.loads((base / 'final/polaris-box-assets.json').read_bytes())
                self.assertEqual(len(index['platforms']), 6)
                self.assertFalse(index['publicationEligible'])
                self.assertTrue(all(value == 'pending' for value in index['gates'].values()))
                for line in (base / 'final/SHA256SUMS').read_text().splitlines():
                    expected, name = line.split('  ')
                    self.assertEqual(production.digest(base / 'final' / name), expected)
                source = base / 'final' / index['sourceAsset']['name']
                production.recover_source(config, source, index['sourceAsset']['sha256'], HEAD, base / 'recovered-input')
                self.assertEqual((base / 'recovered-input').read_bytes(), old.read_bytes())
                receipt_path = next(inputs.rglob('production-receipt.json'))
                mixed = json.loads(receipt_path.read_bytes())
                mixed['workflowAttempt'] = '2'
                receipt_path.write_bytes(encode(mixed))
                with self.assertRaisesRegex(ValueError, 'mixed source/run/attempt/version'):
                    production.assemble(REPO, HEAD, inputs, old, base / 'mixed-output')

    def test_workflow_is_manual_no_publishing_and_does_not_retarget_historical_lanes(self):
        workflow = (REPO / '.github/workflows/polaris-production-release.yml').read_text()
        self.assertIn('max-parallel: 2', workflow)
        self.assertIn('go-version: \'1.25.5\'', workflow)
        self.assertNotIn('contents: write', workflow)
        for operation in ('gh release', 'git push', '--clobber', 'git tag', 'push:'):
            self.assertNotIn(operation, workflow)
        self.assertIn("inputs.attest && github.ref == 'refs/heads/polaris-main'", workflow)
        self.assertEqual(json.loads((REPO / 'release/polaris-candidate-inputs.json').read_bytes())['sourceCommit'],
                         'a01da7a942b3a0dbbfdfda2bba5bd63d5bd9d932')
        self.assertEqual(json.loads((REPO / 'release/polaris-dns-candidate-inputs.json').read_bytes())['sourceCommit'],
                         'aafc521b745e0d1a8f50a6a3f41169433f1c2194')


if __name__ == '__main__':
    unittest.main()
