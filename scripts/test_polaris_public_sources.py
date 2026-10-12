import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import polaris_public_sources as sources
import polaris_production_release as production

REPO=Path(__file__).resolve().parents[1]
class PublicSourceTests(unittest.TestCase):
    def graph(self):
        template=json.loads((REPO/sources.INPUTS).read_bytes());normal=next(r for r in template['modules'] if r['role']=='source-module')
        acquisition=next(r for r in template['modules'] if '_musl' in r['module'])
        return {'normalModules':[{k:normal[k] for k in ['module','version','h1']}],
            'prebuiltAcquisitionModules':[{k:acquisition[k] for k in ['module','version','h1']}],
            'localReplacement':{'module':'github.com/sagernet/sing-tun','version':'frozen','h1':''}}
    def test_exact_actual_union_and_modified_replacement_have_public_sources(self):
        value=sources.delivery(REPO,production.plan(REPO),'a'*40,'b'*40,[self.graph()])
        self.assertEqual(len(value['modules']),2)
        self.assertEqual(value['normalSourceModuleCount'],1)
        self.assertEqual(value['prebuiltAcquisitionModuleCount'],1)
        self.assertEqual(value['productSource']['commit'],'a'*40)
        self.assertEqual(value['productSource']['sourceOwnedReplacement']['replacementFileCount'],256)
        self.assertNotIn('sourceAsset',value)
        self.assertEqual(value['openwrtToolchainCorrespondingSources']['openwrt']['commit'],'0b795ce79e23b553aa184080c390f9ce92a2b6d4')
    def test_unknown_module_or_mixed_replacement_blocks_source_assembly(self):
        for mutation in ['module','replacement']:
            graph=self.graph();other=copy.deepcopy(graph)
            if mutation=='module':other['normalModules'][0]['h1']='h1:unknown'
            else:other['localReplacement']['version']='different'
            with self.assertRaises(ValueError):sources.delivery(REPO,production.plan(REPO),'a'*40,'b'*40,[graph,other])
    def test_bad_public_size_or_digest_preserves_failure_input(self):
        import io
        with tempfile.TemporaryDirectory() as d:
            for expected in [{'bytes':1,'sha256':'a'*64},{'bytes':3,'sha256':'b'*64}]:
                path=Path(d)/str(expected['bytes'])
                with patch.object(sources.urllib.request,'urlopen',return_value=io.BytesIO(b'abc')),self.assertRaises(ValueError):
                    sources.fetch({'url':'https://example.invalid/pinned-source',**expected},path)
                self.assertTrue(path.exists())
if __name__=='__main__':unittest.main()
