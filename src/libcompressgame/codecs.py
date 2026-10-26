from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import time

from .common import ArchiveError, U64, copy_n, exact, file_hash
from .limits import WindowsMemoryJob, spawn_options
from .exdupe_format import check_stdin_archive

# Explicit chunking bounds OpenZL memory even on versions without automatic chunking.
BLOCK = 16 * 1024 * 1024
MAGIC = b'LCGZL1\0\0'


@dataclass(frozen=True)
class Tools:
    exdupe: Path
    zli: Path

    @classmethod
    def find(cls, exdupe=None, zli=None):
        def find_one(value, name):
            result = shutil.which(str(value or name))
            if result is None and value is None:
                local = Path('tools/bin') / (name + ('.exe' if os.name == 'nt' else ''))
                if local.is_file():
                    result = shutil.which(str(local.resolve()))
            if result is None:
                raise ArchiveError(f'{name} executable missing; pass --{name} /path/to/{name}')
            return Path(result).resolve()
        return cls(find_one(exdupe, 'exdupe'), find_one(zli, 'zli'))

    def hashes(self):
        return {'exdupe': file_hash(self.exdupe), 'zli': file_hash(self.zli)}

    def check(self):
        # 3.x frame contract is intentionally pinned. Other majors need a new format adapter.
        result = subprocess.run([str(self.exdupe), '-B'], capture_output=True, timeout=30)
        if result.returncode or b'3.0.2' not in result.stdout + result.stderr:
            raise ArchiveError('eXdupe 3.0.2 required; install the pinned upstream release')
        result = subprocess.run([str(self.zli), '--version'], capture_output=True, timeout=30)
        if result.returncode or b'0.3.0' not in result.stdout + result.stderr:
            raise ArchiveError('OpenZL zli 0.3.0 required; build the pinned upstream release')
        return self.hashes()


def run(args, output: Path, limit: int, *, stdin=None, stdout=False, timeout=3600, memory_bytes=2 * 1024**3):
    """Never invoke a shell. Keep logs on disk and cap decoded output while running."""
    log = output.with_name(output.name + '.log')
    src = stdin.open('rb') if stdin is not None else subprocess.DEVNULL
    dst = output.open('xb') if stdout else subprocess.DEVNULL
    try:
        with log.open('wb') as err:
            try:
                with subprocess.Popen([str(x) for x in args], stdin=src, stdout=dst, stderr=err,
                                      cwd=output.parent,
                                      **spawn_options(memory_bytes)) as process:
                    try:
                        job = WindowsMemoryJob(process, memory_bytes)
                    except ArchiveError:
                        process.kill()
                        process.wait()
                        raise
                    start = time.monotonic()
                    try:
                        while process.poll() is None:
                            if ((output.exists() and output.stat().st_size > limit) or
                                    log.stat().st_size > 1024 * 1024 or time.monotonic() - start > timeout):
                                process.kill()
                                process.wait()
                                raise ArchiveError('Codec exceeded output, log, or time limit')
                            time.sleep(0.02)
                        if process.returncode:
                            with log.open('rb') as details:
                                details.seek(max(0, log.stat().st_size - 2000))
                                detail = details.read(2000).decode('utf-8', errors='replace')
                            raise ArchiveError(f'{Path(args[0]).name} failed ({process.returncode}): {detail}')
                    finally:
                        job.close()
            except OSError as exc:
                raise ArchiveError(f'Cannot execute codec: {exc}') from exc
        if not output.is_file() or output.stat().st_size > limit:
            raise ArchiveError('Codec produced no output or exceeded output limit')
    finally:
        if stdin is not None:
            src.close()
        if stdout:
            dst.close()
        log.unlink(missing_ok=True)


def encode(directory: Path, payload: Path, tools: Tools, memory_mb: int, threads: int):
    dedup = payload.with_suffix('.exd')
    # stdin stores exactly one known data stream, never arbitrary archive paths.
    run([tools.exdupe, '-v0', f'-m{memory_mb}', f'-t{threads}', '-x1', '-z', '-stdin', dedup],
        dedup, directory.stat().st_size * 2 + BLOCK, stdin=directory,
        memory_bytes=(memory_mb + threads * 128 + 512) * 1024**2)
    with dedup.open('rb') as src, payload.open('xb') as dst:
        dst.write(MAGIC)
        while data := src.read(BLOCK):
            raw = payload.with_suffix('.raw')
            compressed = payload.with_suffix('.zl')
            raw.write_bytes(data)
            run([tools.zli, 'compress', '--profile', 'serial', raw, '--output', compressed],
                compressed, BLOCK * 2)
            dst.write(U64.pack(len(data)) + U64.pack(compressed.stat().st_size))
            with compressed.open('rb') as f:
                copy_n(f, dst, compressed.stat().st_size)
            raw.unlink()
            compressed.unlink()
    return dedup.stat().st_size


def decode(payload: Path, directory: Path, tools: Tools, header: dict):
    dedup = payload.with_suffix('.exd')
    remaining = header['exdupe_bytes']
    with payload.open('rb') as src, dedup.open('xb') as dst:
        if exact(src, 8) != MAGIC:
            raise ArchiveError('Invalid OpenZL chunks magic')
        while remaining:
            raw_len = U64.unpack(exact(src, 8))[0]
            compressed_len = U64.unpack(exact(src, 8))[0]
            if not 0 < raw_len <= min(BLOCK, remaining) or not 0 < compressed_len <= BLOCK * 2:
                raise ArchiveError('Invalid OpenZL chunk length')
            compressed = payload.with_suffix('.zl')
            raw = payload.with_suffix('.raw')
            with compressed.open('xb') as f:
                copy_n(src, f, compressed_len)
            run([tools.zli, 'decompress', compressed, '--output', raw], raw, raw_len)
            if raw.stat().st_size != raw_len:
                raise ArchiveError('OpenZL decoded size mismatch')
            with raw.open('rb') as f:
                copy_n(f, dst, raw_len)
            remaining -= raw_len
            raw.unlink()
            compressed.unlink()
        if src.read(1):
            raise ArchiveError('Trailing OpenZL chunk data')
    # Upstream -stdout alone still processes links and directory metadata: preflight
    # rejects every archive form except our single ordinary stdin file.
    check_stdin_archive(dedup, header['directory_bytes'])
    run([tools.exdupe, '-v0', '-R', dedup, '-stdout'], directory,
        header['directory_bytes'], stdout=True)
    if directory.stat().st_size != header['directory_bytes']:
        raise ArchiveError('eXdupe decoded size mismatch')
