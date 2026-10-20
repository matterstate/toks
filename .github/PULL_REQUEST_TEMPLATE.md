## What changes

## Why

The bug, the measurement or the idea; link the issue if there is one.

## Receipts

- Commands run and on what machine: `tools/ci/test.sh`, `make test-guard`, and the installed-wheel checks
  in `docs/ci.md` if the Python binding changed.
- Exactness: which tokenizers and cases were compared, ids byte for byte against hf tokenizers 0.23.2.
- Speed, if claimed: host and its load, tokenizer, corpus, chunk size, the exact command and its output, the
  comparator's number beside toks's.
