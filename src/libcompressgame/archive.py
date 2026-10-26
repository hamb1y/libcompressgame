from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import sys
import tempfile

from . import codecs, envelope, manifest
from .common import ArchiveError, absent, atomic_file, no_output_in_source

DEFAULT_LIMIT = 1024**4  # explicit default: 1 TiB per intermediate stage


def pack(source, output, tools: codecs.Tools, *, password=None, memory_mb=256, threads=2):
    source, output = Path(source).absolute(), Path(output).absolute()
    absent(output)
    no_output_in_source(source.resolve(), output.resolve())
    if not 16 <= memory_mb <= 65536 or not 1 <= threads <= 64:
        raise ArchiveError('Memory must be 16..65536 MiB and threads 1..64')
    identities = tools.check()
    with tempfile.TemporaryDirectory(prefix='.lcg-pack-', dir=output.parent) as temp:
        work = Path(temp)
        directory, payload, ready = work / 'directory.dat', work / 'payload.bin', work / 'ready.lcg'
        entries = manifest.build(source, directory)
        exdupe_size = codecs.encode(directory, payload, tools, memory_mb, threads)
        metadata = dict(chain=['exdupe-3', 'openzl-serial-chunks-v1'],
                        directory_bytes=directory.stat().st_size, exdupe_bytes=exdupe_size,
                        tools=identities)
        header = envelope.write(payload, ready, metadata, password)
        atomic_file(ready, output)
    return dict(header, entries=len(entries), archive_bytes=output.stat().st_size)


def publish_directory(source: Path, destination: Path):
    """Atomic no-replace rename on both supported platforms."""
    if sys.platform == 'win32':
        os.rename(source, destination)  # Windows fails if destination already exists.
    elif sys.platform.startswith('linux'):
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            rename = libc.renameat2
        except AttributeError as exc:
            raise ArchiveError('Atomic directory publication requires Linux renameat2') from exc
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
            err = ctypes.get_errno()
            raise ArchiveError(f'Cannot publish destination: {os.strerror(err)}')
    else:
        raise ArchiveError('Directory extraction currently supports Linux and Windows')


def unpack(archive, destination, tools: codecs.Tools, *, password=None, max_bytes=DEFAULT_LIMIT,
           verify_only=False):
    archive = Path(archive).absolute()
    destination = Path(destination).absolute()
    if max_bytes < 1:
        raise ArchiveError('Extraction limit must be positive')
    if not verify_only:
        absent(destination)
    tools.check()
    with tempfile.TemporaryDirectory(prefix='.lcg-extract-', dir=destination.parent) as temp:
        work = Path(temp)
        payload, directory, stage = work / 'payload.bin', work / 'directory.dat', work / 'game'
        header = envelope.unwrap(archive, payload, password, max_bytes)
        codecs.decode(payload, directory, tools, header)
        stage.mkdir(mode=0o700)
        entries = manifest.extract(directory, stage, max_bytes)
        if not verify_only:
            publish_directory(stage, destination)
    return dict(header, entries=len(entries))
