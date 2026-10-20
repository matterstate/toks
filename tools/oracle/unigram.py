#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p python313 clang uv
# ruff: noqa: EXE005, SIM102
"""Generate pinned Hugging Face streams and check the Rust library against them."""

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+")
    parser.add_argument("--n", type=int, default=2500)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--out", type=Path, default=Path("build/rust-unigram-oracle"))
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument(
        "--python", help="Python with tokenizers==0.23.2; otherwise use uv"
    )
    parser.add_argument(
        "--rust-lib", type=Path, default=Path("target/release/libtoks.a")
    )
    args = parser.parse_args()
    if not 1 <= args.n <= 100000:
        parser.error("n must be 1..100000")
    if not 1 <= args.jobs <= 32:
        parser.error("jobs must be 1..32")
    cache = Path(
        os.environ.get("TOKS_TOKENIZER_CACHE", Path.home() / ".cache/toks/tokenizers")
    )
    exclusions = ("uni_albert", "uni_xlnet")
    models = args.models or sorted(
        path.name for path in cache.glob("uni_*") if path.name not in exclusions
    )
    if not 1 <= len(models) <= 128:
        parser.error("expected 1..128 models")
    args.out.mkdir(parents=True, exist_ok=True)
    runner = args.out / "rust"
    libraries = ["-lpthread", "-lm"]
    if platform.system() == "Linux":
        libraries += ["-ldl", "-lrt", "-lutil"]
    subprocess.run(
        [
            "clang",
            "-O2",
            "-std=c17",
            "-Iinclude",
            "tests/unigram/e2e_check.c",
            str(args.rust_lib),
            *libraries,
            "-o",
            str(runner),
        ],
        check=True,
        timeout=120,
    )

    def run(model: str) -> dict:
        stream = args.out / (model + ".bin")
        if not args.reuse:
            python = (
                [args.python]
                if args.python
                else ["uv", "run", "-q", "--with", "tokenizers==0.23.2", "python"]
            )
            with (
                stream.open("wb") as output,
                (args.out / (model + ".generator.log")).open("wb") as errors,
            ):
                subprocess.run(
                    python
                    + [
                        "tests/unigram/e2e_gen.py",
                        "--tok",
                        model,
                        "--kind",
                        "random",
                        "--n",
                        str(args.n),
                    ],
                    stdout=output,
                    stderr=errors,
                    check=True,
                    timeout=900,
                )
        with stream.open("rb") as source:
            result = subprocess.run(
                [str(runner), str(cache / model)],
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=900,
                check=False,
            )
        log = result.stdout.decode(errors="replace")
        summary = re.search(r": ([0-9]+) encodes,", log)
        compared = int(summary.group(1)) if summary is not None else 0
        status = result.returncode
        if status == 0:
            if compared == 0:
                status = 1
                log += "No encode cases were compared.\n"
        (args.out / (model + ".rust.log")).write_text(log)
        with stream.open("rb") as source:
            oracle_hash = hashlib.file_digest(source, "sha256").hexdigest()
        with (cache / model).open("rb") as source:
            model_hash = hashlib.file_digest(source, "sha256").hexdigest()
        print(model, status, flush=True)
        return {
            "model": model,
            "model_sha256": model_hash,
            "oracle_sha256": oracle_hash,
            "status": status,
            "encodes_compared": compared,
            "log": log,
        }

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(run, models))
    with args.rust_lib.open("rb") as source:
        library_hash = hashlib.file_digest(source, "sha256").hexdigest()
    report = {
        "host": platform.platform(),
        "library_sha256": library_hash,
        "generator": "tokenizers==0.23.2",
        "random_cases_requested": args.n,
        "generator_exclusions": [] if args.models else list(exclusions),
        "models": results,
    }
    (args.out / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(any(result["status"] != 0 for result in results))


if __name__ == "__main__":
    main()
