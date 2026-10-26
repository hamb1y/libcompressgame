# libcompressgame

A Python CLI that packs a game directory into one native self-extracting executable for **Linux or Windows**:

```
directory manifest + file bytes → eXdupe 3.0.2 → OpenZL 0.3.0
→ BLAKE3 → optional password encryption → bundled native extractor
```

The extractor contains Python, both genuine codec executables, the archive and supplied notices/sources. The recipient needs no Python installation or codec tools. Build Linux ELF executables on Linux and Windows PE executables on Windows; PyInstaller does not cross-compile. Build on the oldest Linux distribution you intend to support because bundled executables retain native system/CPU requirements. This project targets 64-bit Linux and Windows; it does not claim one executable runs on both systems.

## Install and build the codecs

Start from a cloned repository or an unpacked source distribution, then run the commands below from its root. Requires Python 3.11+, Git, CMake and a C/C++ compiler. The Windows source build uses Visual Studio 2022 with its C++ tools and ClangCL components; Linux needs a compiler with C++20 `std::format` support, static C/C++ runtime libraries for eXdupe, and the usual development tools.

```sh
python -m pip install ".[build,test]"
python scripts/build_tools.py --output tools --jobs 2
```

A published wheel installs the `lcg` CLI; use `python -m pip install "./libcompressgame-0.1.0-py3-none-any.whl[build]"` with a downloaded wheel. The source distribution also includes `scripts/build_tools.py` for building the required codecs. No PyPI publication is assumed.

The build script checks out immutable source commits (including submodules), builds eXdupe and OpenZL's real `zli`, and saves corresponding sources and a notice in `tools/`. It needs network access for upstream repositories and their build dependencies. Tools are not downloaded or executed implicitly while packing or extracting.

```sh
lcg doctor
```

The CLI finds tools on `PATH` or in the current directory's `tools/bin`. Explicit `--exdupe PATH` and `--zli PATH` options override discovery; on Windows those executables end in `.exe`. Paths containing spaces are supported. Versions are checked; incompatible formats are never silently substituted. The source build disables OpenZL's unused optional XGBoost trainer; its real serial profile and universal decoder are unchanged.

## Create a single executable

Linux example:

```sh
lcg pack /games/MyGame ./MyGame-setup
./MyGame-setup ./MyGame-restored
./MyGame-setup --verify
```

Windows PowerShell example (after building tools on Windows):

```powershell
lcg pack C:\Games\MyGame .\MyGame-setup.exe
.\MyGame-setup.exe .\MyGame-restored
```

The build script writes `toolchain.json` beside its notices and source archive. Packing discovers these outputs beside the selected tools and checks all four file identities and pinned source provenance before automatically bundling them. For independently installed tools, supply explicit `--notice FILE` and `--source-archive FILE` options; these overrides remain available. Build metadata records local provenance and does not authenticate an upstream publisher.

Outputs must not exist and must be outside the source directory. Their parent directories must already exist. Extraction validates every file before publishing the complete destination with a native atomic rename that refuses replacement. It never launches the game or runs an installer script.

For password encryption, add `--encrypt`. Passwords are prompted twice during packing and once during extraction. Automation can use `--password-file FILE` on each command. The file's exact bytes are the password, including any trailing newline; protect it yourself. Secrets are never passed to codec processes, stored in the executable, read from an environment variable, or accepted as command-line password strings.

Encryption uses scrypt (N=32768, r=8, p=1; random 16-byte salt) and AES-256-GCM in 1 MiB authenticated chunks. Each chunk authenticates the complete header, its index and whether it is final. A random nonce prefix and counter ensure unique nonces under each derived key. Wrong passwords, changed headers, reordered chunks and truncation fail verification. BLAKE3 verifies the decrypted OpenZL payload and every extracted file. Without encryption these hashes detect corruption; they do **not** authenticate a publisher. Distributors should sign executables through their own signing process.

## Portable archive and verification

The `.lcg` format can be transferred between Linux and Windows with supported filenames. Its decoders are external when using the Python CLI:

```sh
lcg pack /games/MyGame ./MyGame.lcg --archive --encrypt
lcg info ./MyGame.lcg
lcg verify ./MyGame.lcg
lcg unpack ./MyGame.lcg ./restored
```

`info` and the executable's `--info` display untrusted header metadata without decoding or asking for a password. The extractor supports `--licenses` and `--export-sources NEW_DIRECTORY` to expose the supplied notices and corresponding sources.

`pack` prints stage sizes (`directory_bytes`, `exdupe_bytes`, `payload_bytes`, `archive_bytes`, and, for SFX, `executable_bytes`). eXdupe already compresses; the requested OpenZL pass can expand the result. No compression-ratio improvement is promised. The OpenZL `serial` profile emits a genuine OpenZL frame whose generic graph uses Zstd. It is not a substitute container fabricated by this project. See the [upstream CLI documentation](https://openzl.org/getting-started/cli/).

## Limits and preserved data

- Regular files, empty directories, UTF-8 portable relative names and ordinary permission bits are preserved. Root-directory mode, timestamps, ownership, ACLs, extended attributes, ADS and sparse extents are not preserved; hard links are stored as independent file contents.
- Symlinks, junctions/reparse points, special files, traversal paths, Windows device names, trailing dots/spaces and Unicode-normalized case collisions are rejected. This ensures a package created on Linux can be safely restored on Windows. Keep the source directory quiescent while packing; detected file changes fail the snapshot.
- The manifest is deterministic and bounded to 100,000 entries/16 MiB. eXdupe adds random archive metadata, and encryption adds randomness, so complete archives/executables are not byte-reproducible.
- Python copies file data in 1 MiB buffers. OpenZL receives at most 16 MiB per frame. Real tools run with memory limits (Linux address-space limit or Windows Job Object), a one-hour timeout per invocation, and monitored output/log limits. Decoding has a 2 GiB process-memory cap. Encoding eXdupe has a cap based on `--memory-mb` and `--threads`. Version probes are trusted local tools.
- Extraction defaults to a 1 TiB limit on each intermediate stage and total restored file bytes; reduce it with `--max-bytes`. Codec output limits are monitored while running and checked afterward; an individual write can briefly exceed the limit before termination.
- Intermediates and verified files use private temporary directories. Budget several times the original game size in free disk space for packing, extraction and executable building. Failures clean the temporary workspace and leave no published destination. Filesystems must support hard-link publication for archive/executable files and native no-replace rename for directories.
- Treat self-extracting executables as programs from their distributor. Do not run untrusted executables. The archive parser and bundled codec versions should be kept current as upstreams evolve.

## Test and distribution status

```sh
python -m pytest -q
# Genuine integration, including encrypted and unencrypted native SFX:
LCG_EXDUPE="$PWD/tools/bin/exdupe" LCG_ZLI="$PWD/tools/bin/zli" LCG_TEST_SFX=1 python -m pytest -v -s
```

For PowerShell set the same three names with `$env:NAME = 'value'` before invoking pytest. Without explicit codec paths, integration tests report **skips**, not success. CI builds pinned real codecs and runs all plain/encrypted directory and native executable round trips on `ubuntu-24.04` and `windows-2022`, recording stage sizes in its logs. A workflow definition is not evidence that either build has passed; inspect the run for the commit you use.

Local validation includes genuine eXdupe/OpenZL round trips and plain/encrypted Linux ELF self-extractors, including unsafe native archive metadata rejection. The current run uses the maintained PyPI BLAKE3 package and a fresh network-enabled execution of the source-build helper. Real plain/encrypted Windows PE self-extractors also passed on a native CI runner; see the linked validation evidence and the complete CI result for the commit you use. See [VALIDATION.md](VALIDATION.md) for exact evidence, measured sizes and limits.

Project source is BSD-3-Clause. Redistributing codec/runtime binaries also entails their respective licenses. The build script preserves pinned codec sources and dependency licenses for bundling; supply any additional runtime/dependency notices needed for your distribution with repeated `--notice` and `--source-archive` options. The resulting source archives are included as data and are never automatically extracted or executed.
