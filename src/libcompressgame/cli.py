from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from . import __version__
from .archive import DEFAULT_LIMIT, pack, unpack
from .codecs import Tools
from .common import ArchiveError, absent, no_output_in_source
from .envelope import read_header
from . import sfx
from .provenance import discover


def main(argv=None):
    parser = argparse.ArgumentParser(description='Pack a game directory with eXdupe → OpenZL → BLAKE3 → optional encryption')
    parser.add_argument('--version', action='version', version=__version__)
    subs = parser.add_subparsers(dest='command', required=True)
    create = subs.add_parser('pack', help='Build a host-native self-extracting executable')
    create.add_argument('source', type=Path)
    create.add_argument('output', type=Path)
    create.add_argument('--archive', action='store_true', help='Emit a portable .lcg archive instead of an executable')
    create.add_argument('--encrypt', action='store_true', help='Prompt twice for a password')
    create.add_argument('--password-file', type=Path, help='Encrypt with exact bytes from a protected file')
    create.add_argument('--notice', action='append', default=[], type=Path, help='License/source notice to bundle in SFX (repeatable)')
    create.add_argument('--source-archive', action='append', default=[], type=Path, help='Corresponding source archive to bundle (repeatable)')
    create.add_argument('--memory-mb', type=int, default=256)
    create.add_argument('--threads', type=int, default=2)
    for name in ('unpack', 'verify'):
        p = subs.add_parser(name)
        p.add_argument('archive', type=Path)
        if name == 'unpack':
            p.add_argument('destination', type=Path)
        p.add_argument('--password-file', type=Path)
        p.add_argument('--max-bytes', type=int, default=DEFAULT_LIMIT)
    info = subs.add_parser('info', help='Show untrusted header metadata without extracting')
    info.add_argument('archive', type=Path)
    doctor = subs.add_parser('doctor', help='Check real codec versions and BLAKE3 identities')
    for p in [create, subs.choices['unpack'], subs.choices['verify'], doctor]:
        p.add_argument('--exdupe', type=Path)
        p.add_argument('--zli', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'info':
            with args.archive.open('rb') as src:
                header, _ = read_header(src)
            print(json.dumps(header, indent=2))
            return 0
        tools = Tools.find(args.exdupe, args.zli)
        if args.command == 'doctor':
            print(json.dumps(tools.check(), indent=2))
            return 0
        if args.command == 'pack':
            absent(args.output.absolute())
            no_output_in_source(args.source.resolve(), args.output.resolve())
            notices, sources = args.notice, args.source_archive
            if not args.archive and not notices:
                notices, defaults = discover(tools)
                sources = sources or defaults
            password = sfx.password_file(args.password_file) if args.password_file else sfx.prompt(True) if args.encrypt else None
            if args.archive:
                result = pack(args.source, args.output, tools, password=password,
                              memory_mb=args.memory_mb, threads=args.threads)
            else:
                with tempfile.TemporaryDirectory(prefix='.lcg-build-', dir=args.output.absolute().parent) as temp:
                    archive = Path(temp) / 'game.lcg'
                    result = pack(args.source, archive, tools, password=password,
                                  memory_mb=args.memory_mb, threads=args.threads)
                    sfx.build(archive, args.output.absolute(), tools, [p.resolve() for p in notices],
                              [p.resolve() for p in sources])
                    result['executable_bytes'] = args.output.stat().st_size
            print(json.dumps(result, indent=2))
        else:
            with args.archive.open('rb') as src:
                header, _ = read_header(src)
            password = None
            if header['encryption'] != 'none':
                password = sfx.password_file(args.password_file) if args.password_file else sfx.prompt()
            destination = args.destination if args.command == 'unpack' else Path.cwd() / '.verify-unused'
            result = unpack(args.archive, destination, tools, password=password,
                            max_bytes=args.max_bytes, verify_only=args.command == 'verify')
            print(f'Verified {result["entries"]} entries' if args.command == 'verify' else f'Extracted to {destination}')
        return 0
    except (ArchiveError, OSError, ValueError, EOFError, subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        print(f'libcompressgame: {exc}', file=sys.stderr)
        return 2
