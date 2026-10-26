from pathlib import Path
import os
import subprocess
import sys

from libcompressgame.cli import main
from libcompressgame.archive import publish_directory
from libcompressgame.common import ArchiveError
import pytest


def test_help_and_missing_dependency(capsys):
    assert main(['doctor', '--exdupe', '/definitely/missing']) == 2
    assert 'exdupe executable missing' in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        main(['--help'])
    assert exc.value.code == 0


def test_atomic_publication_never_replaces(tmp_path):
    source, out = tmp_path / 'source', tmp_path / 'out'
    source.mkdir()
    out.mkdir()
    with pytest.raises((ArchiveError, OSError)):
        publish_directory(source, out)
    assert source.is_dir()
    assert out.is_dir()


def test_redirected_help_with_windows_legacy_encoding():
    env = dict(os.environ, PYTHONIOENCODING='cp1252')
    for command in [[], ['pack'], ['unpack'], ['verify'], ['info'], ['doctor']]:
        result = subprocess.run([sys.executable, '-m', 'libcompressgame', *command, '--help'],
                                env=env, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr.decode('cp1252', errors='replace')
        assert b'usage:' in result.stdout
        assert b'UnicodeEncodeError' not in result.stderr
