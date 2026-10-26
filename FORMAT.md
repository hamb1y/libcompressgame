# LCG format version 1

All sizes are unsigned little-endian 64-bit integers. JSON is ASCII-encoded, sorted-key compact JSON. Readers bound allocation lengths before reading them.

## Directory stream

`LCGDIR1\0`, JSON length, JSON manifest, then regular file contents in manifest order.

The manifest is an ordered array of `{path, kind, mode, size, blake3}` entries. Paths are ascending portable POSIX relative strings. Every parent directory has an earlier directory entry. Kinds are `file` and `dir`; directory sizes are zero and their hash is null. File hashes are 64 lowercase hexadecimal BLAKE3 characters. Modes are integers 0..0777. Duplicate normalized/case-folded paths and unsupported metadata are rejected. Trailing bytes are forbidden.

## Codec payload

The directory stream is passed on stdin to eXdupe **3.0.2**, using `-x1` (deduplication and its normal compression), `-z` (BLAKE3 deduplication hashes), bounded deduplication memory and thread options. Before decode, a narrow eXdupe-format preflight validates the 3.0.2 signature and footer chain and accepts exactly one ordinary file named `stdin` with an empty link field and the expected size. Its absolute provenance field must be empty, except for Windows-platform records where a strict absolute drive/UNC path ending in `-stdin` is accepted: upstream Windows `_wfullpath` produces this value, and `restore_from_file` never uses that field. Directory, symlink and differential flags are forbidden. Decode then uses `-R FILE -stdout`. The preflight is necessary because upstream's stdout mode still processes directory/symlink metadata.

The resulting eXdupe byte stream is split into chunks of at most 16 MiB. Each is compressed using genuine OpenZL **0.3.0** `zli compress --profile serial INPUT --output OUTPUT`. The payload is `LCGZL1\0\0`, followed by repetitions of uncompressed chunk length, compressed frame length, OpenZL frame bytes. Compressed length is at most 32 MiB. Total decoded size must exactly equal `exdupe_bytes`. No trailing bytes are accepted. OpenZL frames are decoded independently with `zli decompress INPUT --output OUTPUT`.

## Envelope

`LCGAME1\0`, JSON header length, JSON header, encoded body. Header maximum is 64 KiB. Its exact keys are:

- `version`: 1
- `chain`: `["exdupe-3", "openzl-serial-chunks-v1"]`
- `directory_bytes`, `exdupe_bytes`, `payload_bytes`: exact intermediate sizes
- `payload_blake3`: BLAKE3 of the full plaintext codec payload
- `tools`: `exdupe` and `zli` BLAKE3 executable identities, used to verify bundled SFX tools
- `encryption`: `none` or `scrypt-aes256gcm`
- `salt`, `nonce`: null when plaintext; 16-byte and 8-byte random values in hexadecimal when encrypted

The plaintext body is the exact codec payload. The encrypted body partitions that same payload into 1 MiB chunks, each followed by a 16-byte AES-GCM tag; an empty payload still has one empty authenticated chunk. The scrypt-derived key is 32 bytes, using N=32768, r=8 and p=1. For chunk i, nonce = 8-byte random prefix || big-endian uint32(i). Associated data = exact envelope prefix through JSON header || big-endian uint32(i) || one byte equal to 1 for the final chunk and 0 otherwise. Number/size of chunks is determined by `payload_bytes`. No reused counter space, extra chunks or trailing bytes are allowed.

The outer hash is checked before invoking codecs. All extracted file hashes are checked before atomic no-replace publication. Header fields and embedded hashes in an unencrypted archive are not an external trust anchor. This format does not claim to authenticate publishers.

## SFX

SFX is a host-native PyInstaller one-file program. The archive is bundled as `game.lcg`; tools are `tools/exdupe[.exe]` and `tools/zli[.exe]`. These exact executable bytes are checked against the envelope identities before running. Runtime and tools are unpacked by PyInstaller into a private runtime directory. There is no cross-OS executable or embedded password. Source archives/notices are bundled as inert data.
