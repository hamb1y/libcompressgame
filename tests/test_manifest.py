import io
import json
import os
from pathlib import Path

import pytest

from libcompressgame.common import ArchiveError, U64, canonical
from libcompressgame import manifest


def fixture_game(root):
    root.mkdir()
    (root / 'empty').mkdir()
    (root / 'nested').mkdir()
    (root / 'nested' / '零 bytes.txt').write_bytes(b'')
    (root / 'nested' / 'data.bin').write_bytes(bytes(range(256)) * 8193)
    (root / 'launch.sh').write_bytes(b'#!/bin/sh\necho game\n')
    os.chmod(root / 'launch.sh', 0o755)
    return root


def test_deterministic_manifest_and_roundtrip(tmp_path):
    game = fixture_game(tmp_path / 'game')
    a, b = tmp_path / 'a', tmp_path / 'b'
    entries = manifest.build(game, a)
    manifest.build(game, b)
    assert a.read_bytes() == b.read_bytes()
    out = tmp_path / 'out'
    out.mkdir()
    assert manifest.extract(a, out, 10**8) == entries
    for item in entries:
        if item['kind'] == 'file':
            assert (out / item['path']).read_bytes() == (game / item['path']).read_bytes()
    if os.name != 'nt':
        assert (out / 'launch.sh').stat().st_mode & 0o777 == 0o755
    assert (out / 'empty').is_dir()


@pytest.mark.parametrize('path', ['../escape', '/root', 'a//b', 'a/./b', 'a/../b',
                                  'C:/file', 'a\\b', 'CON', 'aux.txt', 'file.', 'a\x00b'])
def test_unsafe_paths(path):
    with pytest.raises(ArchiveError):
        manifest.safe_path(path)


def test_reject_case_collision_and_links(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'A').write_bytes(b'a')
    if os.name != 'nt':
        (root / 'a').write_bytes(b'b')
        with pytest.raises(ArchiveError, match='colliding'):
            manifest.build(root, tmp_path / 'stream')
        (root / 'a').unlink()
        (root / 'link').symlink_to(root / 'A')
        with pytest.raises(ArchiveError, match='Symlinks'):
            manifest.build(root, tmp_path / 'stream')


def test_tampered_file_and_limits(tmp_path):
    root = fixture_game(tmp_path / 'root')
    stream = tmp_path / 'stream'
    manifest.build(root, stream)
    out = tmp_path / 'out'
    out.mkdir()
    with pytest.raises(ArchiveError, match='limit'):
        manifest.extract(stream, out, 1)
    data = bytearray(stream.read_bytes())
    data[-1] ^= 1
    stream.write_bytes(data)
    with pytest.raises(ArchiveError, match='BLAKE3'):
        manifest.extract(stream, out, 10**8)


def test_file_as_parent_and_privileged_modes():
    file = dict(path='a', kind='file', mode=0o644, size=0, blake3='0' * 64)
    with pytest.raises(ArchiveError, match='parent'):
        manifest.validate([file, dict(file, path='a/b')])
    with pytest.raises(ArchiveError, match='mode'):
        manifest.validate([dict(file, mode=0o4755)])
