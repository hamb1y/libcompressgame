from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata

from .common import ArchiveError, MAX_JSON, U64, canonical, copy_n, exact, new_hash

MAGIC = b'LCGDIR1\0'
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{x}' for x in '123456789¹²³'), *(f'LPT{x}' for x in '123456789¹²³')}


def safe_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode('utf-8', errors='surrogatepass')) > 4096:
        raise ArchiveError('Invalid archive path')
    pieces = value.split('/')
    for p in pieces:
        if (not p or p in ('.', '..') or p[-1:] in (' ', '.') or
                any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF or c in '<>:"\\|?*' for c in p) or
                p.split('.')[0].upper() in RESERVED):
            raise ArchiveError(f'Unsafe or nonportable path: {value!r}')
    if PurePosixPath(value).is_absolute():
        raise ArchiveError(f'Absolute path: {value!r}')
    return value


def validate(entries):
    if not isinstance(entries, list) or len(entries) > 100000:
        raise ArchiveError('Manifest must contain at most 100000 entries')
    names = {}
    prior = ''
    for e in entries:
        if not isinstance(e, dict) or e.keys() != {'path', 'kind', 'mode', 'size', 'blake3'}:
            raise ArchiveError('Invalid manifest entry')
        name = safe_path(e['path'])
        folded = unicodedata.normalize('NFC', name).casefold()
        if folded in names or name <= prior:
            raise ArchiveError('Duplicate, case-colliding, or unsorted manifest paths')
        parent = str(PurePosixPath(name).parent)
        if parent != '.' and names.get(unicodedata.normalize('NFC', parent).casefold()) != 'dir':
            raise ArchiveError('Missing directory or file used as parent')
        if e['kind'] not in ('file', 'dir') or type(e['mode']) is not int or not 0 <= e['mode'] <= 0o777:
            raise ArchiveError('Invalid file type or mode')
        if type(e['size']) is not int or not 0 <= e['size'] <= 2**63 - 1:
            raise ArchiveError('Invalid file size')
        if e['kind'] == 'dir':
            if e['size'] != 0 or e['blake3'] is not None:
                raise ArchiveError('Invalid directory metadata')
        elif not isinstance(e['blake3'], str) or not re.fullmatch('[0-9a-f]{64}', e['blake3']):
            raise ArchiveError('Invalid BLAKE3 digest')
        names[folded] = e['kind']
        prior = name
    return entries


def open_regular(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    f = os.fdopen(fd, 'rb')
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        f.close()
        raise ArchiveError(f'Input is no longer a regular file: {path}')
    return f


def _add_entry(path, source, entries, metadata_size):
    rel = safe_path(path.relative_to(source).as_posix())
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_reparse_tag', 0):
        raise ArchiveError(f'Symlinks and reparse points are unsupported: {rel}')
    if stat.S_ISDIR(st.st_mode):
        kind, size, digest = 'dir', 0, None
    elif stat.S_ISREG(st.st_mode):
        kind, size, h = 'file', st.st_size, new_hash()
        with open_regular(path) as f:
            while data := f.read(1024 * 1024):
                h.update(data)
            after = os.fstat(f.fileno())
        if (st.st_size, st.st_mtime_ns, st.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ArchiveError(f'Source changed during snapshot: {rel}')
        digest = h.hexdigest()
    else:
        raise ArchiveError(f'Special file unsupported: {rel}')
    entry = dict(path=rel, kind=kind, mode=stat.S_IMODE(st.st_mode) & 0o777,
                 size=size, blake3=digest)
    metadata_size[0] += len(canonical(entry)) + 1
    if metadata_size[0] > MAX_JSON:
        raise ArchiveError('Manifest exceeds 16 MiB')
    entries.append(entry)
    if len(entries) > 100000:
        raise ArchiveError('At most 100000 entries supported')


def build(source: Path, output: Path):
    """Snapshot sorted portable metadata and bytes. Files changing mid-read fail."""
    if not source.is_dir() or source.is_symlink():
        raise ArchiveError('Source must be an ordinary directory')
    entries = []
    metadata_size = [2]
    pending = [source]
    while pending:
        root = pending.pop()
        with os.scandir(root) as listing:
            for item in listing:
                path = Path(item.path)
                if len(entries) >= 100000:
                    raise ArchiveError('At most 100000 entries supported')
                st = path.lstat()
                if stat.S_ISDIR(st.st_mode) and not getattr(st, 'st_reparse_tag', 0):
                    pending.append(path)
                _add_entry(path, source, entries, metadata_size)
    entries.sort(key=lambda e: e['path'])
    validate(entries)
    data = canonical(entries)
    if len(data) > MAX_JSON:
        raise ArchiveError('Manifest exceeds 16 MiB')
    with output.open('xb') as out:
        out.write(MAGIC + U64.pack(len(data)) + data)
        for e in entries:
            if e['kind'] == 'file':
                h = new_hash()
                with open_regular(source / e['path']) as f:
                    copy_n(f, out, e['size'], h)
                    if f.read(1) or h.hexdigest() != e['blake3']:
                        raise ArchiveError(f'Source changed during snapshot: {e["path"]}')
    return entries


def extract(stream_path: Path, destination: Path, max_bytes: int):
    with stream_path.open('rb') as src:
        if exact(src, len(MAGIC)) != MAGIC:
            raise ArchiveError('Invalid directory stream magic')
        length = U64.unpack(exact(src, 8))[0]
        if length > MAX_JSON:
            raise ArchiveError('Manifest exceeds 16 MiB')
        try:
            entries = validate(json.loads(exact(src, length)))
        except (ValueError, UnicodeError, TypeError, KeyError) as exc:
            raise ArchiveError('Invalid manifest JSON') from exc
        if sum(e['size'] for e in entries) > max_bytes:
            raise ArchiveError('Directory exceeds extraction size limit')
        for e in entries:
            path = destination / e['path']
            if e['kind'] == 'dir':
                path.mkdir(mode=0o700)
            else:
                h = new_hash()
                with path.open('xb') as out:
                    copy_n(src, out, e['size'], h)
                if h.hexdigest() != e['blake3']:
                    raise ArchiveError(f'BLAKE3 file check failed: {e["path"]}')
                os.chmod(path, e['mode'])
        if src.read(1):
            raise ArchiveError('Unexpected trailing directory bytes')
        for e in reversed(entries):
            if e['kind'] == 'dir':
                os.chmod(destination / e['path'], e['mode'])
    return entries
