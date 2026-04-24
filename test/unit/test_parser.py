"""
COMMAND PARSER TESTS FOR MCU-MDT


Validates parsing of cli into structured commands.

Coverage:
1. Command recognition (case-insensitive, e.g. PING)
2. Invalid input handling
3. Memory commands (READ_MEM / WRITE_MEM)
4. Memory types (RAM, FLASH, EEPROM)
5. Address and length parsing
6. Data decoding
7. Register commands (READ_REG / WRITE_REG)
8. Breakpoint commands (ENABLED, DISABLED, RESET, NEXT)
9. Watchpoint commands (ENABLED, DISABLED, MASK)
10. Control value mapping to enums
11. Input validation (invalid data, missing params)

Setup:
1. COMMANDS dict defining command structure and expected parameters
2. CONTROL_VALUES dict mapping control strings to enum values
3. MCU_METADATA (empty, no hardware dependencies)

Goal:
Ensure that the command parser correctly translates user input into structured command objects with proper types and values.
"""

from test.common.asserts import assert_eq
from pc_tool.common.enums import CommandId, MemType, BreakpointControl, WatchpointControl
from pc_tool.parser import parse_line
from test.pymdtest import parametrize
from test.common.mdtfixtures import CONTROL_VALUES, COMMANDS

MCU_METADATA = {"modules": {}, "memories": {}}


def _parse(line: str):
    return parse_line(line, COMMANDS, CONTROL_VALUES, MCU_METADATA)


# PING
@parametrize("input,expected", [
    ("PING", "PING"),
    ("ping", "PING"),
])
def test_parse_ping(input, expected):
    cmd = _parse(input)
    assert_eq(cmd.name, expected)


@parametrize("input", [
    ("BAMBILICI",),
    ("",),
])
def test_parse_invalid_returns_none(input):
    assert_eq(_parse(input), None)


# READ_MEM
@parametrize("mem_str,expected", [
    ("RAM", MemType.RAM),
    ("FLASH", MemType.FLASH),
    ("EEPROM", MemType.EEPROM),
])
def test_parse_read_mem_memtypes(mem_str, expected):
    cmd = _parse(f"READ_MEM {mem_str} 0x20000000 4")
    assert_eq(cmd.mem, expected)

def test_parse_read_mem_decimal():
    cmd = _parse("READ_MEM RAM 0x20000000 4")
    assert_eq(cmd.address, 0x20000000)

# WRITE_MEM
@parametrize("data_str,expected", [
    ("DEADBEEF", b'\xDE\xAD\xBE\xEF'),
    ("0xDEADBEEF", b'\xDE\xAD\xBE\xEF'),
])
def test_parse_write_mem(data_str, expected):
    cmd = _parse(f"WRITE_MEM RAM 0x20000000 4 {data_str}")
    assert_eq(cmd.data, expected)


def test_parse_write_mem_invalid():
    assert_eq(_parse("WRITE_MEM RAM 0x20000000 4 ZZZZ"), None)


# REG
def test_parse_read_reg():
    cmd = _parse("READ_REG 0x40013800")
    assert_eq(cmd.id, CommandId.READ_REG)
    assert_eq(cmd.address, 0x40013800)


def test_parse_write_reg():
    cmd = _parse("WRITE_REG 0x40013800 000000FF")
    assert_eq(cmd.data, b'\x00\x00\x00\xFF')

# BREAKPOINT
@parametrize("ctrl,expected", [
    ("ENABLED", BreakpointControl.ENABLED),
    ("DISABLED", BreakpointControl.DISABLED),
    ("RESET", BreakpointControl.RESET),
    ("NEXT", BreakpointControl.NEXT),
])
def test_parse_breakpoint(ctrl, expected):
    cmd = _parse(f"BREAKPOINT 0 {ctrl}")
    assert_eq(cmd.mem, expected)


def test_parse_breakpoint_invalid():
    assert_eq(_parse("BREAKPOINT 0 INVALID"), None)


# WATCHPOINT
@parametrize("ctrl,expected", [
    ("ENABLED", WatchpointControl.ENABLED),
    ("DISABLED", WatchpointControl.DISABLED),
    ("MASK", WatchpointControl.MASK),
])
def test_parse_watchpoint(ctrl, expected):
    cmd = _parse(f"WATCHPOINT 0 {ctrl} 000000FF")
    assert_eq(cmd.mem, expected)


def test_parse_watchpoint_data():
    cmd = _parse("WATCHPOINT 0 ENABLED 0x20000100")
    assert_eq(cmd.data, b'\x00\x01\x00\x20')


def test_parse_watchpoint_invalid():
    assert_eq(_parse("WATCHPOINT 0 ENABLED"), None)