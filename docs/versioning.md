# Versioning

The Matterstate Rust fork starts its own version sequence at `0.4.0`. Inherited
tags through `v0.3.2` belong to the upstream C project. The current `0.4.0`
working tree is not a tagged release or a published registry package.

Cargo package versions, `include/toks.h` and the native `toks_version()` string
agree. Python package metadata reads its version from the header. The C ABI
version is separate and remains `0.4`; a package version change alone does not
change the ABI.

Install from a checked-out revision using the commands in the
[README](../README.md). Pin the Git commit for reproducible deployments.
The package and import names remain `toks`; a registry install by name does
not identify this fork. This repository has no automatic publishing workflow.
