"""
COMMAND RULES TESTS (pc_tool/command_rules.py)

Coverage:
1. READ_MEM / WRITE_MEM stay inside a segment of the right kind, data length matches
2. Flash writes and erases stay off the running firmware; an erase covers its whole page
3. READ_REG / WRITE_REG land on a register, every byte of it; writes need a writable one
4. Breakpoint and watchpoint slots exist in the firmware built; control values are known
5. WATCHPOINT ENABLED needs a watch address in RAM or on a register; unaligned ones warn
"""

from pc_tool import command_rules
from pc_tool.command_parser import CommandError
from pc_tool.wire_protocol import BreakpointControl, Command, CommandId, MemType, WatchpointControl
from test.common.asserts import assert_eq, logged_warnings
from test.common.target_fixtures import (
    AVR_PERIPHERALS,
    eeprom,
    firmware,
    flash,
    make_target,
    ram,
    usart1,
)
from test.pymdtest import parametrize

TARGET = make_target(segments=[ram(), flash(), eeprom()], peripherals=[usart1()])   # RAM 0x20000000-0x20004FFF
FLASHED = make_target(segments=[ram(), flash()], firmware=firmware())               # image in 0x08000000-0x08002FFF


def _command(id, address=0, mem=None, length=4, data=None) -> Command:
    return Command(name=CommandId(id).name, id=id, mem=mem, address=address, length=length, data=data)


def _ok(command: Command, target=TARGET) -> bool:
    try:
        command_rules.check(command, target)
    except CommandError as exc:
        assert_eq(exc.code, 3, message=str(exc))
        return False
    return True


def _reason(command: Command, target=TARGET) -> str:
    try:
        command_rules.check(command, target)
    except CommandError as exc:
        return str(exc)
    raise AssertionError(f"{command} accepted")


def _read(mem, address, length=4):
    return _command(CommandId.READ_MEM, address, mem, length)


def _write(mem, address, length=4, data=None):
    return _command(CommandId.WRITE_MEM, address, mem, length, data if data is not None else bytes(length))


# ---------------------------------------------------------------- 1. memory ranges

@parametrize("command,ok", [
    (_read(MemType.RAM, 0x20000000),            True),
    (_read(MemType.RAM, 0x20004FFC),            True),    # the last word fits exactly
    (_read(MemType.RAM, 0x20004FFD),            False),   # one byte past the end
    (_read(MemType.RAM, 0x1FFFFFFC),            False),   # before the start
    (_read(MemType.RAM, 0x20000000, 0x5001),    False),   # longer than the segment
    (_read(MemType.FLASH, 0x08000100),          True),
    (_read(MemType.EEPROM, 0x810000),           True),
    (_read(MemType.FLASH, 0x20000000),          False),   # a RAM address is not flash
    (_write(MemType.RAM, 0x20000010),           True),
    (_write(MemType.RAM, 0x20005000),           False),
    (_write(MemType.EEPROM, 0x810000),          True),
])
def test_memory_ranges(command, ok):
    assert_eq(_ok(command), ok, command=command)


def test_range_errors_name_the_access():
    assert_eq(_reason(_read(MemType.RAM, 0x20004FFC, 8)), "READ_MEM out of range: RAM addr=0x20004FFC len=8.")
    assert_eq(_reason(_write(MemType.RAM, 0x20005000)), "WRITE_MEM out of range: RAM addr=0x20005000 len=4.")
    assert_eq(_reason(_read(MemType.EEPROM, 0x810000), FLASHED), "No memory segments found for type: eeprom.")
    assert_eq(_reason(_read(7, 0)), "Invalid memory type: 7.")


def test_write_length_must_match_the_data():
    assert_eq(_reason(_write(MemType.RAM, 0x20000000, 4, b"\x01\x02")), "Length field 4 does not match data length 2.")


# ---------------------------------------------------------------- 2. the running firmware

@parametrize("address,length,ok", [
    (0x08000000, 4, False),     # inside the image
    (0x08002FFC, 4, False),     # its last word
    (0x08002FFE, 4, False),     # straddles its end
    (0x08003000, 4, True),      # the first free byte
    (0x08008000, 4, True),
])
def test_flash_writes_stay_off_the_firmware(address, length, ok):
    assert_eq(_ok(_write(MemType.FLASH, address, length), FLASHED), ok, address=hex(address))


def test_flash_write_errors_and_warning():
    assert_eq(_reason(_write(MemType.FLASH, 0x08000000), FLASHED),
              "FLASH write rejected: 0x08000000+4B overlaps firmware (0x08000000–0x08002FFF). "
              "Write only above firmware_end_address.")
    with logged_warnings("pc_tool.command_rules") as warnings:
        command_rules.check(_write(MemType.FLASH, 0x08008000), FLASHED)
    assert_eq(warnings, ["Writing to FLASH is platform-dependent (SPM/bootloader required). "
                         "MCU may reject this command."])


def test_flash_writes_are_free_when_the_firmware_is_unknown():
    assert_eq(_ok(_write(MemType.FLASH, 0x08000000), TARGET), True)


@parametrize("address,ok", [
    (0x08000000, False),        # page 0: the vector table
    (0x08001000, False),
    (0x08002C00, False),        # the image's last page
    (0x08002FFF, False),        # erases the whole page from 0x08002C00
    (0x08003000, True),         # the first free page
    (0x08008000, True),
    (0x20000000, False),        # not flash
])
def test_erase_covers_the_whole_page(address, ok):
    assert_eq(_ok(_write(MemType.ERASE, address, 1), FLASHED), ok, address=hex(address))


def test_erase_errors():
    assert_eq(_reason(_write(MemType.ERASE, 0x08000000, 1), FLASHED),
              "ERASE rejected: page 0x08000000–0x080003FF overlaps firmware (0x08000000–0x08002FFF). "
              "Only erase pages above firmware_end_address.")
    assert_eq(_reason(_write(MemType.ERASE, 0x20000000, 1), FLASHED),
              "ERASE address 0x20000000 does not fall within any flash segment.")


# ---------------------------------------------------------------- 3. registers

@parametrize("address,ok", [
    (0x40013800, True), (0x40013803, True),     # every byte of SR
    (0x40013808, True), (0x4001380B, True),     # BRR
    (0x4001380C, False),                        # just past BRR
    (0x50000000, False),
])
def test_read_reg_lands_on_a_register(address, ok):
    assert_eq(_ok(_command(CommandId.READ_REG, address)), ok, address=hex(address))


def test_avr_16_bit_register_high_byte_is_readable():
    avr = make_target(peripherals=AVR_PERIPHERALS)
    assert_eq([_ok(_command(CommandId.READ_REG, a), avr) for a in (0xC3, 0xC4, 0xC5)], [False, True, True])


def test_write_reg_needs_a_writable_register():
    read_only = make_target(peripherals=[usart1(writable=False)])
    assert_eq(_ok(_command(CommandId.WRITE_REG, 0x40013804, data=bytes(4))), True)
    assert_eq(_reason(_command(CommandId.WRITE_REG, 0x40013804, data=bytes(4)), read_only),
              "Register DR at 0x40013804 is read-only.")
    assert_eq(_reason(_command(CommandId.WRITE_REG, 0xDEADBEEF, data=bytes(4))), "WRITE_REG address 0xDEADBEEF not found.")
    assert_eq(_reason(_command(CommandId.READ_REG, 0xDEADBEEF)), "No register found at address 0xDEADBEEF.")


# ---------------------------------------------------------------- 4. slots and controls

def test_slots_follow_the_build():
    """A firmware built with BREAKPOINTS=8 / WATCHPOINTS=2 accepts slot 7 / 1 and rejects 8 / 2."""
    built = make_target(breakpoints=8, watchpoints=2)
    breakpoint_at = lambda slot: _command(CommandId.BREAKPOINT, slot, BreakpointControl.ENABLED)   # noqa: E731
    watchpoint_at = lambda slot: _command(CommandId.WATCHPOINT, slot, WatchpointControl.DISABLED)  # noqa: E731
    assert_eq([_ok(breakpoint_at(s), built) for s in (-1, 0, 7, 8)], [False, True, True, False])
    assert_eq([_ok(watchpoint_at(s), built) for s in (-1, 0, 1, 2)], [False, True, True, False])
    assert_eq(_reason(breakpoint_at(9), built), "Invalid breakpoint ID: 9. Must be 0..7.")


@parametrize("control", [(c,) for c in BreakpointControl])
def test_every_breakpoint_control(control):
    assert_eq(_ok(_command(CommandId.BREAKPOINT, 0, control)), True)


def test_unknown_control_values():
    assert_eq(_reason(_command(CommandId.BREAKPOINT, 0, 99)), "Invalid breakpoint control value: 99.")
    assert_eq(_reason(_command(CommandId.WATCHPOINT, 0, 99)), "Invalid watchpoint control value: 99.")


def test_ping_and_reset_pass():
    assert_eq((_ok(_command(CommandId.PING)), _ok(_command(CommandId.RESET))), (True, True))


# ---------------------------------------------------------------- 5. the watch address

def _watch(address=None, control=WatchpointControl.ENABLED, data=None):
    data = address.to_bytes(4, "little") if address is not None else data
    return _command(CommandId.WATCHPOINT, 0, control, data=data)


@parametrize("address,ok", [
    (0x20000100, True),
    (0x20004FFC, True),
    (0x20004FFE, False),        # its 4 bytes run past RAM
    (0x40013808, True),         # a register
    (0x60000000, False),        # unmapped: would fault the MCU on every poll
])
def test_watch_address_must_be_ram_or_a_register(address, ok):
    assert_eq(_ok(_watch(address)), ok, address=hex(address))


def test_enabled_needs_a_watch_address():
    message = "WATCHPOINT ENABLED needs the address to watch: WATCHPOINT <id> ENABLED <symbol|addr>."
    assert_eq(_reason(_watch()), message)
    assert_eq(_reason(_watch(data=b"\x00\x01")), message)
    for control in (WatchpointControl.DISABLED, WatchpointControl.RESET, WatchpointControl.MASK):
        assert_eq(_ok(_watch(control=control)), True, control=control.name)


def test_unaligned_watch_address_warns():
    with logged_warnings("pc_tool.command_rules") as warnings:
        assert_eq(_ok(_watch(0x20000101)), True)
    assert_eq(len(warnings), 1)
    assert warnings[0].startswith("Watch address 0x20000101 is not 4-byte aligned"), warnings
