import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import polaris_openwrt as ow

REPO=Path(__file__).resolve().parents[1]

class OpenWrtTests(unittest.TestCase):
    def test_scope_and_linker_contract_preserve_generic_capabilities(self):
        config=ow.plan(REPO)
        self.assertEqual(config['clangInput']['revision'],'llvmorg-24-init-3796-g20e97c4b-27')
        self.assertEqual(config['clangInput']['sha256'],'968195fa0b49958e066695df2c7c985d169a20fa06eedb8fcef900a6030edcb0')
        self.assertEqual({r['architecture'] for r in config['targets']},{'x86_64','aarch64_generic'})
        self.assertEqual(len(config['guestInputs']),4)
        self.assertFalse(config['publicationEligible']);self.assertFalse(config['realDeviceAcceptance'])
        self.assertEqual(config['package']['provides'],[])

    def test_payload_preserves_binary_mode_and_has_disabled_safe_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);core=root/'core';core.write_bytes(b'inert-core')
            inventory=ow.payload(REPO,ow.plan(REPO),core,root/'payload',{'fixture':True})
            p=root/'payload';self.assertEqual((p/'usr/bin/sing-box').read_bytes(),b'inert-core')
            self.assertEqual(inventory['usr/bin/sing-box']['mode'],0o755)
            self.assertIn("option enabled '0'",(p/'etc/config/sing-box').read_text())
            self.assertEqual(json.loads((p/'etc/sing-box/config.json').read_bytes())['inbounds'],[])
            self.assertFalse(list(p.rglob('*.so')))
            for name in ['MUSL-COPYRIGHT.txt','GCC-RUNTIME-LIBRARY-EXCEPTION-3.1.txt','GPL-3.0.txt']:
                self.assertTrue((p/'usr/share/licenses/polaris-box'/name).is_file())

    def test_actual_shell_lifecycle_preserves_preexisting_and_removed_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'etc/config').mkdir(parents=True);(root/'etc/sing-box').mkdir()
            uci=root/'etc/config/sing-box';cfg=root/'etc/sing-box/config.json';uci.write_bytes(b'user uci\n');cfg.write_bytes(b'user configuration\n')
            env=dict(os.environ,IPKG_INSTROOT=str(root))
            def shell(name,*args):subprocess.run(['sh',str(REPO/'release/openwrt'/name),*args],env=env,check=True)
            shell('preinst');uci.write_bytes(b'package default');cfg.write_bytes(b'package default');shell('postinst')
            self.assertEqual(uci.read_bytes(),b'user uci\n');self.assertEqual(cfg.read_bytes(),b'user configuration\n')
            shell('prerm','remove');uci.unlink();cfg.unlink();shell('postrm','remove')
            self.assertEqual(uci.read_bytes(),b'user uci\n');self.assertEqual(cfg.read_bytes(),b'user configuration\n')
            # Manager-retained/new user paths are never overwritten by remove recovery.
            cfg.write_bytes(b'new user config');shell('postrm','remove');self.assertEqual(cfg.read_bytes(),b'new user config')

    def test_upgrade_never_disables_or_creates_removal_backup(self):
        with tempfile.TemporaryDirectory() as d:
            env=dict(os.environ,IPKG_INSTROOT=d)
            for script in ['prerm','postrm']:
                subprocess.run(['sh',str(REPO/'release/openwrt'/script),'upgrade'],env=env,check=True)
            self.assertFalse((Path(d)/'etc/polaris-box/retained-config').exists())

    def test_foreign_elf_or_dynamic_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            core=Path(d)/'core';core.write_bytes(b'not ELF')
            with self.assertRaises(ValueError):ow.check_static(core,'x86_64')
            data=bytearray(64);data[:6]=b'\x7fELF\x02\x01';data[18:20]=(62).to_bytes(2,'little');core.write_bytes(data)
            with patch.object(ow,'run',return_value=' INTERP NEEDED GLIBC_2.39'):
                with self.assertRaisesRegex(ValueError,'interpreter/glibc'):ow.check_static(core,'x86_64')
            with self.assertRaises(ValueError):ow.check_static(core,'aarch64_generic')

    def test_partial_guest_inventory_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inputs=root/'inputs';inputs.mkdir();guests=root/'guests';guests.mkdir()
            with self.assertRaisesRegex(ValueError,'two OpenWrt'):ow.validate_assembled_openwrt(REPO,'a'*40,'b'*40,inputs,guests,root/'out','20','1')

if __name__=='__main__':unittest.main()
