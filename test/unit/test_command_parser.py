"""
COMMAND PARSER TESTS (pc_tool/command_parser.py), with the shipped configs/commands.yaml

Coverage:
1. commands.yaml: every parameter has a known type and field; usage lines for HELP
2. Command names any case, unknown commands, blank lines, parameter counts, local commands
3. Numbers: hex and decimal parameters, hex data
4. Choices: each command takes only its own names (BREAKPOINT 0 MASK must not send NEXT)
5. Registers by address or name (qualified, bare, any case, AVR names, 16-bit AVR registers)
6. Symbols: exact, local statics (name.N), ambiguous, missing, no ELF; narrow variables warn
7. WATCHPOINT's value is optional; a number for the data field is sent as 4 little-endian bytes
"""

from pc_tool import command_parser
from pc_tool.command_parser import CommandError
from pc_tool.elf_symbols import Symbol
from pc_tool.wire_protocol import BreakpointControl, CommandId, MemType, WatchpointControl
from test.common.asserts import assert_eq, logged_warnings
from test.common.target_fixtures import AVR_PERIPHERALS, make_target, usart1
from test.pymdtest import parametrize

SPECS = command_parser.load_specs()
STM32 = make_target(peripherals=[usart1()])
AVR = make_target(peripherals=AVR_PERIPHERALS)
SYMBOLS = make_target(symbols={
    "counter": Symbol("counter", 0x20000010, 4),
    "flag": Symbol("flag", 0x20000014, 1),
    "state.0": Symbol("state.0", 0x20000018, 4),
    "tick.1": Symbol("tick.1", 0x20000020, 4), "tick.2": Symbol("tick.2", 0x20000024, 4),
})


def _parse(line: str, target=STM32):
    return command_parser.parse(line, SPECS, target)


def _error(line: str, target=STM32) -> tuple[str, int]:
    try:
        _parse(line, target)
    except CommandError as exc:
        return str(exc), exc.code
    raise AssertionError(f"{line!r} parsed")


# ---------------------------------------------------------------- 1. commands.yaml

def test_every_parameter_has_a_known_type_and_field():
    for spec in SPECS.values():
        assert_eq(spec.local, spec.id is None, command=spec.name)
        for param in spec.params:
            assert param.type in command_parser._READERS, (spec.name, param.type)
            assert param.field in ("mem", "address", "length", "data"), (spec.name, param.field)
            assert_eq(param.values is not None, param.type == "choice", command=spec.name, param=param.name)
        optional = [p.optional for p in spec.params]
        assert_eq(optional, sorted(optional), command=spec.name, what="optional parameters come last")


def test_usage_lines():
    assert_eq(SPECS["READ_MEM"].usage, "READ_MEM <RAM|FLASH|EEPROM> <addr> <length>")
    assert_eq(SPECS["WATCHPOINT"].usage, "WATCHPOINT <id> <ENABLED|DISABLED|RESET|MASK> [<symbol|addr|mask>]")
    assert_eq(SPECS["PING"].usage, "PING")


# ---------------------------------------------------------------- 2. names and counts

@parametrize("line", [("PING",), ("ping",), ("  Ping  ",)])
def test_command_names_any_case(line):
    command = _parse(line)
    assert_eq((command.name, command.id), ("PING", CommandId.PING))


def test_blank_line_is_no_command():
    assert_eq(_parse("   "), None)


@parametrize("line,error", [
    ("BAMBILICI",            ("Unknown command: BAMBILICI", 3)),
    ("PING 1",               ("PING expects 0 parameter(s), got 1", 2)),
    ("READ_MEM RAM",         ("READ_MEM expects 3 parameter(s), got 1", 2)),
    ("WATCHPOINT 0",         ("WATCHPOINT expects 2 to 3 parameter(s), got 1", 2)),
    ("WATCHPOINT 0 MASK 1 2", ("WATCHPOINT expects 2 to 3 parameter(s), got 4", 2)),
    ("HELP me",              ("HELP expects 0 parameter(s), got 1", 2)),
])
def test_unknown_commands_and_wrong_counts(line, error):
    assert_eq(_error(line), error)


def test_local_commands_parse_but_have_no_id():
    for name in ("EXIT", "HELP", "CLEAR"):
        command = _parse(name.lower())
        assert_eq((command.name, command.id, SPECS[name].local), (name, None, True))


# ---------------------------------------------------------------- 3. numbers

def test_read_mem_address_is_hex_and_length_decimal():
    command = _parse("READ_MEM RAM 20000000 10")
    assert_eq((command.mem, command.address, command.length), (MemType.RAM, 0x20000000, 10))
    assert_eq(_parse("READ_MEM RAM 0x20000000 0x10").length, 16)


@parametrize("data,expected", [("DEADBEEF", b"\xDE\xAD\xBE\xEF"), ("0xDEADBEEF", b"\xDE\xAD\xBE\xEF")])
def test_write_mem_data(data, expected):
    command = _parse(f"WRITE_MEM RAM 0x20000000 4 {data}")
    assert_eq((command.id, command.data, command.length), (CommandId.WRITE_MEM, expected, 4))


@parametrize("line,error", [
    ("WRITE_MEM RAM 0x20000000 4 ZZZZ", "Invalid hex data for data: 'ZZZZ'"),
    ("READ_MEM RAM 0x20000000 four",    "Invalid value 'four' for len"),
    ("BREAKPOINT zz ENABLED",           "Invalid value 'zz' for address"),
])
def test_bad_numbers(line, error):
    assert_eq(_error(line), (error, 2))


def test_slot_ids_are_hex():
    assert_eq(_parse("BREAKPOINT 10 ENABLED").address, 0x10)


# ---------------------------------------------------------------- 4. choices

@parametrize("line,mem", [
    ("READ_MEM ram 0 4",            MemType.RAM),
    ("READ_MEM FLASH 0 4",          MemType.FLASH),
    ("READ_MEM EEPROM 0 4",         MemType.EEPROM),
    ("WRITE_MEM ERASE 0 1 00",      MemType.ERASE),
    ("BREAKPOINT 0 ENABLED",        BreakpointControl.ENABLED),
    ("BREAKPOINT 0 disabled",       BreakpointControl.DISABLED),
    ("BREAKPOINT 0 RESET",          BreakpointControl.RESET),
    ("BREAKPOINT 0 NEXT",           BreakpointControl.NEXT),
    ("WATCHPOINT 0 ENABLED 0",      WatchpointControl.ENABLED),
    ("WATCHPOINT 0 DISABLED",       WatchpointControl.DISABLED),
    ("WATCHPOINT 0 MASK 000000FF",  WatchpointControl.MASK),
])
def test_choices_send_their_own_numbers(line, mem):
    assert_eq(_parse(line).mem, mem)


@parametrize("line,expected", [
    ("BREAKPOINT 0 MASK",             "DISABLED, ENABLED, RESET, NEXT"),   # MASK == NEXT == 3: used to send NEXT
    ("BREAKPOINT 0 FLASH",            "DISABLED, ENABLED, RESET, NEXT"),   # FLASH == ENABLED == 1
    ("READ_MEM ENABLED 0x08000000 4", "RAM, FLASH, EEPROM"),               # used to read FLASH
    ("READ_MEM ERASE 0x08000000 4",   "RAM, FLASH, EEPROM"),               # ERASE is a write-only zone
    ("WATCHPOINT 0 NEXT 0x20000000",  "DISABLED, ENABLED, RESET, MASK"),   # used to set the mask
    ("WATCHPOINT 0 RAM 0x20000000",   "DISABLED, ENABLED, RESET, MASK"),
])
def test_names_of_another_command_are_rejected(line, expected):
    word = line.split()[2] if line.startswith(("BREAKPOINT", "WATCHPOINT")) else line.split()[1]
    assert_eq(_error(line), (f"Invalid control value '{word}'. Expected one of: {expected}", 2))


# ---------------------------------------------------------------- 5. registers

@parametrize("name,address", [
    ("0x40013800", 0x40013800),
    ("USART1_SR",  0x40013800),
    ("USART1_DR",  0x40013804),
    ("USART1_BRR", 0x40013808),
    ("SR",         0x40013800),     # bare name
    ("usart1_sr",  0x40013800),     # any case
])
def test_register_by_address_or_name(name, address):
    assert_eq(_parse(f"READ_REG {name}").address, address)


def test_write_reg_by_name():
    command = _parse("WRITE_REG USART1_DR 000000FF")
    assert_eq((command.id, command.address, command.data), (CommandId.WRITE_REG, 0x40013804, b"\x00\x00\x00\xFF"))


@parametrize("name,address", [
    ("UDR0", 0xC6), ("UCSR0A", 0xC0), ("Ucsr0a", 0xC0), ("TWBR", 0xB8), ("TWDR", 0xBB),
    ("UBRR0", 0xC4),                # 16-bit register: its low address
    ("USART_UDR0", 0xC6),           # the ATDF module name qualifies too
])
def test_avr_register_names(name, address):
    assert_eq(_parse(f"READ_REG {name}", AVR).address, address)


@parametrize("name,target", [("RCC_CR", STM32), ("SPDR", AVR), ("SPI_SPDR", AVR)])
def test_unknown_register_names(name, target):
    assert_eq(_error(f"READ_REG {name}", target), (f"Unknown register name '{name}'", 2))


# ---------------------------------------------------------------- 6. symbols

def test_symbols_exact_and_local_static():
    assert_eq(_parse("READ_MEM RAM counter 4", SYMBOLS).address, 0x20000010)
    assert_eq(_parse("WATCHPOINT 0 ENABLED state", SYMBOLS).data, (0x20000018).to_bytes(4, "little"))
    assert_eq(_parse("WATCHPOINT 0 ENABLED tick.2", SYMBOLS).data, (0x20000024).to_bytes(4, "little"))


def test_symbol_errors():
    message, code = _error("WATCHPOINT 0 ENABLED tick", SYMBOLS)
    assert "Ambiguous symbol 'tick'" in message and "tick.1, tick.2" in message and code == 2, message
    message, _ = _error("WATCHPOINT 0 ENABLED nope", SYMBOLS)
    assert message.startswith("Symbol 'nope' not found in ELF symbol table."), message
    message, _ = _error("WATCHPOINT 0 ENABLED counter", STM32)
    assert message.startswith("Cannot resolve symbol 'counter': no ELF loaded."), message


def test_a_variable_narrower_than_the_sampled_word_warns():
    with logged_warnings("pc_tool.command_parser") as warnings:
        _parse("WATCHPOINT 0 ENABLED counter", SYMBOLS)
        assert_eq(warnings, [])
        _parse("WATCHPOINT 0 ENABLED flag", SYMBOLS)
    assert_eq(len(warnings), 1)
    assert "'flag' is uint8_t" in warnings[0] and "MASK 0x000000FF" in warnings[0], warnings


# ---------------------------------------------------------------- 7. WATCHPOINT's value

def test_watchpoint_value_is_four_little_endian_bytes():
    assert_eq(_parse("WATCHPOINT 0 ENABLED 0x20000100").data, b"\x00\x01\x00\x20")
    assert_eq(_parse("WATCHPOINT 1 MASK 000000FF").data, b"\xFF\x00\x00\x00")


def test_watchpoint_value_may_be_left_out():
    command = _parse("WATCHPOINT 0 RESET")
    assert_eq((command.address, command.mem, command.data), (0, WatchpointControl.RESET, None))
