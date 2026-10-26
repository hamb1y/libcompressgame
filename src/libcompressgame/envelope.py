from __future__ import annotations

import json
import os
from pathlib import Path
import struct

from .common import ArchiveError, CHUNK, U64, canonical, copy_n, exact, file_hash, new_hash

MAGIC = b'LCGAME1\0'
MAX_HEADER = 65536


def key_for(password: bytes, salt: bytes):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(password)


def write(payload: Path, output: Path, metadata: dict, password: bytes | None = None):
    size = payload.stat().st_size
    if size > CHUNK * (2**32 - 1):
        raise ArchiveError('Payload exceeds encryption counter capacity')
    header = dict(metadata, version=1, payload_bytes=size, payload_blake3=file_hash(payload),
                  encryption='none' if password is None else 'scrypt-aes256gcm',
                  salt=None if password is None else os.urandom(16).hex(),
                  nonce=None if password is None else os.urandom(8).hex())
    raw = canonical(header)
    prefix = MAGIC + U64.pack(len(raw)) + raw
    with output.open('xb') as dst, payload.open('rb') as src:
        dst.write(prefix)
        if password is None:
            copy_n(src, dst, size)
        else:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            cipher = AESGCM(key_for(password, bytes.fromhex(header['salt'])))
            remaining = size
            for index in range(max(1, (size + CHUNK - 1) // CHUNK)):
                length = min(remaining, CHUNK)
                block = exact(src, length)
                remaining -= length
                counter = struct.pack('>I', index)
                aad = prefix + counter + bytes([remaining == 0])
                dst.write(cipher.encrypt(bytes.fromhex(header['nonce']) + counter, block, aad))
    return header


def read_header(src):
    if exact(src, len(MAGIC)) != MAGIC:
        raise ArchiveError('Not a libcompressgame v1 archive')
    size = U64.unpack(exact(src, 8))[0]
    if size > MAX_HEADER:
        raise ArchiveError('Archive header exceeds 64 KiB')
    raw = exact(src, size)
    try:
        header = json.loads(raw)
        required = {'version', 'payload_bytes', 'payload_blake3', 'encryption', 'salt', 'nonce',
                    'directory_bytes', 'exdupe_bytes', 'tools', 'chain'}
        if not isinstance(header, dict) or header.keys() != required:
            raise ValueError('header fields')
        if header['version'] != 1 or header['chain'] != ['exdupe-3', 'openzl-serial-chunks-v1']:
            raise ValueError('unsupported version/codec chain')
        for key in ('payload_bytes', 'directory_bytes', 'exdupe_bytes'):
            if type(header[key]) is not int or not 0 <= header[key] < 2**52:
                raise ValueError('invalid size')
        if header['payload_bytes'] > CHUNK * (2**32 - 1):
            raise ValueError('payload too large for nonce space')
        if not isinstance(header['tools'], dict) or header['tools'].keys() != {'exdupe', 'zli'}:
            raise ValueError('invalid tool metadata')
        for digest in [header['payload_blake3'], *header['tools'].values()]:
            if not isinstance(digest, str) or len(digest) != 64 or len(bytes.fromhex(digest)) != 32:
                raise ValueError('invalid digest')
        if header['encryption'] == 'scrypt-aes256gcm':
            if len(bytes.fromhex(header['salt'])) != 16 or len(bytes.fromhex(header['nonce'])) != 8:
                raise ValueError('invalid encryption metadata')
        elif header['encryption'] != 'none' or header['salt'] is not None or header['nonce'] is not None:
            raise ValueError('unsupported encryption')
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ArchiveError(f'Invalid archive header: {exc}') from exc
    return header, MAGIC + U64.pack(size) + raw


def unwrap(archive: Path, payload: Path, password: bytes | None, max_bytes: int):
    with archive.open('rb') as src, payload.open('xb') as dst:
        header, prefix = read_header(src)
        size = header['payload_bytes']
        if max(size, header['directory_bytes'], header['exdupe_bytes']) > max_bytes:
            raise ArchiveError('Archive exceeds extraction size limit')
        h = new_hash()
        if header['encryption'] == 'none':
            copy_n(src, dst, size, h)
        else:
            if password is None:
                raise ArchiveError('Password required for encrypted archive')
            from cryptography.exceptions import InvalidTag
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            cipher = AESGCM(key_for(password, bytes.fromhex(header['salt'])))
            remaining = size
            for index in range(max(1, (size + CHUNK - 1) // CHUNK)):
                length = min(remaining, CHUNK)
                remaining -= length
                counter = struct.pack('>I', index)
                aad = prefix + counter + bytes([remaining == 0])
                try:
                    block = cipher.decrypt(bytes.fromhex(header['nonce']) + counter,
                                           exact(src, length + 16), aad)
                except InvalidTag as exc:
                    raise ArchiveError('Wrong password or damaged authenticated archive') from exc
                dst.write(block)
                h.update(block)
        if src.read(1):
            raise ArchiveError('Unexpected trailing archive bytes')
        if h.hexdigest() != header['payload_blake3']:
            raise ArchiveError('BLAKE3 payload check failed')
    return header
