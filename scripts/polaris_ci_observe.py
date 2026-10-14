#!/usr/bin/env python3
"""Stream one existing CI command and preserve bounded failure/cancel observations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import threading
import time

LOG_LIMIT = 32 * 1024 * 1024


def memory_observation(child):
    if os.name != 'nt':
        import resource
        peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        return {'kind': 'OS-child-rusage-maxrss',
                'bytes': int(peak) * (1 if platform.system() == 'Darwin' else 1024) if peak else None,
                'simultaneousProcessTreePeakBytes': None}
    try:
        import ctypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        value = Counters()
        value.cb = ctypes.sizeof(value)
        api = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
        api.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        api.restype = ctypes.c_int
        if not api(int(child._handle), ctypes.byref(value), value.cb):
            raise OSError('process memory observation unavailable')
        peak = int(value.PeakWorkingSetSize)
    except (OSError, AttributeError, TypeError):
        peak = None
    return {'kind': 'Windows-direct-child-peak-working-set', 'bytes': peak or None,
            'simultaneousProcessTreePeakBytes': None}


def terminate_owned_tree(child):
    if os.name == 'nt':
        if child.poll() is not None:
            return
        # Only this invocation's owned PID tree; no image-name/global task kill.
        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
    else:
        # Existing Python producers use finally to close their own detached
        # guest QEMU processes. Interrupt first so those owners can clean up;
        # do not discover/kill unrelated PIDs or assume a shared session.
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(child.pid, number)
            except ProcessLookupError:
                return
            if number != signal.SIGKILL:
                try:
                    child.wait(timeout=10)
                    return
                except subprocess.TimeoutExpired:
                    pass


def observe(command, phase, output, timeout, log_limit=LOG_LIMIT, heartbeat=60):
    if not re.fullmatch(r'[a-z0-9-]{1,64}', phase) or not command or not 0 < timeout <= 6 * 3600:
        raise ValueError('bounded phase, command and deadline required')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    stopped = threading.Event()
    reason = {'signal': None, 'timeout': False}
    child = None
    count = retained = 0
    digest = hashlib.sha256()
    handlers = {}
    error = None
    eof = False
    code = 127
    def cancel(number, _frame):
        reason['signal'] = number
    for number in (signal.SIGINT, signal.SIGTERM):
        handlers[number] = signal.signal(number, cancel)
    def watchdog():
        next_heartbeat = heartbeat
        while not stopped.wait(0.25):
            elapsed = time.monotonic() - started
            if elapsed >= timeout or reason['signal'] is not None:
                reason['timeout'] = elapsed >= timeout and reason['signal'] is None
                try:
                    terminate_owned_tree(child)
                except (OSError, subprocess.SubprocessError):
                    child.kill()
                return
            if elapsed >= next_heartbeat:
                print(json.dumps({'schema': 'polaris-ci-heartbeat-v1', 'phase': phase,
                                  'elapsedSeconds': round(elapsed, 2), 'childRunning': child.returncode is None}), flush=True)
                next_heartbeat += heartbeat
    try:
        print(json.dumps({'schema': 'polaris-ci-phase-start-v1', 'phase': phase,
                          'deadlineSeconds': timeout, 'resourcePolicyChanged': False}), flush=True)
        options = {'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options['start_new_session'] = True
        child = subprocess.Popen(command, **options)
        watcher = threading.Thread(target=watchdog, daemon=True)
        watcher.start()
        with (output / 'command.log').open('xb') as log:
            while block := child.stdout.read1(64 * 1024):
                digest.update(block)
                count += len(block)
                take = max(0, min(len(block), log_limit - retained))
                if take:
                    log.write(block[:take]); retained += take
                # Original CI log is streamed in full; only the extra artifact
                # prefix is bounded. Never turn truncated retained bytes into a
                # claim that all output was preserved in this extra file.
                sys.stdout.buffer.write(block)
                sys.stdout.buffer.flush()
        eof = True
        child.stdout.close()
        code = child.wait()
    except (OSError, ValueError) as failure:
        error = type(failure).__name__
        if child is not None:
            terminate_owned_tree(child)
            code = child.wait()
        if code == 0:
            code = 1
    finally:
        stopped.set()
        for number, handler in handlers.items():
            signal.signal(number, handler)
        memory = memory_observation(child) if child is not None else {
            'kind': 'not-launched', 'bytes': None, 'simultaneousProcessTreePeakBytes': None}
        exit_code = 124 if reason['timeout'] else 128 + reason['signal'] if reason['signal'] else code if code >= 0 else 128 - code
        result = {'schema': 'polaris-ci-command-observation-v1', 'phase': phase,
                  'workflowCommit': os.environ.get('GITHUB_SHA'), 'sourceCommit': os.environ.get('SOURCE_COMMIT'),
                  'outcome': 'timeout' if reason['timeout'] else 'cancelled' if reason['signal'] else 'success' if exit_code == 0 else 'failure',
                  'childExitCode': code, 'ciExitCode': exit_code, 'receivedSignal': reason['signal'],
                  'elapsedSeconds': round(time.monotonic() - started, 3), 'memoryObservation': memory,
                  'childMergedStreamBytes': count, 'childMergedStreamSha256': digest.hexdigest(),
                  'artifactLogPrefixBytes': retained, 'artifactLogTruncated': count > retained,
                  'fullOriginalStreamLocation': 'original GitHub job log', 'streamObservedThroughEOF': eof, 'resourcePolicyChanged': False,
                  'observerErrorKind': error, 'observerEnvironmentDumped': False, 'observerArgvDumped': False}
        try:
            (output / 'observation.json').write_text(json.dumps(result, indent=2) + '\n')
        except OSError:
            if exit_code == 0:
                exit_code = 1  # Lost required observation cannot become success.
            result.update(ciExitCode=exit_code, outcome='failure', observerErrorKind='observation-write-failure')
        print(json.dumps(result, sort_keys=True), flush=True)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=float, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    raise SystemExit(observe(command, args.phase, args.output, args.timeout_seconds))


if __name__ == '__main__':
    main()
