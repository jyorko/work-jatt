"""Inspect real procfs processes and TCP sockets without printing command lines."""

from pathlib import Path
import os
import re
import sys


def is_server(args):
    for index, arg in enumerate(args):
        path = Path(arg)
        is_t3_entry = (
            re.search(r'/dist/(bin|index)\.mjs$', arg)
            and 't3code-cli-main' in path.parts
        ) or (index == 0 and path.name == 't3')
        if not is_t3_entry:
            continue
        options = [value for value in args[index + 1:] if value]
        if any(value.split('=', 1)[0] in {'--help', '-h', '--version', '-v', '-V', '--completions'}
               for value in options):
            return False
        options = iter(options)
        for value in options:
            if value == '--':
                return True
            if value in {'--port', '--host', '--mode', '--base-dir', '--dev-url',
                         '--bootstrap-fd', '--tailscale-serve-port', '--log-level'}:
                next(options, None)
            elif not value.startswith('-'):
                # The first positional value is either a subcommand or the root cwd.
                return value not in {
                    'help', 'app', 'pair', 'auth', 'environment', 'browser', 'project',
                    'thread', 'up', 'status', 'service', 'update', 'install', 'uninstall',
                    'theme', 'trace', 'doctor', 'policy', 'triage', 'connect',
                }
        return True
    return False


def servers():
    result = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().decode(errors='replace').split('\0')
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        if is_server(args):
            result[int(entry.name)] = args
    return result


def listeners():
    result = {}
    for table in ('/proc/net/tcp', '/proc/net/tcp6'):
        for line in Path(table).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == '0A':
                result[fields[9]] = int(fields[1].split(':')[1], 16)
    return result


def owned_listeners(pid, listening):
    owned = set()
    for descriptor in Path(f'/proc/{pid}/fd').iterdir():
        try:
            target = os.readlink(descriptor)
        except FileNotFoundError:
            continue
        if target.startswith('socket:[') and target.endswith(']'):
            owned.add(target[8:-1])
    return {inode: port for inode, port in listening.items() if inode in owned}


def check(mode, pid, prefix=None):
    running = servers()
    competitors = set(running) - {pid}
    if competitors:
        raise ValueError(f'Competing T3 server PID(s): {sorted(competitors)}. No process was stopped.')
    listening = listeners()
    owned = owned_listeners(pid, listening) if pid > 1 else {}
    if mode == 'preflight':
        if any(port == 3773 and inode not in owned for inode, port in listening.items()):
            raise ValueError('TCP port 3773 already has a competing listener. No process was stopped.')
        return
    if pid <= 1 or Path(f'/proc/{pid}').stat().st_uid != os.getuid():
        raise ValueError('The service MainPID is not owned by vscode.')
    expected = {str((Path(prefix) / 'libexec/dist' / name).resolve()) for name in ('bin.mjs', 'index.mjs')}
    if pid not in running or 'serve' not in running[pid] or not any(
        str(Path(arg).resolve()) in expected for arg in running[pid] if arg
    ):
        raise ValueError('The service MainPID is not the installed formula t3 serve process.')
    if not owned:
        raise ValueError('The service MainPID owns no TCP listener yet.')
    print(f'MainPID={pid}, UID={os.getuid()}, one T3 server, owned TCP port(s)={sorted(set(owned.values()))}.')


if __name__ == '__main__':
    try:
        check(sys.argv[1], int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)
    except (OSError, ValueError) as error:
        sys.exit(f'ERROR: {error}')
