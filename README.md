# toks

Matterstate's private Rust fork of [bitemyapp/toks](https://github.com/bitemyapp/toks),
derived from [Actual Computer's toks](https://github.com/actual-computer/toks).
The default branch is `main`.

The Rust core uses the original NEON/AVX2 assembly and exposes an owned Rust API,
the C ABI and a PyO3 Python extension. The original C implementation stays as a
frozen correctness and performance reference.

## Build and test

On NixOS, enter a shell with the build tools:

```sh
nix-shell -p cargo rustc clang llvm gnumake python313 uv
```

From that shell:

```sh
make
python3 tools/ci/fetch_tokenizers.py
tools/ci/test.sh
make test-guard
make reference
uv build --wheel python --python 3.13
```

`tools/ci/test.sh` checks native and scalar execution, the assembly audit and
missing critical tokenizer fixtures. The fetch command verifies pinned hashes;
the cache defaults to `~/.cache/toks`. See [CI](docs/ci.md) for the full checks.

Linux x86-64 and macOS arm64 have been exercised. CI currently runs on Linux
x86-64. The Rust Windows port is incomplete. The core remains mostly unsafe;
the owned `Tokenizer`, `Encoder` and `Decoder` API manages lifetimes and scratch
ownership.

## Layout

- `rust/`: production tokenizer core and worker pool.
- `src/asm/`: shared assembly kernels; `include/`: C ABI.
- `python/`: PyO3 binding, Python API and parity tests.
- `src/core/`, `src/platform/`, `Makefile.reference`: frozen C reference.
- `tests/`: correctness fixtures and C callers used against both implementations.
- `tools/`: test, oracle and benchmark callers.
- `docs/`: algorithms, API contracts, migration details and measurement receipts.

## Performance and exactness

The [Rust migration report](docs/rust-port/README.md) records the port's coverage
and limits. [Paired benchmarks](docs/rust-port/benchmarks.md) separate fresh,
streaming and replay workloads; [optimization records](docs/rust-port/optimizations.md)
include regressions and rejected experiments. The later
[Unigram optimization](docs/rust-port/unigram-path.md) has separate measurements.
These are historical measurements on the named machines, not a throughput
guarantee for every tokenizer or the Python adapter.

See the [Python API](python/README.md), [testing guide](docs/testing.md) and
[contribution guide](CONTRIBUTING.md) for development details.

The code is Apache-2.0; see [LICENSE](LICENSE), [NOTICE](NOTICE),
[LICENSING.md](LICENSING.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
The inherited `v0.3.0` and `v0.3.1` tags retain their original BUSL license;
`v0.3.2` is the upstream C release, not a release of this Rust fork.
