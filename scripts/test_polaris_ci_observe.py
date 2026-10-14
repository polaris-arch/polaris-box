import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).with_name('polaris_ci_observe.py')


class ObservationTests(unittest.TestCase):
    def run_child(self, code, timeout=30, expected=0):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'observation'
            env = dict(os.environ, HIDDEN_ENV_TOKEN='do-not-dump-this-marker')
            command = [sys.executable, '-B', str(SCRIPT), '--phase', 'fixture', '--output', str(output),
                       '--timeout-seconds', str(timeout), '--', sys.executable, '-u', '-c', code]
            run = subprocess.run(command, capture_output=True, env=env, timeout=45)
            self.assertEqual(run.returncode, expected, run.stderr.decode())
            row = json.loads((output / 'observation.json').read_text())
            self.assertEqual(row['ciExitCode'], expected)
            self.assertNotIn('do-not-dump-this-marker', json.dumps(row))
            self.assertIsNone(row['memoryObservation']['simultaneousProcessTreePeakBytes'])
            return row, (output / 'command.log').read_bytes(), run.stdout

    def test_success_stream_and_original_failure_code(self):
        row, raw, stdout = self.run_child('import sys; print("out", flush=True); print("err", file=sys.stderr, flush=True)')
        self.assertIn(b'out', raw); self.assertIn(b'err', raw)
        self.assertEqual(row['childMergedStreamSha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(row['outcome'], 'success')
        row, raw, stdout = self.run_child('import sys; print("original-failure"); sys.exit(7)', expected=7)
        self.assertEqual(row['outcome'], 'failure'); self.assertEqual(row['childExitCode'], 7)
        self.assertIn(b'original-failure', raw)

    def test_deadline_fails_and_preserves_original_prefix(self):
        row, raw, stdout = self.run_child('import time; print("before-timeout", flush=True); time.sleep(60)', timeout=0.8, expected=124)
        self.assertEqual(row['outcome'], 'timeout'); self.assertIn(b'before-timeout', raw)

    @unittest.skipIf(os.name == 'nt', 'POSIX signal contract; Windows owns taskkill PID-tree path')
    def test_cancel_preserves_signal_and_reaps_owned_group(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'observation'; marker = Path(folder) / 'started'
            child_code = 'from pathlib import Path; import time; Path(' + repr(str(marker)) + ').write_text("ready"); print("cancel-prefix", flush=True); time.sleep(60)'
            p = subprocess.Popen([sys.executable, '-B', str(SCRIPT), '--phase', 'cancel', '--output', str(output),
                    '--timeout-seconds', '30', '--', sys.executable, '-u', '-c', child_code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 10
            while not marker.exists() and time.monotonic() < deadline: time.sleep(0.05)
            self.assertTrue(marker.exists()); p.send_signal(signal.SIGTERM)
            stdout, stderr = p.communicate(timeout=20)
            self.assertEqual(p.returncode, 128 + signal.SIGTERM, stderr.decode())
            row = json.loads((output / 'observation.json').read_text()); self.assertEqual(row['receivedSignal'], signal.SIGTERM)
            self.assertEqual(row['outcome'], 'cancelled'); self.assertIn(b'cancel-prefix', (output / 'command.log').read_bytes())

    @unittest.skipIf(os.name == 'nt', 'POSIX producer finally owns its detached session')
    def test_deadline_allows_existing_owner_to_close_detached_guest(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'guest.pid'; output = Path(folder) / 'observation'
            code = ('import subprocess,sys,time\nfrom pathlib import Path\n'
                    'guest=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],start_new_session=True)\n'
                    'Path(' + repr(str(marker)) + ').write_text(str(guest.pid))\n'
                    'try: time.sleep(60)\nfinally: guest.terminate();guest.wait()\n')
            run = subprocess.run([sys.executable, '-B', str(SCRIPT), '--phase', 'guest', '--output', str(output),
                  '--timeout-seconds', '1', '--', sys.executable, '-u', '-c', code], capture_output=True, timeout=30)
            self.assertEqual(run.returncode,124,run.stderr.decode())
            pid=int(marker.read_text())
            with self.assertRaises(ProcessLookupError): os.kill(pid,0)
            self.assertEqual(json.loads((output/'observation.json').read_text())['outcome'],'timeout')

    def test_large_output_prefix_budget_does_not_truncate_original_stream(self):
        row, raw, stdout = self.run_child('import sys; sys.stdout.buffer.write(b"x"*(33*1024*1024))')
        self.assertEqual(len(raw), 32 * 1024 * 1024)
        self.assertEqual(row['childMergedStreamBytes'], 33 * 1024 * 1024)
        self.assertTrue(row['artifactLogTruncated']); self.assertGreater(len(stdout), len(raw))


if __name__ == '__main__':
    unittest.main()
