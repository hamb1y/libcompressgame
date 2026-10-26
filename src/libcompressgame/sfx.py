from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from .archive import DEFAULT_LIMIT, unpack
from .codecs import Tools
from .common import ArchiveError, absent, atomic_file
from .envelope import read_header


def password_file(path):
    # File bytes are exact: no newline stripping, environment variables, or command-line secret.
    with Path(path).open('rb') as source:
        data = source.read(1025)
    if not data or len(data) > 1024:
        raise ArchiveError('Password file must contain 1..1024 bytes (including any newline)')
    return data


def prompt(confirm=False):
    value = getpass.getpass('Archive password: ').encode('utf-8')
    if not value or len(value) > 1024:
        raise ArchiveError('Password must contain 1..1024 UTF-8 bytes')
    if confirm and value != getpass.getpass('Confirm password: ').encode('utf-8'):
        raise ArchiveError('Passwords do not match')
    return value


def build(archive: Path, output: Path, tools: Tools, notices: list[Path], sources: list[Path] | None = None):
    """Build on the target OS. Bundle payload, native tools, runtime and supplied notices."""
    if sys.platform not in ('linux', 'win32'):
        raise ArchiveError('SFX builds require Linux or Windows')
    absent(output)
    if sys.platform == 'win32' and output.suffix.lower() != '.exe':
        raise ArchiveError('Windows self-extractors need a .exe output name')
    if not notices or any(not p.is_file() for p in notices):
        raise ArchiveError('Supply --notice files with decoder license/source distribution notices')
    try:
        import PyInstaller
    except ImportError as exc:
        raise ArchiveError('SFX build dependency missing: pip install libcompressgame[build]') from exc
    with tempfile.TemporaryDirectory(prefix='.lcg-sfx-', dir=output.parent) as temp:
        work = Path(temp)
        entry = work / 'extract_game.py'
        entry.write_text('from libcompressgame.sfx import main\nraise SystemExit(main())\n', encoding='utf-8')
        # Fixed internal names make decoder selection independent of upstream executable names.
        bundle = work / 'bundle'
        bundle.mkdir()
        suffix = '.exe' if sys.platform == 'win32' else ''
        for name, path in [('exdupe', tools.exdupe), ('zli', tools.zli)]:
            shutil.copy2(path, bundle / (name + suffix))
        notice_dir = bundle / 'notices'
        notice_dir.mkdir()
        for index, path in enumerate(notices):
            shutil.copy2(path, notice_dir / f'{index:03}-{path.name}')
        source_dir = bundle / 'sources'
        source_dir.mkdir()
        for path in sources or []:
            if not path.is_file() or (source_dir / path.name).exists():
                raise ArchiveError('Source archives must exist and have distinct names')
            shutil.copy2(path, source_dir / path.name)
        args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--noupx',
                '--console', '--name', 'game-extractor', '--distpath', str(work / 'dist'),
                '--workpath', str(work / 'build'), '--specpath', str(work),
                '--paths', str(Path(__file__).resolve().parent.parent),
                '--collect-all', 'blake3', '--copy-metadata', 'blake3',
                '--collect-all', 'cryptography', '--copy-metadata', 'cryptography',
                '--add-data', f'{archive}{os.pathsep}.',
                '--add-data', f'{notice_dir}{os.pathsep}notices',
                '--add-data', f'{source_dir}{os.pathsep}sources',
                '--add-binary', f'{bundle / ("exdupe" + suffix)}{os.pathsep}tools',
                '--add-binary', f'{bundle / ("zli" + suffix)}{os.pathsep}tools', str(entry)]
        result = subprocess.run(args, cwd=work)
        if result.returncode:
            raise ArchiveError(f'PyInstaller failed ({result.returncode})')
        built = work / 'dist' / ('game-extractor' + suffix)
        atomic_file(built, output, 0o755)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verify and extract this packaged game directory')
    parser.add_argument('destination', nargs='?', type=Path)
    parser.add_argument('--verify', action='store_true', help='Verify all bytes without publishing a directory')
    parser.add_argument('--info', action='store_true', help='Show archive header without extracting')
    parser.add_argument('--licenses', action='store_true', help='Print bundled third-party notices')
    parser.add_argument('--export-sources', type=Path, help='Copy bundled corresponding source archives to a new directory')
    parser.add_argument('--password-file', type=Path)
    parser.add_argument('--max-bytes', type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args(argv)
    try:
        if not getattr(sys, 'frozen', False):
            raise ArchiveError('This entry point is intended for a built self-extractor')
        base = Path(sys._MEIPASS)
        archive = base / 'game.lcg'
        if args.export_sources:
            from .archive import publish_directory
            absent(args.export_sources.absolute())
            with tempfile.TemporaryDirectory(prefix='.lcg-sources-', dir=args.export_sources.absolute().parent) as temp:
                stage = Path(temp) / 'sources'
                shutil.copytree(base / 'sources', stage)
                publish_directory(stage, args.export_sources.absolute())
            return 0
        if args.licenses:
            for path in sorted((base / 'notices').iterdir()):
                print(path.read_text(encoding='utf-8'))
            return 0
        with archive.open('rb') as src:
            header, _ = read_header(src)
        if args.info:
            print(json.dumps(header, indent=2))
            return 0
        if args.destination is None and not args.verify:
            parser.error('destination is required unless --verify, --info or --licenses is used')
        password = None
        if header['encryption'] != 'none':
            password = password_file(args.password_file) if args.password_file else prompt()
        suffix = '.exe' if sys.platform == 'win32' else ''
        tools = Tools(base / 'tools' / ('exdupe' + suffix), base / 'tools' / ('zli' + suffix))
        if tools.hashes() != header['tools']:
            raise ArchiveError('Bundled decoder BLAKE3 check failed')
        result = unpack(archive, args.destination or Path.cwd() / '.verify-unused', tools,
                        password=password, max_bytes=args.max_bytes, verify_only=args.verify)
        print(f'Verified {result["entries"]} entries' if args.verify else f'Extracted to {args.destination}')
        return 0
    except (ArchiveError, OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
        print(f'libcompressgame: {exc}', file=sys.stderr)
        return 2
