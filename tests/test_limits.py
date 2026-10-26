import os
from pathlib import Path
import sys

import pytest

from libcompressgame.codecs import run
from libcompressgame.common import ArchiveError


def test_subprocess_output_limit(tmp_path):
    output = tmp_path / 'output'
    with pytest.raises(ArchiveError, match='limit'):
        run([sys.executable, '-c', 'import sys; sys.stdout.buffer.write(b"x"*2000000)'],
            output, 1024, stdout=True)
    assert not output.with_suffix('.log').exists()


def test_subprocess_failure_details(tmp_path):
    with pytest.raises(ArchiveError, match='codec failed deliberately'):
        run([sys.executable, '-c', 'import sys; print("codec failed deliberately",file=sys.stderr);sys.exit(9)'],
            tmp_path / 'output', 1024, stdout=True)


def test_subprocess_timeout(tmp_path):
    with pytest.raises(ArchiveError, match='time limit'):
        run([sys.executable, '-c', 'import time;time.sleep(10)'], tmp_path / 'output',
            1024, stdout=True, timeout=0.05)


def test_subprocess_memory_limit(tmp_path):
    with pytest.raises(ArchiveError):
        run([sys.executable, '-c', 'data=bytearray(1024**3)'], tmp_path / 'output',
            1024, stdout=True, memory_bytes=256 * 1024**2)
