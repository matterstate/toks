# Contributing

Changes to this private fork target `main` in `matterstate/toks`. Keep each
change focused and preserve upstream authorship and notices. Contributions to
this fork use Apache-2.0; this fork adds no separate relicensing grant.

## Validation

Run commands in the Nix shell described in [README.md](README.md).

```sh
python3 tools/ci/fetch_tokenizers.py
tools/ci/test.sh
make test-guard
```

For Python binding changes, also build the wheel and run the installed-wheel
parity checks described in [CI](docs/ci.md). Report commands, failures and
missing optional fixtures in the pull request.

Supported tokenizers must return the reference token IDs. Use the frozen C
implementation and the pinned Hugging Face oracle to check changes. A changed
ID requires investigation before merging.

A performance claim needs paired measurements: host, load, tokenizer, corpus,
chunk size, cache state, build flags, commands and complete results. Keep
correctness checks outside timed sections and report regressions too.

Keep the C reference separate from production Rust changes. Update
`include/toks.h` and its ABI version when changing the public C ABI.
