# Rust and C APIs

## Rust

The public owned API is exported from the `toks` crate. Add this repository as a
Cargo dependency and use `Tokenizer`, `Encoder`, `BatchEncoder` and `Decoder`.

```rust
use toks::{EncodeFlags, ScratchOptions, Tier, Tokenizer};

fn main() -> Result<(), toks::Error> {
    let tokenizer = Tokenizer::from_file("tokenizer.json", Tier::Auto)?;
    let mut encoder = tokenizer.encoder(ScratchOptions::default())?;
    let ids = encoder.encode(b"Hello world", EncodeFlags::default())?;
    let _text = tokenizer.decode(&ids, toks::DecodeFlags::default())?;
    Ok(())
}
```

The tokenizer owns immutable model tables. Encoders and decoders retain the
model for their entire lifetime and own their scratch state. Use separate
mutable state for concurrent calls. A `BatchEncoder` reuses worker state and
returns results in input order.

See [src/safe.rs](../src/safe.rs) for supported flags, errors and method
signatures, and [Rust integration tests](../tests/owned.rs) for complete usage.
Generate the local API reference with `cargo doc --no-deps -p toks`.

## C ABI

[include/toks.h](../include/toks.h) defines all public functions, structures,
flags, errors and ownership requirements. `make` produces `libtoks.a` and the
platform's shared library under `build/<os>-<isa>/`.

A caller loads a context, obtains capacity and scratch requirements, allocates
and initializes its buffers, then encodes or decodes while checking every
return code. A loaded context can be shared. Scratch buffers and decode streams
must not be used concurrently. The C API leaves allocation and cleanup to the
caller; the Rust API wraps those lifetimes.

`toks_pieces` returns tokenization piece boundaries. Use `toks_split_points`
when independently encoding chunks: its certified cuts, continuation flags and
post-processing requirements are documented in the public header. Do not
substitute arbitrary byte or piece offsets for certified cuts.

The [C ABI callers](../tests/c/) are executable examples covering errors,
capacity limits, malformed inputs, concurrency and protected-page bounds.

## Python

The [Python API](../python/README.md) documents the installed `toks` package,
including Hugging Face-style calls, tiktoken-style calls, buffers and batching.
Build and installed-wheel test commands are in [CI](ci.md).
