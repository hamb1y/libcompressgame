from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct

CHUNK = 1024 * 1024
MAX_JSON = 16 * CHUNK
U64 = struct.Struct('<Q')


class ArchiveError(Exception):
    """Invalid archive, unavailable dependency, or unsupported input."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def exact(stream, size: int) -> bytes:
    value = stream.read(size)
    if len(value) != size:
        raise ArchiveError('Truncated archive')
    return value


def copy_n(src, dst, size: int, hasher=None):
    while size:
        data = exact(src, min(size, CHUNK))
        dst.write(data)
        if hasher is not None:
            hasher.update(data)
        size -= len(data)


def new_hash():
    try:
        from blake3 import blake3
    except ImportError as exc:
        raise ArchiveError('BLAKE3 dependency missing: install libcompressgame with pip') from exc
    return blake3()


def file_hash(path: Path) -> str:
    h = new_hash()
    with path.open('rb') as f:
        while data := f.read(CHUNK):
            h.update(data)
    return h.hexdigest()


def atomic_file(source: Path, output: Path, mode=0o644):
    """Publish a complete file without replacing an existing output."""
    # source is always created alongside output, so hard-link publication is atomic.
    os.chmod(source, mode)
    try:
        os.link(source, output)
    except FileExistsError as exc:
        raise ArchiveError(f'Output already exists: {output}') from exc
    except OSError as exc:
        raise ArchiveError(f'Cannot publish output atomically: {exc}') from exc


def no_output_in_source(source: Path, output: Path):
    if output == source or source in output.parents:
        raise ArchiveError('Output must be outside the source directory')


def absent(path: Path):
    if path.exists() or path.is_symlink():
        raise ArchiveError(f'Output already exists: {path}')
    if not path.parent.is_dir():
        raise ArchiveError(f'Output parent directory does not exist: {path.parent}')
