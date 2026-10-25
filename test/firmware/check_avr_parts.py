#!/usr/bin/env python3
"""Build every AVR part listed in build_system/avr/ and check the list is the truth.

  python3 test/firmware/check_avr_parts.py          # every listed part must build
  python3 test/firmware/check_avr_parts.py --all    # also: no part outside the list may build

The list is the contract: only the listed parts are supported. This catches a listed
part that stopped building (HAL or toolchain change) and, with --all, a part that now
builds but is not listed (so the list is out of date). Needs avr-gcc; skips without it.
"""

import argparse
import concurrent.futures
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def listed_parts() -> set:
    nodes = set()
    for path in sorted((ROOT / "build_system" / "avr").glob("tree_branch_*.yaml")):
        nodes |= {name.lower() for name in yaml.safe_load(path.read_text())["nodes"]}
    return nodes


def host_database_parts() -> set:
    return {p.stem.lower() for p in (ROOT / "pc_tool" / "mcu_db" / "avr" / "atmega").iterdir()}


def build(part: str) -> tuple:
    make = ["make", "PLATFORM=avr", f"MCU={part}"]
    subprocess.run([*make, "clean"], cwd=ROOT, capture_output=True)
    result = subprocess.run(make, cwd=ROOT, capture_output=True, text=True)
    errors = [line for line in (result.stdout + result.stderr).splitlines() if "error" in line.lower()]
    return part, result.returncode == 0, (errors[0].strip()[:110] if errors else "")


def build_all(parts: list, jobs: int) -> dict:
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        return {part: (ok, why) for part, ok, why in pool.map(build, parts)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--all", action="store_true", help="also build every other part of the host database")
    ap.add_argument("-j", "--jobs", type=int, default=6)
    args = ap.parse_args()

    if shutil.which("avr-gcc") is None:
        print("avr-gcc not found, skipping")
        return 0

    listed = sorted(listed_parts())
    failures = []

    results = build_all(listed, args.jobs)
    broken = {p: why for p, (ok, why) in results.items() if not ok}
    print(f"listed parts: {len(listed) - len(broken)}/{len(listed)} build")
    for part, why in sorted(broken.items()):
        print(f"  FAIL {part}: {why}")
        failures.append(part)

    if args.all:
        others = sorted(host_database_parts() - set(listed))
        results = build_all(others, args.jobs)
        surprising = sorted(p for p, (ok, _) in results.items() if ok)
        print(f"unlisted parts: {len(others) - len(surprising)}/{len(others)} fail to build, as expected")
        for part in surprising:
            print(f"  BUILDS BUT NOT LISTED {part}")
            failures.append(part)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
