#!/usr/bin/env python3
"""Build pinned genuine codec sources; no replacement algorithms or remote script execution."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from libcompressgame.provenance import PINS, sha256

def run(args, cwd=None):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run([str(x) for x in args], cwd=cwd, check=True)


def checkout(name, destination):
    url, commit = PINS[name]
    if destination.exists():
        current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=destination, text=True).strip()
        if current != commit:
            raise RuntimeError(f'{destination} is at {current}; expected {commit}; use a fresh directory')
    else:
        destination.mkdir(parents=True)
        run(['git', 'init', '--quiet', destination])
        run(['git', 'remote', 'add', 'origin', url], destination)
        run(['git', 'fetch', '--depth', '1', 'origin', commit], destination)
        run(['git', 'checkout', '--detach', 'FETCH_HEAD'], destination)
    run(['git', 'submodule', 'update', '--init', '--recursive', '--depth', '1'], destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('tools'))
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    windows = sys.platform == 'win32'
    for name in PINS:
        checkout(name, root / 'source' / name)
    exdupe_source = root / 'source' / 'exdupe'
    openzl_source = root / 'source' / 'openzl'
    # zli's CMake currently enables an unrelated XGBoost trainer unconditionally.
    # Disable that optional tool; serial compression and the universal decoder are unchanged.
    tools_cmake = openzl_source / 'tools' / 'CMakeLists.txt'
    original = subprocess.check_output(['git', 'show', PINS['openzl'][1] + ':tools/CMakeLists.txt'],
                                       cwd=openzl_source, text=True)
    if original.count('set(OPENZL_BUILD_ML_SELECTOR ON)') != 2:
        raise RuntimeError('Pinned OpenZL optional-trainer build contract changed')
    tools_cmake.write_text(original.replace('set(OPENZL_BUILD_ML_SELECTOR ON)',
                                           'set(OPENZL_BUILD_ML_SELECTOR OFF)'), encoding='utf-8')
    exdupe_build, openzl_build = root / 'build' / 'exdupe', root / 'build' / 'openzl'
    # eXdupe's C++20 build uses MSVC on Windows. OpenZL recommends clang-cl.
    exdupe_flags = ['-G', 'Visual Studio 17 2022', '-A', 'x64'] if windows else []
    openzl_flags = ['-G', 'Visual Studio 17 2022', '-A', 'x64', '-T', 'ClangCL'] if windows else []
    run(['cmake', '-S', exdupe_source / 'src', '-B', exdupe_build,
         '-DCMAKE_BUILD_TYPE=Release', *exdupe_flags])
    run(['cmake', '--build', exdupe_build, '--config', 'Release', '--target', 'exdupe',
         '--parallel', args.jobs])
    run(['cmake', '-S', openzl_source, '-B', openzl_build, '-DCMAKE_BUILD_TYPE=Release',
         '-DOPENZL_BUILD_TESTS=OFF', '-DOPENZL_BUILD_EXAMPLES=OFF', '-DOPENZL_BUILD_BENCHMARKS=OFF',
         '-DOPENZL_BUILD_PYTHON_EXT=OFF', '-DOPENZL_BUILD_SHARED_LIBS=OFF',
         '-DOPENZL_BUILD_PARQUET_TOOLS=OFF', *openzl_flags])
    run(['cmake', '--build', openzl_build, '--config', 'Release', '--target', 'zli',
         '--parallel', args.jobs])
    suffix = '.exe' if windows else ''
    binary_dir = root / 'bin'
    binary_dir.mkdir(exist_ok=True)
    for name, search in [('exdupe', root / 'build'), ('zli', openzl_build)]:
        matches = list(search.rglob(name + suffix))
        matches = [p for p in matches if p.is_file() and not p.is_symlink()]
        if not matches:
            raise RuntimeError(f'Built {name} executable not found under {search}')
        shutil.copy2(matches[0], binary_dir / (name + suffix))
    # Preserve complete source, including submodules and license files, alongside binaries.
    sources = root / 'codec-sources.tar.gz'
    with tarfile.open(sources, 'w:gz') as archive:
        archive.add(root / 'source', arcname='codec-sources',
                    filter=lambda t: None if '.git' in Path(t.name).parts else t)
        for path in (root / 'build').rglob('*-src'):
            if path.is_dir() and not any(p.name.endswith('-src') for p in path.parents):
                archive.add(path, arcname='build-dependencies/' + str(path.relative_to(root / 'build')),
                            filter=lambda t: None if '.git' in Path(t.name).parts else t)
    notice = root / 'CODEC-NOTICE.txt'
    notice.write_text(
        'This self-extractor includes eXdupe 3.0.2 (GPL-2.0-or-later) and OpenZL 0.3.0 (BSD-3-Clause).\n'
        'Exact corresponding codec sources and their dependency licenses are bundled in codec-sources.tar.gz.\n'
        'Build adaptation: the unused optional OpenZL XGBoost trainer is disabled; serial compression/decoding is unchanged.\n'
        'Use --export-sources DIRECTORY to obtain them.\n'
        'Upstream provenance:\n' + '\n'.join(f'{k}: {url} at {sha}' for k, (url, sha) in PINS.items()) + '\n',
        encoding='utf-8')
    (root / 'pins.json').write_text(json.dumps(PINS, indent=2) + '\n', encoding='utf-8')
    identities = {'exdupe': sha256(binary_dir / ('exdupe' + suffix)),
                  'zli': sha256(binary_dir / ('zli' + suffix)),
                  'notice': sha256(notice), 'sources': sha256(sources)}
    (root / 'toolchain.json').write_text(json.dumps({'pins': PINS, 'sha256': identities}, indent=2) + '\n',
                                      encoding='utf-8')
    print(f'Codec tools: {binary_dir}\nNotices: {notice}\nCorresponding sources: {sources}')


if __name__ == '__main__':
    main()
