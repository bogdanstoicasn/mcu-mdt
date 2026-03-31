from test.common.asserts import assert_eq
from pc_tool.common.enums import CommandId, MemType, BreakpointControl, WatchpointControl
from pc_tool.parser import parse_line
from test.pymdtest import parametrize


COMMANDS = {
    "PING": {"id": 0x05, "params": []},

    "READ_MEM": {
        "id": 0x01,
        "params": [
            {"name": "control_value", "type": "str"},
            {"name": "address", "type": "uint32"},
            {"name": "len", "type": "uint32"},
        ]
    },

    "WRITE_MEM": {
        "id": 0x02,
        "params": [
            {"name": "control_value", "type": "str"},
            {"name": "address", "type": "uint32"},
            {"name": "len", "type": "uint32"},
            {"name": "data", "type": "bytes"},
        ]
    },

    "READ_REG": {
        "id": 0x03,
        "params": [{"name": "address", "type": "uint32_or_str"}]
    },

    "WRITE_REG": {
        "id": 0x04,
        "params": [
            {"name": "address", "type": "uint32_or_str"},
            {"name": "data", "type": "bytes"},
        ]
    },

    "BREAKPOINT": {
        "id": 0x0A,
        "params": [
            {"name": "address", "type": "uint32"},
            {"name": "control_value", "type": "str"},
        ]
    },

    "WATCHPOINT": {
        "id": 0x0B,
        "params": [
            {"name": "address", "type": "uint32"},
            {"name": "control_value", "type": "str"},
            {"name": "data", "type": "bytes"},
        ]
    },
}

CONTROL_VALUES = {
    "RAM": 0, "FLASH": 1, "EEPROM": 2,
    "DISABLED": 0, "ENABLED": 1, "RESET": 2, "NEXT": 3,
    "MASK": 3,
}

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
    cmd = _parse("READ_MEM RAM 536870912 4")
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
    cmd = _parse("WATCHPOINT 0 ENABLED 20000100")
    assert_eq(cmd.data, b'\x00\x01\x00\x20')


def test_parse_watchpoint_invalid():
    assert_eq(_parse("WATCHPOINT 0 ENABLED"), None)