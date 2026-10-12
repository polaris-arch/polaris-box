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


class OwnershipRegressionTests(unittest.TestCase):
    def ipk(self,root,bad_section=None):
        import io,tarfile
        path=root/'fixture.ipk'
        with tarfile.open(path,'w:gz') as outer:
            for section in ['control.tar.gz','data.tar.gz']:
                buffer=io.BytesIO()
                with tarfile.open(fileobj=buffer,mode='w:gz') as inner:
                    entry=tarfile.TarInfo('control' if section.startswith('control') else './usr/bin/sing-box')
                    entry.uid=1001 if section==bad_section else 0;entry.gid=0;entry.size=4;inner.addfile(entry,io.BytesIO(b'test'))
                raw=buffer.getvalue();entry=tarfile.TarInfo(section);entry.uid=entry.gid=0;entry.size=len(raw);outer.addfile(entry,io.BytesIO(raw))
        return path
    def test_all_payload_and_control_archive_members_must_be_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertEqual(len(ow.archive_ownership(self.ipk(root),'ipk')['members']),4)
            for section in ['control.tar.gz','data.tar.gz']:
                with self.subTest(section=section),self.assertRaisesRegex(ValueError,'root:root'):
                    ow.archive_ownership(self.ipk(root,section),'ipk')
    def test_apk_all_directory_and_file_acl_owners_are_checked(self):
        with patch.object(ow,'run',return_value=json.dumps({'paths':[{'name':'usr','acl':{'mode':493,'user':'root','group':'root'},'files':[{'name':'bin','acl':{'mode':493,'user':'1001','group':'root'}}]}]})):
            with self.assertRaisesRegex(ValueError,'root:root'):ow.archive_ownership(Path('inert.apk'),'apk',Path('/inert/apk'))
    def test_packaging_command_explicitly_sets_virtual_root_ownership(self):
        with patch.object(ow.shutil,'which',return_value='/usr/bin/fakeroot'), patch.object(ow,'fakeroot_library',return_value=Path('/fixed/libfakeroot.so')):
            args=ow.root_owned_command(Path('/private payload'),['sh','/fixed/sdk/ipkg-build','/private payload','/out'])
            self.assertEqual(args[:5],['fakeroot','-l','/fixed/libfakeroot.so','sh','-ec'])
            self.assertIn('chown -hR 0:0 "$1"',args[5])
            self.assertEqual(args[7],'/private payload')


class GuestProtocolRegressionTests(unittest.TestCase):
    def test_ssh_warning_is_not_part_of_version_or_json_stdout(self):
        import polaris_openwrt_guest as guest
        result=subprocess.CompletedProcess([],0,stdout=b'sing-box version 1.15.0-alpha.12\n',stderr=b'Warning: Permanently added fixture host\n')
        with patch.object(guest.subprocess,'run',return_value=result) as run:
            actual=guest.ssh_command(['ssh','private-fixture'],'sing-box version')
        self.assertEqual(guest.checked_stdout(actual,'version').splitlines()[0],b'sing-box version 1.15.0-alpha.12')
        self.assertEqual(run.call_args.kwargs['stderr'],subprocess.PIPE)
        self.assertTrue(run.call_args.args[0][-1].startswith('set -eu; '))
    def test_fail_fast_shell_cannot_hide_earlier_owner_or_ca_failure(self):
        result=subprocess.run(['sh','-c','set -eu; false; printf masked-success'],capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,b'')
    def test_actual_old_prerm_new_preinst_postinst_order_restores_active_service(self):
        import shlex
        with tempfile.TemporaryDirectory(prefix='polaris-upgrade-order-') as directory:
            root=Path(directory);(root/'etc/config').mkdir(parents=True);(root/'etc/sing-box').mkdir()
            (root/'etc/config/sing-box').write_text('user enabled configuration');(root/'etc/sing-box/config.json').write_text('user JSON')
            state=root/'running';state.touch();calls=root/'calls';service=root/'service'
            service.write_text('#!/bin/sh\ncase "$1" in\n running) test -f '+shlex.quote(str(state))+';;\n stop) printf "stop\n" >> '+shlex.quote(str(calls))+'; rm -f '+shlex.quote(str(state))+';;\n start) printf "start\n" >> '+shlex.quote(str(calls))+'; touch '+shlex.quote(str(state))+';;\nesac\n');service.chmod(0o755)
            for name,args in [('prerm',['upgrade']),('preinst',['upgrade']),('postinst',['configure'])]:
                body=(REPO/'release/openwrt'/name).read_text().replace('/etc/init.d/sing-box',str(service)).replace('$root/etc/',str(root)+'/etc/')
                script=root/name;script.write_text(body)
                subprocess.run(['sh',script,*args],env=dict(os.environ,IPKG_INSTROOT=''),check=True)
            self.assertTrue(state.exists());self.assertEqual(calls.read_text().splitlines(),['stop','start'])
            self.assertEqual((root/'etc/config/sing-box').read_text(),'user enabled configuration')
            self.assertEqual((root/'etc/sing-box/config.json').read_text(),'user JSON')

if __name__=='__main__':unittest.main()
