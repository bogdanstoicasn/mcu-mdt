"""
INSTALL TEST FOR MCU-MDT: the package as pip installs it

Builds the project into a fresh virtual environment, then runs one golden case through the
installed `mcu-mdt` command from a directory outside the repository. It fails when a file the
tool needs at run time (commands.yaml, an ATDF/SVD) is missing from the package, or when the
tool only works from the repository root.

Needs network access for pip's isolated build (it downloads setuptools); skipped without it.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from test.common import fake_mcu
from test.common.asserts import assert_eq
from test.golden.golden_cases import cases, contract, expected_path, run_case

_REPO = Path(__file__).resolve().parents[2]
_NOT_PACKAGED = shutil.ignore_patterns(".git", "build", "logs", "__pycache__", "*.egg-info", ".ruff_cache")


def test_installed_tool_runs_from_anywhere():
    with tempfile.TemporaryDirectory() as tmp:
        source, venv = Path(tmp) / "source", Path(tmp) / "venv"
        shutil.copytree(_REPO, source, ignore=_NOT_PACKAGED)    # a clean tree: the repo's build/ is firmware
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        install = subprocess.run([str(venv / "bin" / "pip"), "install", "--quiet", str(source)],
                                 capture_output=True, text=True)
        if install.returncode != 0:
            print(f"  [SKIP] pip could not build the package (offline?): {install.stderr.strip()[-200:]}")
            return

        server, port = fake_mcu.serve()
        try:
            part, name, script = next(c for c in cases() if c[:2] == ("f030f4", "happy"))
            got = contract(run_case(part, script, port, tool=[str(venv / "bin" / "mcu-mdt")]))
        finally:
            server.close()
        assert_eq(got, expected_path(part, name).read_text().splitlines(), case="installed f030f4 happy")
