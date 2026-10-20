# CI

[The Rust workflow](../.github/workflows/rust.yml) runs on pushes to `main`,
pull requests targeting `main` and manual dispatch. It uses the standard
`ubuntu-24.04` runner, Rust 1.94.1 and Python 3.13 for wheel checks. Repository
permissions are read-only. Logs and result files are retained for 14 days.

The workflow checks:

1. Pinned tokenizer fixtures, verified by SHA-256.
2. Native and scalar Rust execution through the C callers, owned Rust API and
   assembly audits (`tools/ci/test.sh`). Missing critical fixtures fail the job.
3. Protected-page tests (`make test-guard`).
4. An installed Python wheel against reviewed Rust regression snapshots and the
   pinned Hugging Face, tiktoken and transformers oracles.
5. Python source archive construction.

The fork has no scheduled jobs or automatic release publishing. Upstream's
Blacksmith workflows and organization-specific contribution automation have
been removed. Historical upstream release procedures under `docs/release/`
describe the original C project.

## Reproduce locally

Enter the Nix shell from [README.md](../README.md), then run:

```sh
python3 tools/ci/fetch_tokenizers.py
tools/ci/test.sh
make test-guard
uv build --wheel python --python 3.13 --out-dir build/wheels
uv venv --python 3.13 build/python-env
uv pip install --python build/python-env/bin/python build/wheels/*.whl pytest tokenizers==0.23.2 tiktoken==0.14.0 transformers==5.18.0
build/python-env/bin/python -m pytest -q -ra -p no:cacheprovider python/tests
uv build --sdist python --python 3.13 --out-dir build/dist
```

Current CI does not test macOS or Windows. CI checks correctness; performance
canaries use paired Rust builds on a controlled host. See
[validation](validation.md) for snapshot review and canary requirements.
