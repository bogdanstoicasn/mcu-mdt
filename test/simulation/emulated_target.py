"""One emulated MCU for the simulation tests: build the validation firmware, start the emulator,
stop it at exit.

    MDT_SIM=f103c8 python3 -m test.pymdtest simulation

MDT_SIM picks the target (one per run: two emulators on a small machine starve each other):

    f103c8      Renode, STM32F103C8, UART-idle (interrupt) mode
    f030f4      Renode, STM32F030F4, poll mode (Renode's F0 USART has no IDLE interrupt)
    atmega328p  simavr, ATmega328P @ 16 MHz, poll mode

Needs the target's toolchain, and Renode (`renode` on PATH, or RENODE=<path to renode>) or simavr
(gcc with libsimavr-dev, libelf-dev). Without MDT_SIM every simulation test skips.

The firmware is test/simulation/validation_main.c, linked against build/<part>/lib*.a like a user
project. Building runs `make MCU=<part> lib` (F030F4 with UART_IDLE=0), which regenerates
build/<part>/ with those settings.
"""

import atexit
import os
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "build" / "sim"

TARGETS = {
    "f103c8": dict(mcu="F103C8", emulator="renode", resc="stm32f103.resc", uart_idle=True, flash=True),
    "f030f4": dict(mcu="F030F4", emulator="renode", resc="stm32f030.resc", uart_idle=False, flash=True,
                   settings=["UART_IDLE=0"]),
    "atmega328p": dict(mcu="atmega328p", emulator="simavr", f_cpu=16000000, uart_idle=False, flash=False),
}

@dataclass
class Emulated:
    name: str
    port: int
    build_info: Path
    elf: Path
    uart_idle: bool
    flash: bool                     # flash erase and write can be tried (they fail in Renode: no flash controller)
    process: subprocess.Popen

    @property
    def url(self) -> str:
        return f"socket://localhost:{self.port}"


_running: Emulated | None = None
_failure: str | None = None


def selected() -> str | None:
    return os.environ.get("MDT_SIM") or None


def target() -> Emulated:
    """The running emulated target, started on first use. Raises RuntimeError if it can't start."""
    global _running, _failure
    if _running is None and _failure is None:
        try:
            _running = _start(selected())
            atexit.register(_stop)
        except Exception as exc:
            _failure = f"{type(exc).__name__}: {exc}"
    if _failure:
        raise RuntimeError(f"emulated target {selected()} did not start: {_failure}")
    return _running


def _start(name: str) -> Emulated:
    spec = TARGETS[name]
    part = spec["mcu"].lower()
    elf = _build_firmware(part, spec)
    port = _free_port()
    out = WORK / part
    log = open(out / "emulator.log", "w")    # noqa: SIM115 - the emulator writes to it until it stops
    if spec["emulator"] == "renode":
        renode = os.environ.get("RENODE") or shutil.which("renode")
        if not renode:
            raise RuntimeError("Renode not found: put renode on PATH or set RENODE")
        resc = out / "validation.resc"
        resc.write_text(_resc(spec["resc"], part, elf, port))
        cmd = [renode, "--disable-gui", "-P", str(_free_port()), str(resc)]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    else:
        bridge = _build_avr_bridge()
        cmd = [str(bridge), part, str(spec["f_cpu"]), str(elf), str(port)]
        process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    _wait_for_port(port, process, timeout=90)
    time.sleep(1.0)                 # let the firmware run mcu_mdt_init()
    return Emulated(name, port, ROOT / "build" / part / "build_info.yaml", elf, spec["uart_idle"], spec["flash"], process)


def _resc(name: str, part: str, elf: Path, port: int) -> str:
    """test/simulators/<name> with the validation firmware, the UART on *port*, and no GDB server."""
    lines = []
    for line in (ROOT / "test" / "simulators" / name).read_text().splitlines():
        if "StartGdbServer" in line:
            continue
        line = line.replace(f"@build/{part}/mcu_mdt_example.elf", f"@{elf}")
        if "CreateServerSocketTerminal" in line:
            line = f'emulation CreateServerSocketTerminal {port} "uart_term" false'
        lines.append(line)
    return "\n".join(lines) + "\n"


def _stop() -> None:
    if _running and _running.process.poll() is None:
        _running.process.terminate()
        try:
            _running.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _running.process.kill()


def _build_firmware(part: str, spec: dict) -> Path:
    """build/<part>/lib*.a with make, then validation_main.c linked against it like a user project."""
    _run(["make", f"MCU={spec['mcu']}", *spec.get("settings", []), "lib"], cwd=ROOT)
    mk = dict(_make_vars(ROOT / "build" / part / "build.mk"))
    build = ROOT / "build" / part
    out = WORK / part
    out.mkdir(parents=True, exist_ok=True)
    elf = out / "validation.elf"
    ldflags = [f for f in shlex.split(mk["LDFLAGS"]) if not f.startswith("-Wl,-Map=") and f != "-Wl,--print-gc-sections"]
    cmd = [mk["CC"], *shlex.split(mk["CFLAGS"]), f"-I{mk['INC_DIR']}", f"-I{mk['HAL_DIR']}", f"-I{build}",
           "-include", str(build / "mdt_target.h"), *ldflags, *shlex.split(mk.get("STARTUP", "")),
           str(Path(__file__).with_name("validation_main.c")), f"-L{build}", f"-l{mk['LIB']}",
           *shlex.split(mk.get("LDLIBS", "")), "-o", str(elf)]
    _run(cmd, cwd=ROOT)
    return elf


def _build_avr_bridge() -> Path:
    out = WORK / "avr_uart_tcp"
    source = ROOT / "test" / "simulators" / "avr_uart_tcp.c"
    if not out.exists() or out.stat().st_mtime < source.stat().st_mtime:
        out.parent.mkdir(parents=True, exist_ok=True)
        _run(["gcc", "-O2", "-o", str(out), str(source), "-lsimavr", "-lelf"], cwd=ROOT)
    return out


def _make_vars(path: Path):
    for line in path.read_text().splitlines():
        if " := " in line and not line.startswith("#"):
            key, value = line.split(" := ", 1)
            yield key.strip(), value.strip()


def _run(cmd, cwd):
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"{' '.join(map(str, cmd[:3]))} ... failed:\n{(done.stdout + done.stderr)[-1500:]}")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the emulator exited with {process.returncode}")
        try:
            # a probe connection the emulator then drops; Renode and the bridge take the next one
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"nothing listened on port {port} after {timeout:.0f} s")


def skip() -> bool:
    """True (after saying so) when no target is selected."""
    if selected() is None:
        print("  [SKIP] MDT_SIM not set (f103c8, f030f4 or atmega328p)")
        return True
    return False


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="mdtsim-"))
