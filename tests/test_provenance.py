import json
from pathlib import Path

import pytest

from libcompressgame.codecs import Tools
from libcompressgame.common import ArchiveError
from libcompressgame.provenance import PINS, discover, sha256


def test_discovery_checks_all_build_identities(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    paths = {'exdupe': bindir / 'exdupe', 'zli': bindir / 'zli',
             'notice': tmp_path / 'CODEC-NOTICE.txt', 'sources': tmp_path / 'codec-sources.tar.gz'}
    # Identity-only test data; these files are never executed as codecs.
    for name, path in paths.items():
        path.write_bytes(name.encode())
    (tmp_path / 'toolchain.json').write_text(json.dumps({'pins': PINS,
        'sha256': {name: sha256(path) for name, path in paths.items()}}))
    tools = Tools(paths['exdupe'], paths['zli'])
    assert discover(tools) == ([paths['notice']], [paths['sources']])
    paths['notice'].write_bytes(b'changed')
    with pytest.raises(ArchiveError, match='changed'):
        discover(tools)


def test_missing_provenance_requires_explicit_notices(tmp_path):
    with pytest.raises(ArchiveError, match='--notice'):
        discover(Tools(tmp_path / 'bin/exdupe', tmp_path / 'bin/zli'))
