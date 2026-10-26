import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from libcompressgame.archive import pack, unpack
from libcompressgame.codecs import Tools
from libcompressgame.common import ArchiveError
from libcompressgame import sfx
from test_manifest import fixture_game


@pytest.fixture
def tools():
    if not os.environ.get('LCG_EXDUPE') or not os.environ.get('LCG_ZLI'):
        pytest.skip('Set LCG_EXDUPE and LCG_ZLI to genuine pinned native codec executables')
    tools = Tools.find(os.environ['LCG_EXDUPE'], os.environ['LCG_ZLI'])
    tools.check()
    return tools


@pytest.mark.integration
@pytest.mark.parametrize('password', [None, b'real encrypted game'])
def test_real_codecs(tmp_path, tools, password):
    game = fixture_game(tmp_path / 'game')
    archive, out = tmp_path / 'game.lcg', tmp_path / 'restored'
    header = pack(game, archive, tools, password=password, memory_mb=64)
    print(json.dumps({key: header[key] for key in ['directory_bytes', 'exdupe_bytes', 'payload_bytes', 'archive_bytes']}))
    unpack(archive, out, tools, password=password)
    assert (out / 'nested' / 'data.bin').read_bytes() == (game / 'nested' / 'data.bin').read_bytes()
    assert (out / 'empty').is_dir()
    with pytest.raises(ArchiveError, match='exists'):
        unpack(archive, out, tools, password=password)
    if password:
        with pytest.raises(ArchiveError, match='Wrong password'):
            unpack(archive, tmp_path / 'wrong', tools, password=b'wrong')
        assert not (tmp_path / 'wrong').exists()
    data = bytearray(archive.read_bytes())
    data[-1] ^= 1
    archive.write_bytes(data)
    with pytest.raises(ArchiveError):
        unpack(archive, tmp_path / 'damaged', tools, password=password)
    assert not (tmp_path / 'damaged').exists()
    assert not list(tmp_path.glob('.lcg-extract-*'))


@pytest.mark.integration
def test_empty_game(tmp_path, tools):
    root = tmp_path / 'empty'
    root.mkdir()
    archive = tmp_path / 'empty.lcg'
    pack(root, archive, tools, memory_mb=64)
    unpack(archive, tmp_path / 'out', tools)
    assert list((tmp_path / 'out').iterdir()) == []


@pytest.mark.integration
@pytest.mark.sfx
@pytest.mark.parametrize('password', [None, b'sfx secret'])
def test_native_sfx(tmp_path, tools, password):
    if os.environ.get('LCG_TEST_SFX') != '1':
        pytest.skip('Set LCG_TEST_SFX=1 to run native PyInstaller builds')
    game = fixture_game(tmp_path / 'game')
    archive = tmp_path / 'game.lcg'
    pack(game, archive, tools, memory_mb=64, password=password)
    output = tmp_path / ('setup.exe' if sys.platform == 'win32' else 'setup')
    notice = tmp_path / 'NOTICE.txt'
    notice.write_text('Test-only binary; not for redistribution. Source build provenance in CI.\n')
    source_file = Path(__file__).resolve().parents[1] / 'src/libcompressgame/manifest.py'
    sfx.build(archive, output, tools, [notice], [source_file])
    signature = output.read_bytes()[:4]
    assert signature[:2] == b'MZ' if sys.platform == 'win32' else signature == b'\x7fELF'
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    # Extraction must use bundled tools with no compiler or Python installation on PATH.
    env['PATH'] = str(tmp_path)
    args = [str(output), str(tmp_path / 'restored')]
    if password:
        password_path = tmp_path / 'password'
        password_path.write_bytes(password)
        args.extend(['--password-file', str(password_path)])
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'restored' / 'nested' / 'data.bin').read_bytes() == (game / 'nested' / 'data.bin').read_bytes()
    info = subprocess.run([str(output), '--info'], env=env, capture_output=True, text=True, timeout=60)
    assert info.returncode == 0, info.stderr
    assert json.loads(info.stdout)['chain'] == ['exdupe-3', 'openzl-serial-chunks-v1']
    verify_args = [str(output), '--verify']
    if password:
        verify_args.extend(['--password-file', str(password_path)])
        wrong = tmp_path / 'wrong-password'
        wrong.write_bytes(b'wrong')
        rejected = subprocess.run([str(output), str(tmp_path / 'wrong-out'), '--password-file', str(wrong)],
                                  env=env, capture_output=True, text=True, timeout=60)
        assert rejected.returncode == 2
        assert 'Wrong password' in rejected.stderr
        assert not (tmp_path / 'wrong-out').exists()
    verified = subprocess.run(verify_args, env=env, capture_output=True, text=True, timeout=60)
    assert verified.returncode == 0, verified.stderr
    licenses = subprocess.run([str(output), '--licenses'], env=env, capture_output=True, text=True, timeout=60)
    assert licenses.returncode == 0
    assert 'Test-only binary' in licenses.stdout
    exported = tmp_path / 'sources'
    result = subprocess.run([str(output), '--export-sources', str(exported)],
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert (exported / source_file.name).read_bytes() == source_file.read_bytes()


@pytest.mark.integration
def test_multiple_openzl_frames(tmp_path, tools):
    import random
    game = tmp_path / 'game'
    game.mkdir()
    data = random.Random(20261025).randbytes(17 * 1024 * 1024)
    (game / 'large.bin').write_bytes(data)
    archive = tmp_path / 'large.lcg'
    header = pack(game, archive, tools, memory_mb=64)
    print(json.dumps({key: header[key] for key in ['directory_bytes', 'exdupe_bytes', 'payload_bytes', 'archive_bytes']}))
    assert header['exdupe_bytes'] > 16 * 1024 * 1024
    unpack(archive, tmp_path / 'out', tools)
    assert (tmp_path / 'out' / 'large.bin').read_bytes() == data


@pytest.mark.integration
def test_reject_native_metadata_before_restore(tmp_path, tools):
    from libcompressgame.exdupe_format import check_stdin_archive
    src = tmp_path / 'input'
    src.write_bytes(b'actual stdin payload')
    native = tmp_path / 'native.exd'
    with src.open('rb') as stream:
        subprocess.run([str(tools.exdupe), '-v0', '-m64', '-t2', '-x1', '-z', '-stdin', str(native)],
                       stdin=stream, check=True)
    check_stdin_archive(native, src.stat().st_size)
    original = native.read_bytes()
    contents = original.rfind(b'CONTENTS') + 8
    assert contents > 8
    for flag in [1, 2, 4, 8, 16, 32, 128]:
        changed = bytearray(original)
        changed[contents + 8] = flag
        native.write_bytes(changed)
        with pytest.raises(ArchiveError):
            check_stdin_archive(native, src.stat().st_size)
    changed = bytearray(original)
    changed[contents:contents + 8] = (2).to_bytes(8, 'little')
    native.write_bytes(changed)
    with pytest.raises(ArchiveError, match='exactly one'):
        check_stdin_archive(native, src.stat().st_size)
    changed = bytearray(original)
    name = changed.index(b'stdin', contents)
    changed[name:name + 5] = b'../..'
    native.write_bytes(changed)
    with pytest.raises(ArchiveError, match='metadata'):
        check_stdin_archive(native, src.stat().st_size)


@pytest.mark.integration
@pytest.mark.parametrize('kind', ['directory', 'symlink', 'named_file'])
def test_refuse_genuine_non_stdin_archives(tmp_path, tools, kind):
    from libcompressgame.exdupe_format import check_stdin_archive
    source = tmp_path / 'source'
    if kind == 'directory':
        source.mkdir()
        (source / 'nested').mkdir()
    elif kind == 'symlink':
        if os.name == 'nt':
            pytest.skip('Creating symlinks on Windows requires Developer Mode or privilege')
        source.symlink_to('target-outside')
    else:
        source.write_bytes(b'ordinary named file')
    archive = tmp_path / 'non-stdin.exd'
    subprocess.run([str(tools.exdupe), '-v0', '-m64', '-t2', '-x1', '-z', str(source), str(archive)],
                   check=True)
    with pytest.raises(ArchiveError):
        check_stdin_archive(archive, 0)
    assert not (tmp_path / 'target-outside').exists()
