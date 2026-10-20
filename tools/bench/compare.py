#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p python313 rustc clang git util-linux
# ruff: noqa: EXE005, SIM102
"""Paired, exact-output Rust baseline/candidate benchmark using the SAME upstream e2e caller.

Every ABBA run emits raw logs and full token-stream SHA-256. Timings exclude
load and output validation. Report all cells; never discard slow candidate cells.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
ap = argparse.ArgumentParser()
ap.add_argument("--baseline", default="build/rust-bench/baseline-e2e")
ap.add_argument("--candidate", default="build/rust-bench/candidate-e2e")
ap.add_argument(
    "--models",
    nargs="+",
    default=[
        "gpt2",
        "llama3",
        "o200k",
        "qwen38",
        "gemma4",
        "wp-bert-uncased",
        "uni_t5base",
    ],
)
ap.add_argument("--corpora", nargs="+", default=["en", "code", "ml", "cjk"])
ap.add_argument("--chunks", nargs="+", type=int, default=[4096])
ap.add_argument("--rounds", type=int, default=3)
ap.add_argument("--reps", type=int, default=5)
ap.add_argument("--cpu", type=int)
ap.add_argument("--out", default="build/rust-bench/paired")
ap.add_argument(
    "--golden",
    help="reviewed baseline golden.json from an earlier run; require every cell to match",
)
a = ap.parse_args()
if not 1 <= a.rounds <= 31 or not 1 <= a.reps <= 101:
    ap.error("rounds must be 1..31 and reps 1..101")
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def command(cmd):
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()


meta = {
    "host": platform.platform(),
    "cpu": a.cpu,
    "args": vars(a),
    "commit": command(["git", "rev-parse", "HEAD"])
    if (ROOT / ".git").exists()
    else "rsync checkout",
    "rustc": command(["rustc", "-Vv"]),
    "clang": command(["clang", "--version"]),
    "binaries": {
        k: {"path": v, "sha256": sha(v)}
        for k, v in [("baseline", a.baseline), ("candidate", a.candidate)]
    },
    "started": time.time(),
    "cells": [],
}
meta["processor"] = (
    command(["sysctl", "-n", "machdep.cpu.brand_string"])
    if platform.system() == "Darwin"
    else command(["lscpu"])
)
if a.cpu is not None:
    meta["siblings"] = (
        Path(f"/sys/devices/system/cpu/cpu{a.cpu}/topology/thread_siblings_list")
        .read_text()
        .strip()
    )
# Golden streams derive from the known-working Rust baseline, once per cell.
prior_golden = json.loads(Path(a.golden).read_text()) if a.golden else None
golden = {}
for model in a.models:
    tokenizer = (
        Path(
            os.environ.get(
                "TOKS_TOKENIZER_CACHE", Path.home() / ".cache/toks/tokenizers"
            )
        )
        / model
    )
    if not tokenizer.is_file():
        raise SystemExit(f"missing tokenizer: {tokenizer}")
    for corpus in a.corpora:
        text = ROOT / "build/rust-bench/corpora" / f"{corpus}.txt"
        for chunk in a.chunks:
            key = f"{model}-{corpus}-{chunk}"
            cell = {
                "key": key,
                "model_sha256": sha(tokenizer),
                "corpus_sha256": sha(text),
                "bytes": text.stat().st_size,
                "runs": [],
            }
            for block in range(a.rounds):
                # Alternating ABBA/BAAB preserves pairing while balancing starts.
                order = (
                    ("baseline", "candidate", "candidate", "baseline")
                    if block % 2 == 0
                    else ("candidate", "baseline", "baseline", "candidate")
                )
                for slot, side in enumerate(order):
                    tag = f"{key}-{block}-{slot}-{side}"
                    ids = out / "ids.tmp"
                    env = dict(os.environ, E2E_IDS_OUT=str(ids))
                    cmd = [
                        a.baseline if side == "baseline" else a.candidate,
                        str(tokenizer),
                        str(chunk),
                        str(a.reps),
                        str(text),
                    ]
                    if a.cpu is not None:
                        cmd = ["taskset", "-c", str(a.cpu)] + cmd
                    before = os.getloadavg()
                    start = time.monotonic()
                    cp = subprocess.run(
                        cmd,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        env=env,
                        check=True,
                    )
                    elapsed = time.monotonic() - start
                    (out / f"{tag}.log").write_text(cp.stdout)
                    digest = sha(ids)
                    ids.unlink()
                    if prior_golden is not None:
                        if digest != prior_golden[key]["sha256"]:
                            raise ValueError(f"baseline golden mismatch: {tag}")
                    expected = golden.setdefault(
                        key,
                        {
                            "sha256": digest,
                            "from": tag,
                            "binary_sha256": meta["binaries"][side]["sha256"],
                        },
                    )
                    # The first block starts with the baseline; the candidate cannot establish the golden.
                    if digest != expected["sha256"]:
                        raise ValueError(f"token stream mismatch: {tag}")
                    line = next(
                        l for l in cp.stdout.splitlines() if l.startswith("E2E ")
                    )
                    fields = dict(x.split("=", 1) for x in line.split()[1:])
                    run = {
                        "side": side,
                        "block": block,
                        "slot": slot,
                        "seconds": elapsed,
                        "load_before": before,
                        "load_after": os.getloadavg(),
                        "ids_sha256": digest,
                        "metrics": fields,
                    }
                    cell["runs"].append(run)
            ratios = {}
            for state in ("cold", "pass", "warm"):
                times = {
                    side: [
                        statistics.median(
                            float(t) for t in r["metrics"][state + "_reps_s"].split(",")
                        )
                        for r in cell["runs"]
                        if r["side"] == side
                    ]
                    for side in ("baseline", "candidate")
                }
                ratios[state] = statistics.median(
                    times["baseline"]
                ) / statistics.median(times["candidate"])
            cell["speedup"] = ratios
            meta["cells"].append(cell)
            (out / "results.json").write_text(json.dumps(meta, indent=2) + "\n")
            (out / "golden.json").write_text(json.dumps(golden, indent=2) + "\n")
            print(key, " ".join(f"{k}={v:.3f}x" for k, v in ratios.items()), flush=True)
meta["geomean"] = {
    state: math.exp(
        statistics.mean(math.log(c["speedup"][state]) for c in meta["cells"])
    )
    for state in ("cold", "pass", "warm")
}
meta["finished"] = time.time()
(out / "results.json").write_text(json.dumps(meta, indent=2) + "\n")
print("geomean:", meta["geomean"])
