"""Narrow eXdupe 3.0.2 stdin-archive validation before invoking its native restore.

The upstream -stdout path still creates symlink/directory metadata entries. Only
its exact single ordinary stdin-file form is accepted here, so those branches
are unreachable. This is a format adapter, not an eXdupe implementation.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from .common import ArchiveError, U64, exact


def compact(src):
    value = 0
    for i in range(10):
        byte = exact(src, 1)[0]
        if i == 9 and byte > 1:
            raise ArchiveError('Invalid eXdupe compact integer')
        value |= (byte & 127) << (7 * i)
        if byte < 128:
            if i and byte == 0:
                raise ArchiveError('Noncanonical eXdupe compact integer')
            return value
    raise ArchiveError('Invalid eXdupe compact integer')


def string(src):
    size = compact(src)
    if size > 1024:
        raise ArchiveError('Unexpected eXdupe metadata string')
    return exact(src, size)


def check_stdin_archive(path: Path, expected_size: int):
    with path.open('rb') as src:
        if exact(src, 12) != b'EXDUPE F\x03\x00\x02\x00':
            raise ArchiveError('Expected stable eXdupe 3.0.2 full archive')
        size = path.stat().st_size
        if size < 32:
            raise ArchiveError('Truncated eXdupe archive')
        src.seek(size - 3)
        if exact(src, 3) != b'END':
            raise ArchiveError('Invalid eXdupe archive footer')
        end = size - 3
        for section in [b'REFERENC', b'HASHTBLE', b'CONTENTS']:
            if end < 16:
                raise ArchiveError('Invalid eXdupe section bounds')
            src.seek(end - 8)
            length = U64.unpack(exact(src, 8))[0]
            start = end - 16 - length
            if start < 12:
                raise ArchiveError('Invalid eXdupe section bounds')
            src.seek(start)
            if exact(src, 8) != section:
                raise ArchiveError('Unexpected eXdupe footer section')
            if section == b'CONTENTS':
                if length > 4096:
                    raise ArchiveError('Unexpected eXdupe file metadata')
                contents = io.BytesIO(exact(src, length))
            end = start
        if U64.unpack(exact(contents, 8))[0] != 1:
            raise ArchiveError('eXdupe archive must contain exactly one stdin file')
        kind = exact(contents, 1)[0]
        if kind not in (0, 64):  # only platform bit; no directories, links, or diff flags
            raise ArchiveError('eXdupe directories, links and differential entries are forbidden')
        file_id = compact(contents)
        absolute = string(contents)
        payload = compact(contents)
        name, link = string(contents), string(contents)
        decoded_size = compact(contents)
        # Windows _wfullpath('-stdin') returns an absolute provenance string even
        # when that path does not exist. restore_from_file never uses abs_path.
        normalized = absolute.replace(b'\\', b'/')
        windows_provenance = (kind == 64 and
            re.fullmatch(rb'(?:[A-Za-z]:/|//[^/:]+/[^/:]+/)(?:[^/:\x00]+/)*-stdin', normalized) and
            all(part not in (b'.', b'..') for part in normalized.split(b'/')) and
            all(byte >= 32 for byte in absolute))
        if file_id != 0 or (absolute and not windows_provenance) or payload != 0 or name != b'stdin' or link or decoded_size != expected_size:
            raise ArchiveError('Unexpected eXdupe stdin-file metadata')
        exact(contents, 4)  # data checksum; native decoder also validates it
        compact(contents)  # ctime
        compact(contents)  # mtime
        exact(contents, 4)  # attributes are never applied in the permitted stdout path
        if compact(contents) != 0:
            raise ArchiveError('Unexpected eXdupe duplicate-file metadata')
        hash_size = compact(contents)
        if hash_size not in (0, 16, 32):
            raise ArchiveError('Unexpected eXdupe file hash size')
        exact(contents, hash_size)
        if hash_size:
            exact(contents, 16)
        if exact(contents, 4) != b'\0' * 4 or contents.read(1):
            raise ArchiveError('Unexpected trailing eXdupe contents metadata')
