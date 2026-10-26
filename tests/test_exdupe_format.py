"""Pinned wire-format fixtures for platform metadata; no fabricated codec results."""
import pytest

from libcompressgame.common import ArchiveError, U64
from libcompressgame.exdupe_format import check_stdin_archive


def fixture(kind, absolute):
    assert len(absolute) < 128
    # Single-file 3.0.2 CONTENTS record, using documented native compact integers.
    entry = (bytes([kind, 0, len(absolute)]) + absolute + b'\0\x05stdin\0\0' +
             b'\0' * 4 + b'\0\0' + b'\0' * 4 + b'\0\0')
    def section(name, data):
        return name + data + U64.pack(len(data))
    return (b'EXDUPE F\x03\x00\x02\x00' + b'\0' * 50 +
            section(b'CONTENTS', U64.pack(1) + entry + b'\0' * 4) +
            section(b'HASHTBLE', U64.pack(0)) + section(b'REFERENC', U64.pack(0)) + b'END')


@pytest.mark.parametrize('path', [b'C:\\work\\-stdin', b'C:/work/-stdin', b'\\\\server\\share\\work\\-stdin'])
def test_windows_absolute_provenance_only_under_windows_flag(tmp_path, path):
    native = tmp_path / 'metadata.exd'
    native.write_bytes(fixture(64, path))
    check_stdin_archive(native, 0)
    native.write_bytes(fixture(0, path))
    with pytest.raises(ArchiveError):
        check_stdin_archive(native, 0)


@pytest.mark.parametrize('path', [b'/tmp/-stdin', b'C:/work/../-stdin', b'C:/work/not-stdin', b'C:/work/\x00-stdin'])
def test_windows_provenance_shape_is_strict(tmp_path, path):
    native = tmp_path / 'metadata.exd'
    native.write_bytes(fixture(64, path))
    with pytest.raises(ArchiveError):
        check_stdin_archive(native, 0)
