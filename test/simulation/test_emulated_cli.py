"""
EMULATED CLI TESTS: `mcu_mdt.py` as a user runs it, on a pseudo-terminal or with a script,
against the validation firmware in Renode or simavr

    MDT_SIM=f103c8 python3 -m test.pymdtest simulation       (see emulated_target.py)

Coverage:
1. The prompt: TAB completion, history in ~/.mcu_mdt_history, up arrow, Ctrl-C and Ctrl-D exits
2. An event arriving while a line is half typed: printed above it, the line kept
3. An idle session uses almost no CPU (bug 3)
4. An unplugged cable at the prompt: exit 1 with the log footer and the history saved (bug 4)
5. A corrupted reply in a script is resent (bug 1)
6. Exit status: 0 for a clean script, 1 for an error line, a missing script, --elf or port (bug 6)
"""

import os
import pty
import re
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

from test.common import fault_proxy as fp
from test.common.asserts import assert_eq
from test.simulation import emulated_target as emu

LAUNCHER = emu.ROOT / "mcu_mdt.py"
_SCREEN = re.compile(r"\x1b(\[[0-9;?]*[A-Za-z]|[=>]|\][^\x07]*\x07)|\r|\x07")   # terminal codes, CR, bell


def _workdir(port: int | None = None) -> Path:
    t = emu.target()
    work = emu.temp_dir()
    info = yaml.safe_load(t.build_info.read_text())
    info.update(port=f"socket://localhost:{port or t.port}", elf=str(t.elf))
    (work / "build_info.yaml").write_text(yaml.safe_dump(info))
    (work / "home").mkdir()
    return work


def _log(work: Path) -> str:
    logs = sorted((work / "logs").glob("*.log"))
    return logs[-1].read_text() if logs else ""


class _Terminal:
    """The tool on a pseudo-terminal. Keys are sent at human speed: libedit drops keys sent in one burst."""

    def __init__(self, work: Path, args=()):
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(work)
            env = {**os.environ, "HOME": str(work / "home"), "TERM": "xterm", "COLUMNS": "100"}
            os.execve(sys.executable, [sys.executable, str(LAUNCHER), "build_info.yaml", *args], env)
        self.pid, self.fd, self.raw, self.rc = pid, fd, "", None

    def _read(self, timeout: float) -> None:
        if select.select([self.fd], [], [], timeout)[0]:
            try:
                self.raw += os.read(self.fd, 65536).decode(errors="replace")
            except OSError:                              # the tool closed the terminal
                time.sleep(timeout)

    @property
    def screen(self) -> str:
        return _SCREEN.sub("", self.raw)

    def expect(self, pattern: str, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while not re.search(pattern, self.screen):
            if time.monotonic() > deadline:
                raise AssertionError(f"never saw {pattern!r} in:\n{self.screen[-1200:]}")
            self._read(0.1)

    def keys(self, text: str) -> None:
        time.sleep(0.2)
        os.write(self.fd, text.encode())

    def wait(self, timeout: float = 10.0) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._read(0.05)
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.rc = os.waitstatus_to_exitcode(status)
                return self.rc
        self.kill()
        raise AssertionError(f"the tool did not exit:\n{self.screen[-800:]}")

    def kill(self) -> None:
        if self.rc is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
            self.rc = -9

    def cpu_seconds(self) -> float:
        fields = Path(f"/proc/{self.pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def _script(work: Path, text: str, *args) -> tuple[int, str]:
    (work / "s.txt").write_text(text)
    done = subprocess.run([sys.executable, str(LAUNCHER), "build_info.yaml", "--script", "s.txt", *args], cwd=work,
                          capture_output=True, text=True, timeout=120, env={**os.environ, "HOME": str(work / "home")})
    return done.returncode, done.stdout + done.stderr


# ---------------------------------------------------------------- 1. the prompt

def test_tab_completion_history_and_ctrl_c():
    if emu.skip():
        return
    work = _workdir()
    term = _Terminal(work)
    try:
        term.expect(r"> $")
        term.keys("PIN\t")
        term.expect(r"> PING")
        term.keys("\n")
        term.expect(r"Command  : PING")
        term.keys("READ_\t\t")
        term.expect(r"READ_MEM\s+READ_REG")
        term.keys("MEM RAM quiet_word 4\n")
        term.expect(r"Data     : 44 33 22 11")
        term.keys("\x1b[A")                               # up arrow: the last line again
        term.expect(r"Data     : 44 33 22 11(.|\n)*> READ_MEM RAM quiet_word 4")
        term.keys("\x15")                                 # Ctrl-U clears it
        term.keys("\x03")                                 # Ctrl-C at the prompt
        assert_eq(term.wait(), 0)
    finally:
        term.kill()
    assert "Exiting..." in term.screen and "Debugger closed." in term.screen, term.screen[-300:]
    history = (work / "home" / ".mcu_mdt_history").read_text().replace("\\040", " ")    # libedit escapes spaces
    assert "PING" in history and "READ_MEM RAM quiet_word 4" in history, history
    assert "MCU-MDT SESSION END" in _log(work)


def test_ctrl_d_exits_cleanly():
    if emu.skip():
        return
    work = _workdir()
    term = _Terminal(work)
    try:
        term.expect(r"> $")
        term.keys("\x04")
        assert_eq(term.wait(), 0)
    finally:
        term.kill()
    assert "MCU-MDT SESSION END" in _log(work)


# ---------------------------------------------------------------- 2. events at the prompt

def test_an_event_keeps_the_half_typed_line():
    if emu.skip():
        return
    term = _Terminal(_workdir())
    try:
        term.expect(r"> $")
        term.keys("WATCHPOINT 0 ENABLED loop_count\n")
        term.expect(r"\[ACK\]")
        term.keys("READ_M")
        term.expect(r"WATCHPOINT_HIT.*\n> READ_M", timeout=6)     # the event, then the prompt and what was typed
        term.keys("EM RAM quiet_word 4\n")                         # readline still holds "READ_M"
        term.expect(r"Data     : 44 33 22 11")
        term.keys("WATCHPOINT 0 RESET\nEXIT\n")
        assert_eq(term.wait(), 0)
    finally:
        term.kill()


# ---------------------------------------------------------------- 3. idle CPU

def test_an_idle_session_uses_almost_no_cpu():
    if emu.skip():
        return
    term = _Terminal(_workdir())
    try:
        term.expect(r"> $")
        time.sleep(1.0)
        before = term.cpu_seconds()
        time.sleep(5.0)
        used = term.cpu_seconds() - before
        term.keys("EXIT\n")
        term.wait()
    finally:
        term.kill()
    assert used < 0.5, f"{used:.2f} s of CPU in 5 s idle"


# ---------------------------------------------------------------- 4. unplugged

def test_unplugged_cable_at_the_prompt_exits_1_cleanly():
    if emu.skip():
        return
    proxy = fp.FaultProxy(emu.target().port)
    work = _workdir(proxy.port)
    term = _Terminal(work)
    try:
        term.expect(r"> $")
        term.keys("PING\n")
        term.expect(r"Command  : PING")
        proxy.unplug()
        assert_eq(term.wait(timeout=8), 1)
    finally:
        term.kill()
        proxy.close()
    assert "Board disconnected" in term.screen, term.screen[-400:]
    assert "MCU-MDT SESSION END" in _log(work)
    assert (work / "home" / ".mcu_mdt_history").exists()


# ---------------------------------------------------------------- 5.-6. scripts

def test_a_corrupted_reply_in_a_script_is_resent():
    if emu.skip():
        return
    proxy = fp.FaultProxy(emu.target().port)
    proxy.fault = fp.nth_reply(2, fp.flip_crc)                # the 1st reply is the startup ping's echo
    work = _workdir(proxy.port)
    try:
        rc, out = _script(work, "READ_MEM RAM quiet_word 4\nREAD_MEM RAM quiet_word 4\n")
    finally:
        proxy.close()
    assert_eq(rc, 0, output=out[-500:])
    assert "Traceback" not in out, out
    assert_eq(len(re.findall(r"Received ACK: aa01", _log(work))), 2)


def test_exit_status():
    if emu.skip():
        return
    work = _workdir()
    script = "\n".join(["PING", "READ_MEM RAM quiet_word 4", "WRITE_MEM RAM scratch 8 0102030405060708",
                        "READ_MEM RAM scratch 8", "BREAKPOINT 1 ENABLED", "BREAKPOINT 1 DISABLED",
                        "WATCHPOINT 0 ENABLED quiet_word", "WATCHPOINT 0 MASK 000000FF", "WATCHPOINT 0 RESET",
                        "HELP", "# a comment", "", "READ_MEM RAM calls 4"]) + "\n"
    assert_eq(_script(work, script)[0], 0)
    log = _log(work)
    assert_eq(len(re.findall(r"Received ACK", log)), 12)       # the 8-byte write and read are 2 packets each
    assert "Skipping PC-only command at line 10: HELP" in log
    assert_eq(_script(work, "PING\nREAD_REG NOT_A_REGISTER\nPING\n")[0], 1)
    rc, out = _script(work, "PING\n", "--elf", "missing.elf")
    assert rc == 1 and "--elf missing.elf: no such file" in out, (rc, out[-300:])
    missing = subprocess.run([sys.executable, str(LAUNCHER), "build_info.yaml", "--script", "nope.txt"], cwd=work,
                             capture_output=True, text=True, timeout=60)
    assert_eq(missing.returncode, 1)
    rc, out = _script(_workdir(port=1), "PING\n")                # nothing listens on port 1
    assert rc == 1 and "Failed to open serial link" in out, (rc, out[-300:])
