# Architecture

The root Cargo package is `toks`. It builds an `rlib`, a static library and a
shared library from `src/lib.rs`. `python/rust` is a workspace member that links
the core into a PyO3 extension. Neither builds a C tokenizer implementation.

| Location | Responsibility |
| --- | --- |
| `src/safe.rs`, `src/safe/` | Owned Rust API and reusable batch encoder |
| `src/core/` | Loading, configuration, tokenization, decoding and C ABI exports |
| `src/gen/` | Generated Rust Unicode and normalization tables |
| `src/par.rs` | Native worker pool |
| `src/platform.rs`, `src/atomic.rs` | OS operations and atomic primitives |
| `native/asm/` | NEON/AVX2 kernels and optional AVX-512 experiments |
| `native/core/`, `native/platform/` | ABI and assembly layout declarations |
| `native/gen/` | Pinned C-format data read by independent test oracles |
| `include/toks.h` | Public C ABI |
| `python/rust/`, `python/toks/` | Python extension and package surface |
| `tests/` | Rust integration tests, C ABI callers, fixtures and external-oracle drivers |
| `tools/` | Build, validation and measurement helpers |
| `benchmarks/` | Frozen corpus manifest and current measurement receipts |

Loading validates the tokenizer configuration, compiles algorithm-specific
immutable tables, builds vocabulary and decoder indexes, and selects an
available CPU tier. Supported paths include byte-level BPE, SentencePiece-style
BPE, WordPiece and Unigram. Supported pre-tokenizer templates use assembly;
other supported chains use the generic Rust engine. Unsupported configurations
return an error rather than silently approximating their semantics.

Encoding separates added tokens from ordinary text, applies normalization and
pre-tokenization, runs the selected model, and applies the requested template,
truncation and padding. Token IDs and public behavior are checked against pinned
external oracles and reviewed snapshots; see [validation](validation.md).

The core remains mostly unsafe Rust translated from the original implementation.
The owned API manages tokenizer, scratch and stream lifetimes. Immutable
tokenizers can be shared; mutable encoder/decoder state belongs to one caller
at a time. Native assembly shares explicit layouts with Rust, checked through
C ABI and assembly audit tests.

`BatchEncoder` preserves input order and lazily reuses a worker pool. The Python
adapter dispatches batches of 32–4,096 inputs totaling 1–64 MiB to at most four
participants, including the caller. Smaller or larger requests use the serial
path. Each worker owns its mutable scratch state.

The default build supports Linux and macOS on x86-64 and arm64. Linux x86-64 is
the current CI target; Windows support is incomplete. Cross-platform assembly
syntax audits do not establish runtime support on those other platforms.
