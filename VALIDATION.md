# Validation evidence — current run 2026-10-26

Fresh network-enabled `scripts/build_tools.py --output tools/production --jobs 8` completed successfully using the pinned real upstream sources and their normal dependencies. The helper produced executable binaries, notices, identity metadata and a 29,201,252-byte complete corresponding-source archive. No offline dependency substitution was used in this run.

A new isolated environment installed the declared maintained PyPI packages: BLAKE3 1.0.11, cryptography 50.0.2, PyInstaller 6.22.3 and pytest 9.1.1; host Python 3.14.8/GCC 16.2.1. It contains no temporary ctypes binding.

```sh
LCG_EXDUPE="$PWD/tools/production/bin/exdupe" \
LCG_ZLI="$PWD/tools/production/bin/zli" LCG_TEST_SFX=1 \
.venv-production/bin/python -m pytest -v -s \
  --basetemp=/tmp/lcg-production-pytest --junitxml=/tmp/lcg-production-junit.xml
```

The first production-dependency run passed all 55 tests in 39.84 seconds. After adding the redirected-CP1252 help regression, the final source passed **56 tests in 55.29 seconds, zero skips**, including both plain/encrypted native Linux self-extractors with external Python/codecs absent from PATH. The final run used `--basetemp=/tmp/lcg-production-final-pytest --junitxml=/tmp/lcg-production-final-junit.xml`; other command arguments are unchanged.

The normal `lcg pack` flow also built an encrypted Linux executable without manual notice/source flags. The helper's real notice and complete corresponding sources were automatically bundled. Info, notices, verify, extraction and byte-identical source export passed with an empty external-tool PATH. That executable is 83,920,584 bytes, including its source archive. Local artifacts/logs/dependency identities and SHA256 manifest are in ignored `dist/validation-production/`; these are labeled test fixtures.

Remote Linux/Windows CI was launched after publication: https://github.com/hamb1y/libcompressgame/actions/runs/40309358931 . The Ubuntu 24.04 native job passed all 55 tests in 90.75 seconds using Python 3.12.15 and the maintained PyPI packages. The Windows 2022 job built the real codecs and passed both plain/encrypted PE self-extractor tests and all codec integrations. Its suite reported 53 passed, one Windows symlink-creation skip, and one CLI help failure: a decorative arrow could not be encoded when output was redirected under CP1252. The CLI now uses ASCII arrows; a subprocess regression checks every help command with `PYTHONIOENCODING=cp1252`. No user data is rewritten. The final corrected native CI run is linked from the repository Actions page. The earlier network/package restrictions below describe the previous run only.

## Earlier offline evidence — 2026-10-25

Local host: Linux x86-64, Python 3.12.15, GCC 16.2.1, cryptography 46.0.0, PyInstaller 6.22.3.

Final command (all unit, real codec and native SFX tests enabled):

```sh
LCG_EXDUPE=/tmp/lcg-tools/exdupe-build/exdupe \
LCG_ZLI=/tmp/lcg-tools/openzl-build/cli/zli LCG_TEST_SFX=1 \
.venv/bin/python -m pytest -v -s --junitxml=/tmp/lcg-tools/validation.xml
```

Result: **55 passed**, comprising 45 unit/format checks and 10 genuine codec/native integration cases. No skips in this Linux run.

The passing suite includes:

- Deterministic directory-stream round trips, nested/empty/unicode files, executable modes, unsafe traversal/device paths, symlinks/case collisions, file-as-parent, privileged modes, integrity failure and extraction limits.
- Real scrypt/AES-256-GCM plain/encrypted envelope tests across 1 MiB boundaries, empty payloads, wrong passwords, bit flips, truncation and trailing bytes.
- Subprocess memory/output/time limits, actionable missing-codec diagnostics, native no-replace publication and automatic source/notice provenance identity checks.
- Genuine eXdupe 3.0.2 → upstream OpenZL zli 0.3.0 round trips for plain/encrypted/empty games and a 17 MiB incompressible file requiring multiple OpenZL frames.
- Genuine eXdupe directory, symlink and ordinary named-file archives rejected before restore; modified real native archives with directory/link/diff/unknown flags, extra entries and traversal names rejected. The accepted format is deliberately limited to one ordinary stdin file.
- Both plain and encrypted Linux ELF SFX executables built and run with Python and codecs removed from PATH. Extraction, verify/info, license printing, source export and wrong-password refusal were exercised using bundled real decoder executables.
- Windows metadata wire fixtures validate strict drive/UNC provenance only under the Windows platform bit. This is source/format compatibility evidence, not native Windows execution evidence.

Measured small fixture (bytes):

| Directory stream | eXdupe | OpenZL payload | Plain archive | Encrypted archive |
| ---: | ---: | ---: | ---: | ---: |
| 2,097,994 | 11,201 | 2,149 | 2,581 | 2,653 |

The 17 MiB incompressible fixture measured 17,825,947 directory bytes → 18,071,502 eXdupe bytes → 17,974,921 OpenZL payload bytes → 17,975,361 archive bytes. That complete archive grew by approximately 0.84% over the directory stream.

These are observed fixture results, not a general compression promise. The pipeline always retains the requested second pass. Native executables include about 53 MB of runtime/decoder overhead on this development host.

## Dependency provenance and limitations

The shell cannot reach GitHub or PyPI. Upstream source was transferred through the GitHub connector into `/tmp`, then built locally:

- eXdupe 3.0.2 commit `27e03c8687fd0dfd12ff21acaea249eada22e478`, using its normal CMake target and bundled dependencies.
- OpenZL 0.3.0 commit `32246b48faee46807f84183dac4db479089f5445`, genuine upstream zli and serial encoder/decoder. The offline build linked installed Zstd 1.5.7/LZ4 1.10.0 and disabled only the unused optional XGBoost trainer. The maintained build helper also disables that trainer but obtains normal upstream dependency sources.
- Local Python hashing initially used an external temporary ctypes binding to the official BLAKE3 1.8.2 portable C source. All 35 upstream hash-mode vectors passed, with incremental input and extended output. Final full-suite/SFX tests used an external temporary ctypes binding to installed official `libblake3` **1.8.7**; the same 35 hash vectors passed. These temporary bindings are ignored testing infrastructure and are not shipped or substituted for the declared production dependency.

The maintained PyPI dependency and fresh source-build-helper checks were subsequently completed in the current run above. Native Windows evidence and its initial help-encoding failure are recorded above. The repository was archived during this earlier run; it has since been unarchived and published.

The new source and native fixture executables are reviewable locally. Fixture binaries contain test game data and test notices and are not production releases. Source/notice discovery metadata records identities and provenance; it is not an upstream publisher signature.
