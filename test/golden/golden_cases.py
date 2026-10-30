"""The golden corpus: what the PC tool is run with, and the part of its log that must not change.

Each case is one `mcu_mdt.py <build_info> --script <case>` run against test/common/fake_mcu.py:
one script per part that uses every command. Refused lines are covered by the unit tests of
command_parser and command_rules, which run in milliseconds instead of a process each.
The parts' build_info.yaml and ELF are frozen under fixtures/ so the cases do not depend on the
local toolchain.

The contract kept byte for byte: every packet on the wire (sent and received, as hex), every
WARNING/ERROR line, and how the script ended. INFO wording is free to change.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = Path(__file__).parent / "expected"
LAUNCHER = [sys.executable, str(Path(__file__).resolve().parents[2] / "mcu_mdt.py")]

HAPPY = """\
# every command once
PING
READ_MEM RAM {ram} 4
READ_MEM RAM {ram} 10
WRITE_MEM RAM {ram} 4 DEADBEEF
WRITE_MEM RAM {ram} 10 00112233445566778899
READ_REG {reg}
WRITE_REG {reg} 01
BREAKPOINT 0 ENABLED
BREAKPOINT 0 NEXT
BREAKPOINT 0 DISABLED
WATCHPOINT 0 ENABLED {ram}
WATCHPOINT 0 MASK 000000FF
WATCHPOINT 0 RESET 0
WATCHPOINT 0 RESET
{extra}
HELP
RESET
"""

PARTS = {
    "atmega328p": dict(ram="0x0200", reg="PORTB",
                       extra="READ_MEM EEPROM 0x0010 4\nREAD_MEM FLASH 0x0000 4\n"
                             "WATCHPOINT 1 ENABLED rx_buffer"),
    "f030f4": dict(ram="0x20000200", reg="GPIOA_ODR",
                   extra="READ_MEM FLASH 0x08000000 8\nWRITE_MEM ERASE 0x08003C00 1 00\n"
                         "WRITE_MEM FLASH 0x08003C00 4 CAFEBABE\nWATCHPOINT 1 ENABLED packet_buffer"),
    "f103c8": dict(ram="0x20000200", reg="USART1_BRR",
                   extra="READ_REG TIM1_CCMR1_Output\nWRITE_MEM ERASE 0x0800FC00 1 00\n"
                         "WATCHPOINT 1 ENABLED packet_buffer"),
}


def cases() -> list[tuple[str, str, str]]:
    """(part, case name, script) for every golden run."""
    return [(part, "happy", HAPPY.format(**values)) for part, values in PARTS.items()]


def run_case(part: str, script: str, port: int, tool: list[str] = LAUNCHER) -> str:
    """Run the tool on one script against the fake MCU at *port*; return the session log."""
    return run_tool(part, script, port, tool)[0]


def run_tool(part: str, script: str, port: int, tool: list[str] = LAUNCHER) -> tuple[str, int]:
    """Run the tool on one script against the fake MCU at *port*; return (session log, exit status)."""
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        info = yaml.safe_load((FIXTURES / part / "build_info.yaml").read_text())
        info["port"] = f"socket://localhost:{port}"
        info["elf"] = str(FIXTURES / part / info["elf"])
        (work / "build_info.yaml").write_text(yaml.safe_dump(info, sort_keys=False))
        (work / "script.txt").write_text(script)
        done = subprocess.run([*tool, "build_info.yaml", "--script", "script.txt"], cwd=work,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        logs = sorted((work / "logs").glob("*.log"))
        return (logs[0].read_text() if logs else ""), done.returncode


def expected_path(part: str, name: str) -> Path:
    return EXPECTED / part / f"{name}.txt"


_WIRE = re.compile(r"\b(aa[0-9a-f]{34})\b")


def contract(log: str) -> list[str]:
    """The lines of a session log that the rework must keep exactly."""
    kept = []
    for line in log.splitlines():
        line = re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", line)
        if line.startswith(("[WARNING]", "[ERROR]")) or "Script aborted" in line or "Script complete" in line:
            kept.append(line)
        elif "Received packet" not in line:                 # the decoded repr of a packet already kept
            kept += [f"wire {packet}" for packet in _WIRE.findall(line)]
    return kept
