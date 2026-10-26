"""Discover build-script outputs only when their recorded file identities still match."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .common import ArchiveError

PINS = {
    'exdupe': ('https://github.com/rrrlasse/eXdupe.git', '27e03c8687fd0dfd12ff21acaea249eada22e478'),
    'openzl': ('https://github.com/facebook/openzl.git', '32246b48faee46807f84183dac4db479089f5445'),
}


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as src:
        while data := src.read(1024 * 1024):
            h.update(data)
    return h.hexdigest()


def discover(tools):
    root = tools.exdupe.parent.parent
    metadata = root / 'toolchain.json'
    if tools.zli.parent != tools.exdupe.parent or not metadata.is_file():
        raise ArchiveError('SFX notices not found: run scripts/build_tools.py or pass --notice and --source-archive')
    try:
        with metadata.open('rb') as src:
            raw = src.read(65537)
        if len(raw) > 65536:
            raise ValueError('metadata too large')
        info = json.loads(raw)
        if info['pins'] != {k: list(v) for k, v in PINS.items()}:
            raise ValueError('unexpected source provenance')
        paths = {'exdupe': tools.exdupe, 'zli': tools.zli,
                 'notice': root / 'CODEC-NOTICE.txt', 'sources': root / 'codec-sources.tar.gz'}
        if any(sha256(path) != info['sha256'][key] for key, path in paths.items()):
            raise ValueError('build outputs changed')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArchiveError(f'Codec build metadata invalid: {exc}; rebuild tools or pass explicit --notice files') from exc
    return [paths['notice']], [paths['sources']]
