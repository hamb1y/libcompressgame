# Validation evidence — 2026-10-25

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

**Still pending:** installation/integration with the maintained PyPI `blake3` module, execution of the network-dependent source-build helper from a fresh checkout, and native Windows PE builds/execution. CI is configured to perform those checks on Ubuntu 24.04 and Windows 2022 using the real maintained Python package. The repository was archived during this work, preventing publication/CI triggering. No Windows success or passing remote workflow is claimed.

The new source and native fixture executables are reviewable locally. Fixture binaries contain test game data and test notices and are not production releases. Source/notice discovery metadata records identities and provenance; it is not an upstream publisher signature.
