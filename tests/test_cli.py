from pathlib import Path
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
