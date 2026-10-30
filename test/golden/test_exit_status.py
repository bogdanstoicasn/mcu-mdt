"""
EXIT STATUS TESTS FOR MCU-MDT (bug 6): a script run closes the link and says how it ended

The tool runs as a user runs it, against test/common/fake_mcu.py. Exit status 0 means every line
ran; 1 means the build could not be loaded, the port could not be opened, or the script stopped
at an error. Either way the link is closed and the log gets its footer.
"""

import subprocess
import sys

from test.common import fake_mcu
from test.common.asserts import assert_eq
from test.golden.golden_cases import LAUNCHER, run_tool
from test.pymdtest import parametrize

_SERVER, _PORT = fake_mcu.serve()


@parametrize("script,status", [
    ("PING\nREAD_MEM RAM 0x20000200 4\n", 0),
    ("PING\nNOPE\nPING\n", 1),
    ("BREAKPOINT 9 ENABLED\n", 1),
])
def test_script_exit_status_and_clean_close(script, status):
    log, returncode = run_tool("f030f4", script, _PORT)
    assert_eq(returncode, status, script=script)
    assert "Debugger closed." in log, log[-500:]
    assert_eq(log.rstrip().splitlines()[-2].endswith("MCU-MDT SESSION END"), True)


def test_a_build_that_cannot_be_loaded_exits_1():
    done = subprocess.run([*LAUNCHER, "/no/such/build_info.yaml"], capture_output=True, text=True, timeout=60)
    assert_eq(done.returncode, 1)
    assert "ERROR: Cannot load the build: Config file not found" in done.stdout, done.stdout


def test_python_dash_m_runs_the_tool():
    done = subprocess.run([sys.executable, "-m", "pc_tool", "--help"], capture_output=True, text=True, timeout=60)
    assert_eq(done.returncode, 0)
    assert "build_info" in done.stdout, done.stdout
