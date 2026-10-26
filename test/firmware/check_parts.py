#!/usr/bin/env python3
"""Build every part listed in build_system/ and report the ones that fail.

  python3 test/firmware/check_parts.py              # every platform whose toolchain is installed
  python3 test/firmware/check_parts.py stm32 -j 8   # one platform

The node lists are the contract: only listed parts are supported, so each must build.
This catches a listed part that stopped building after a HAL, YAML or toolchain change.
A platform whose compiler is not installed is skipped and reported.
"""

import argparse
import concurrent.futures
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from build_system.generate import TREE, load_yaml, resolve  # noqa: E402


def parts_by_platform() -> dict:
    platforms = {}
    for platform in load_yaml(TREE / "tree_root.yaml")["platform"]:
        nodes = [n for p in sorted((TREE / platform).glob("tree_branch_*.yaml")) for n in load_yaml(p)["nodes"]]
        platforms[platform] = sorted(n.lower() for n in nodes)
    return platforms


def build(part: str) -> tuple:
    subprocess.run(["make", f"MCU={part}", "clean"], cwd=ROOT, capture_output=True)
    result = subprocess.run(["make", f"MCU={part}"], cwd=ROOT, capture_output=True, text=True)
    errors = [line for line in (result.stdout + result.stderr).splitlines() if "error" in line.lower()]
    return part, result.returncode == 0, (errors[0].strip()[:110] if errors else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("platforms", nargs="*", help="limit to these platforms (default: all)")
    ap.add_argument("-j", "--jobs", type=int, default=6)
    args = ap.parse_args()

    failures = 0
    for platform, parts in parts_by_platform().items():
        if args.platforms and platform not in args.platforms:
            continue
        compiler = resolve(parts[0])["desc"]["toolchain"]["prefix"] + "gcc"
        if shutil.which(compiler) is None:
            print(f"{platform}: {compiler} not found, skipped {len(parts)} part(s)")
            continue
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(build, parts))
        broken = [(part, why) for part, ok, why in results if not ok]
        print(f"{platform}: {len(parts) - len(broken)}/{len(parts)} listed parts build")
        for part, why in broken:
            print(f"  FAIL {part}: {why}")
        failures += len(broken)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
