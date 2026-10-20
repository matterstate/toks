#!/usr/bin/env python3
"""tools/ci/suites.py: what a `make test` log ran, counted per test binary, so a vacuous pass cannot hide in CI.

    python3 tools/ci/suites.py build/ci/native.log build/ci/scalar.log

Each log is one tier of the Rust `make test` gate. Require assembly audits, owned
Rust tests and the C ABI caller harness, then check every caller ran with nonzero
reported counts and no skipped critical tokenizer. A caller with no count is
listed without failing. See docs/ci.md.
"""

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_tokenizers

ROOT = fetch_tokenizers.ROOT
HEAD = re.compile(r"^== \S*/tests/(\w+)(?: .*)?$")
COUNT = re.compile(r"(\d+) (?:checks|cases|calls compared|targets|vectors)\b")
SKIP = re.compile(r"\bSKIP\b|\bskip\b|(?<!\d )\bskipped\b|\bnot present\b")
TIER = re.compile(
    r"^tier auto = (\S+) \(cpu features \S+; built:([a-z0-9 ]*)\)"
)  # test_tier's selection line
PRELUDE = (
    ("asmcheck", re.compile(r"^asmcheck: [1-9]\d* objects .* assemble$")),
    ("abi lint", re.compile(r"^asm_regs_audit: .* 0 violations$")),
    ("owned Rust tests", re.compile(r"^test result: ok\. [1-9]\d* passed; 0 failed;")),
    (
        "Rust caller harness",
        re.compile(r"^rust harness: (?:4[5-9]|[5-9]\d|\d{3,}) callers, 0 failures$"),
    ),
)


def critical_names() -> re.Pattern[str]:
    table, _ = fetch_tokenizers.pin_table()
    crit = fetch_tokenizers.critical_files(table, fetch_tokenizers.ledger())
    names = {n for _, n in crit} | set(crit.values()) | {"kimik3"}
    return re.compile(
        r"(?<![A-Za-z0-9_-])(?:"
        + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        + r")(?![A-Za-z0-9_-])"
    )


def parse(path: str):
    """Return each caller's count, skips and tier, plus the audit prelude."""
    out, cur, pre = {}, None, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = HEAD.match(line)
            if m:
                cur = out.setdefault(
                    m.group(1), {"count": None, "skips": [], "tier": ""}
                )
                continue
            if cur is None:
                pre.append(line)
                continue
            for n in COUNT.findall(line):
                cur["count"] = max(cur["count"] or 0, int(n))
            if SKIP.search(line):
                cur["skips"].append(line.strip())
            if line.startswith("tier auto = "):
                cur["tier"] = line
    return out, pre


def main() -> int:
    logs = sys.argv[1:]
    if not logs:
        sys.exit(__doc__)
    want = sorted(
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(ROOT, "tests", "c", "*.c"))
    )
    crit = critical_names()
    cols, bad = [], []
    for path in logs:
        label = os.path.splitext(os.path.basename(path))[0]
        runs, pre = parse(path) if os.path.exists(path) else ({}, [])
        cols.append((label, runs))
        for name, rx in PRELUDE:
            if not any(rx.match(p) for p in pre):
                bad.append(f"{label}: no {name} pass line")
        for b in want + sorted(set(runs) - set(want)):
            r = runs.get(b)
            if r is None:
                bad.append(f"{label}: {b} did not run")
            elif r["count"] == 0:
                bad.append(f"{label}: {b} reported 0 checks")
            for s in r["skips"] if r else []:
                if crit.search(s):
                    bad.append(f"{label}: {b} skipped a critical target: {s}")
        m = TIER.match(runs.get("test_tier", {}).get("tier", ""))
        if m:
            built = m.group(2).split()
            if built:  # noqa: SIM102
                if m.group(1) not in built:
                    bad.append(
                        f"{label}: this cpu runs none of the asm tiers built ({m.group(0)}): no asm kernel was tested"
                    )

    names = want + sorted({b for _, runs in cols for b in runs} - set(want))
    out = [
        "suites: per binary, the count it printed (- = none printed), then its SKIPs",
        f"{'binary':20}" + "".join(f" {label:>14}" for label, _ in cols),
    ]
    for b in names:
        cells = []
        for _, runs in cols:
            r = runs.get(b)
            if r is None:
                cells.append("NOT RUN")
            elif r["count"] is None:
                cells.append("-")
            else:
                cells.append(str(r["count"]))
        out.append(f"{b:20}" + "".join(f" {c:>14}" for c in cells))
    for label, runs in cols:
        ran = [b for b in names if b in runs]
        skips = [(b, s) for b in ran for s in runs[b]["skips"]]
        tier = next((runs[b]["tier"] for b in ran if runs[b]["tier"]), "no tier line")
        nocount = [b for b in ran if runs[b]["count"] is None]
        forced = "unset" if label == "native" else label
        out.append(
            f"suites: {label} (TOKS_TIER={forced}): {len(ran)} binaries run ({len(want)} of tests/c), "
            f"{len(skips)} SKIP lines, {len(nocount)} without a count ({' '.join(nocount) or 'none'}); "
            f"test_tier's {tier}"
        )
        out += [f"  SKIP {label} {b}: {s}" for b, s in skips]
    out += [f"suites: FAIL {x}" for x in bad]
    if not bad:
        out.append(
            f"suites: ok ({len(cols)} logs, {len(want)} binaries each, no critical target skipped)"
        )
    print("\n".join(out))
    if os.environ.get("GITHUB_STEP_SUMMARY"):  # the run page shows the same table
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("```\n" + "\n".join(out) + "\n```\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
