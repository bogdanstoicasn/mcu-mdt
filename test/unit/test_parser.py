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
from pc_tool.parser import parse_line, resolve_register_address
from test.pymdtest import parametrize
from test.common.mdtfixtures import CONTROL_VALUES, COMMANDS, MCU_METADATA_REG, MCU_METADATA_AVR

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


def _parse_with_reg_meta(line: str):
    return parse_line(line, COMMANDS, CONTROL_VALUES, MCU_METADATA_REG)


# PERIPHERAL_REGISTER qualified name resolution
# MCU_METADATA_REG has USART1 at 0x40013800 with SR=+0x00, DR=+0x04, BRR=+0x08

def test_parse_read_reg_by_qualified_name():
    """USART1_SR should resolve to USART1 base + SR offset = 0x40013800."""
    cmd = _parse_with_reg_meta("READ_REG USART1_SR")
    assert_eq(cmd.id,      CommandId.READ_REG)
    assert_eq(cmd.address, 0x40013800)


def test_parse_read_reg_qualified_dr():
    """USART1_DR should resolve to 0x40013800 + 0x04."""
    cmd = _parse_with_reg_meta("READ_REG USART1_DR")
    assert_eq(cmd.address, 0x40013804)


def test_parse_read_reg_qualified_brr():
    """USART1_BRR should resolve to 0x40013800 + 0x08."""
    cmd = _parse_with_reg_meta("READ_REG USART1_BRR")
    assert_eq(cmd.address, 0x40013808)


def test_parse_read_reg_bare_name_fallback():
    """Bare 'SR' should still resolve via the fallback search."""
    cmd = _parse_with_reg_meta("READ_REG SR")
    assert_eq(cmd.address, 0x40013800)


def test_parse_read_reg_case_insensitive():
    """Qualified lookup is case-insensitive: 'usart1_sr' == 'USART1_SR'."""
    cmd = _parse_with_reg_meta("READ_REG usart1_sr")
    assert_eq(cmd.address, 0x40013800)


def test_parse_read_reg_unknown_qualified_falls_through_to_none():
    """Unknown peripheral in qualified name should return None → parse fails."""
    cmd = _parse_with_reg_meta("READ_REG RCC_CR")
    assert_eq(cmd, None)   # RCC not in MCU_METADATA_REG


def test_parse_write_reg_by_qualified_name():
    """WRITE_REG also uses uint32_or_str — qualified name must resolve."""
    cmd = _parse_with_reg_meta("WRITE_REG USART1_DR 000000FF")
    assert_eq(cmd.id,      CommandId.WRITE_REG)
    assert_eq(cmd.address, 0x40013804)
    assert_eq(cmd.data,    b'\x00\x00\x00\xFF')


def test_resolve_register_address_directly():
    """Unit test resolve_register_address without going through parse_line."""
    assert_eq(resolve_register_address("USART1_SR",  MCU_METADATA_REG), 0x40013800)
    assert_eq(resolve_register_address("USART1_DR",  MCU_METADATA_REG), 0x40013804)
    assert_eq(resolve_register_address("USART1_BRR", MCU_METADATA_REG), 0x40013808)
    assert_eq(resolve_register_address("SR",         MCU_METADATA_REG), 0x40013800)
    assert_eq(resolve_register_address("NONEXIST",   MCU_METADATA_REG), None)
    assert_eq(resolve_register_address("RCC_CR",     MCU_METADATA_REG), None)

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

# ── AVR register resolution ──────────────────────────────────────────────────
# AVR (ATDF) has:
#   - No instance offsets → register group base is 0
#   - Register "offset" is the absolute I/O address
#   - Register size in bytes (1 = 8-bit)
#   - Zero register names containing underscores (verified against all ATmega ATDFs)
# The two-stage lookup must not interfere with bare-name AVR lookups.

def _parse_with_avr_meta(line: str):
    return parse_line(line, COMMANDS, CONTROL_VALUES, MCU_METADATA_AVR)


def test_avr_bare_name_udr0():
    """UDR0 has no underscore — goes straight to bare-name search."""
    addr = resolve_register_address("UDR0", MCU_METADATA_AVR)
    assert_eq(addr, 0xC6)


def test_avr_bare_name_ucsr0a():
    addr = resolve_register_address("UCSR0A", MCU_METADATA_AVR)
    assert_eq(addr, 0xC0)


def test_avr_bare_name_twbr():
    """Register in a different module is found correctly."""
    addr = resolve_register_address("TWBR", MCU_METADATA_AVR)
    assert_eq(addr, 0xB8)


def test_avr_bare_name_twdr():
    addr = resolve_register_address("TWDR", MCU_METADATA_AVR)
    assert_eq(addr, 0xBB)


def test_avr_16bit_register_ubrr0():
    """16-bit register (size=2) still resolves to the correct base address."""
    addr = resolve_register_address("UBRR0", MCU_METADATA_AVR)
    assert_eq(addr, 0xC4)


def test_avr_case_insensitive():
    """AVR bare-name lookup is case-insensitive."""
    assert_eq(resolve_register_address("udr0",   MCU_METADATA_AVR), 0xC6)
    assert_eq(resolve_register_address("Ucsr0a", MCU_METADATA_AVR), 0xC0)


def test_avr_unknown_register_returns_none():
    addr = resolve_register_address("SPDR", MCU_METADATA_AVR)
    assert_eq(addr, None)   # SPI not in this fixture


def test_avr_read_reg_via_parse_line():
    """Full parse_line path: READ_REG with a bare AVR register name."""
    cmd = _parse_with_avr_meta("READ_REG UDR0")
    assert_eq(cmd.id,      CommandId.READ_REG)
    assert_eq(cmd.address, 0xC6)


def test_avr_write_reg_via_parse_line():
    """WRITE_REG with a bare AVR register name."""
    cmd = _parse_with_avr_meta("WRITE_REG UCSR0A 00")
    assert_eq(cmd.id,      CommandId.WRITE_REG)
    assert_eq(cmd.address, 0xC0)


def test_avr_qualified_lookup_falls_through_when_no_module_match():
    """A hypothetical 'USART_UDR0' qualified form works too since USART IS a module.
    This is a bonus — AVR users don't need it but it's a consistent behaviour."""
    addr = resolve_register_address("USART_UDR0", MCU_METADATA_AVR)
    # 'USART' is in modules, 'UDR0' is in its register group → resolves correctly
    assert_eq(addr, 0xC6)


def test_avr_qualified_lookup_unknown_module_falls_to_bare():
    """If the prefix is not a known module, falls through to bare-name search."""
    # 'SPI_SPDR' — SPI is not in this fixture, bare 'SPI_SPDR' also not found
    addr = resolve_register_address("SPI_SPDR", MCU_METADATA_AVR)
    assert_eq(addr, None)