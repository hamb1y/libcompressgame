from pathlib import Path

import pytest

from libcompressgame import envelope
from libcompressgame.common import ArchiveError, CHUNK


def metadata(size):
    return dict(directory_bytes=size, exdupe_bytes=size,
                tools={'exdupe': '0' * 64, 'zli': '1' * 64},
                chain=['exdupe-3', 'openzl-serial-chunks-v1'])


@pytest.mark.parametrize('size', [0, 1, CHUNK, CHUNK + 17])
@pytest.mark.parametrize('password', [None, b'an explicit password'])
def test_roundtrip(tmp_path, size, password):
    raw, archive, decoded = [tmp_path / p for p in ('raw', 'archive', 'decoded')]
    raw.write_bytes((b'abcdefg' * (size // 7 + 1))[:size])
    header = envelope.write(raw, archive, metadata(size), password)
    assert envelope.unwrap(archive, decoded, password, 10**8) == header
    assert decoded.read_bytes() == raw.read_bytes()
    if password is not None:
        assert password not in archive.read_bytes()


@pytest.mark.parametrize('encrypted', [False, True])
@pytest.mark.parametrize('damage', ['flip', 'truncate', 'append'])
def test_damage(tmp_path, encrypted, damage):
    raw, archive = tmp_path / 'raw', tmp_path / 'archive'
    raw.write_bytes(b'game contents' * 100)
    password = b'secret' if encrypted else None
    envelope.write(raw, archive, metadata(raw.stat().st_size), password)
    data = bytearray(archive.read_bytes())
    if damage == 'flip':
        data[-1] ^= 1
    elif damage == 'truncate':
        del data[-17:]
    else:
        data.extend(b'junk')
    archive.write_bytes(data)
    with pytest.raises(ArchiveError):
        envelope.unwrap(archive, tmp_path / 'out', password, 10**8)


def test_wrong_password_and_size_limit(tmp_path):
    raw, archive = tmp_path / 'raw', tmp_path / 'archive'
    raw.write_bytes(b'game' * 100)
    envelope.write(raw, archive, metadata(400), b'correct')
    with pytest.raises(ArchiveError, match='Wrong password'):
        envelope.unwrap(archive, tmp_path / 'bad', b'incorrect', 10**8)
    with pytest.raises(ArchiveError, match='limit'):
        envelope.unwrap(archive, tmp_path / 'big', b'correct', 1)
