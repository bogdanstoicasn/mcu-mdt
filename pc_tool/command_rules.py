"""Accept a Command for this Target, or say why not.

The rules keep the MCU safe from what it would do blindly: reads and writes stay inside a memory
segment, register access lands on a register (writes on a writable one), slots exist in the
firmware that was built, and flash writes and erases stay off the running image.
"""

import logging

from pc_tool import command_parser, target_model, wire_protocol

log = logging.getLogger(__name__)

_SEGMENT_KIND = {wire_protocol.MemType.FLASH: "flash", wire_protocol.MemType.RAM: "ram", wire_protocol.MemType.EEPROM: "eeprom",
                 wire_protocol.MemType.ERASE: "flash"}   # an erase is bounded by the flash segments


def check(command: wire_protocol.Command, target: target_model.Target) -> None:
    """Return if *command* may be sent to *target*; raise CommandError (code 3) if not."""
    log.info("Validating %s command: %s.", command.name, command)
    rule = _RULES.get(command.id)
    if rule is None:
        raise _refused(f"Unknown command ID: {command.id}.")
    rule(command, target)


def _refused(message: str) -> command_parser.CommandError:
    return command_parser.CommandError(message, code=3)


def _enum(enum_cls, value: int, what: str):
    try:
        return enum_cls(value)
    except ValueError:
        raise _refused(f"Invalid {what}: {value}.") from None


def _segment(target: target_model.Target, mem: wire_protocol.MemType, address: int, length: int):
    kind = _SEGMENT_KIND[mem]
    if not target.segments_of(kind):
        raise _refused(f"No memory segments found for type: {kind}.")
    return target.segment(kind, address, length)


def _firmware_overlap(target: target_model.Target, address: int, size: int) -> str | None:
    """The firmware's range as text when [address, address + size) overlaps it, else None."""
    firmware = target.firmware
    if firmware is None or address + size <= firmware.start or address >= firmware.start + firmware.size:
        return None
    return f"0x{firmware.start:08X}–0x{firmware.start + firmware.size - 1:08X}"


# ---------------------------------------------------------------- memory

def _read_mem(command: wire_protocol.Command, target: target_model.Target) -> None:
    mem = _enum(wire_protocol.MemType, command.mem, "memory type")
    address, length = command.address, command.length
    segment = _segment(target, mem, address, length)
    if segment is None:
        raise _refused(f"READ_MEM out of range: {mem.name} addr=0x{address:X} len={length}.")
    log.info("READ_MEM valid: %s addr=0x%X len=%d within 0x%X..0x%X.",
             mem.name, address, length, segment.start, segment.start + segment.size - 1)


def _write_mem(command: wire_protocol.Command, target: target_model.Target) -> None:
    mem = _enum(wire_protocol.MemType, command.mem, "memory type")
    if mem == wire_protocol.MemType.ERASE:
        _erase(command, target)
        return

    address, length = command.address, command.length
    if length != len(command.data):
        raise _refused(f"Length field {length} does not match data length {len(command.data)}.")
    if _segment(target, mem, address, length) is None:
        raise _refused(f"WRITE_MEM out of range: {mem.name} addr=0x{address:X} len={length}.")
    if mem == wire_protocol.MemType.FLASH:
        firmware = _firmware_overlap(target, address, length)
        if firmware:
            raise _refused(f"FLASH write rejected: 0x{address:08X}+{length}B overlaps firmware ({firmware}). "
                           f"Write only above firmware_end_address.")
        log.warning("Writing to FLASH is platform-dependent (SPM/bootloader required). MCU may reject this command.")
    log.info("WRITE_MEM valid: %s 0x%X..0x%X.", mem.name, address, address + length - 1)


def _erase(command: wire_protocol.Command, target: target_model.Target) -> None:
    """The MCU erases the whole page holding the address; data and length are ignored."""
    segment = _segment(target, wire_protocol.MemType.ERASE, command.address, 1)
    if segment is None:
        raise _refused(f"ERASE address 0x{command.address:X} does not fall within any flash segment.")
    page = (target.firmware and target.firmware.page) or segment.page or 1
    page_base = command.address & ~(page - 1)
    firmware = _firmware_overlap(target, page_base, page)
    if firmware:
        raise _refused(f"ERASE rejected: page 0x{page_base:08X}–0x{page_base + page - 1:08X} overlaps firmware "
                       f"({firmware}). Only erase pages above firmware_end_address.")
    log.info("ERASE valid: page 0x%08X (flash 0x%X..0x%X).", page_base, segment.start, segment.start + segment.size - 1)


# ---------------------------------------------------------------- registers

def _read_reg(command: wire_protocol.Command, target: target_model.Target) -> None:
    register = target.registers.at(command.address)
    if register is None:
        raise _refused(f"No register found at address 0x{command.address:X}.")
    log.info("READ_REG valid: %s in %s at 0x%X..0x%X.", register.name, register.peripheral,
             register.address, register.address + register.size - 1)


def _write_reg(command: wire_protocol.Command, target: target_model.Target) -> None:
    register = target.registers.at(command.address)
    if register is None:
        raise _refused(f"WRITE_REG address 0x{command.address:X} not found.")
    if not register.writable:
        raise _refused(f"Register {register.name} at 0x{register.address:X} is read-only.")
    log.info("WRITE_REG valid: %s in %s at 0x%X..0x%X.", register.name, register.peripheral,
             register.address, register.address + register.size - 1)


# ---------------------------------------------------------------- breakpoints and watchpoints

def _slot(kind: str, slot: int, count: int) -> None:
    """A slot exists if it is below the count the firmware was built with."""
    if not 0 <= slot < count:
        raise _refused(f"Invalid {kind} ID: {slot}. Must be 0..{count - 1}.")


def _breakpoint(command: wire_protocol.Command, target: target_model.Target) -> None:
    _slot("breakpoint", command.address, target.breakpoints)
    control = _enum(wire_protocol.BreakpointControl, command.mem, "breakpoint control value")
    log.info("BREAKPOINT valid: slot=%d control=%s.", command.address, control.name)


# The controls that use the value; DISABLED and RESET ignore it, so it may be left out there.
# (A MASK sent without one would set the mask to 0, and the watchpoint would never fire again.)
_WATCHPOINT_VALUE = {
    wire_protocol.WatchpointControl.ENABLED: "the address to watch: WATCHPOINT <id> ENABLED <symbol|addr>",
    wire_protocol.WatchpointControl.MASK: "the mask: WATCHPOINT <id> MASK <mask>",
}


def _watchpoint(command: wire_protocol.Command, target: target_model.Target) -> None:
    _slot("watchpoint", command.address, target.watchpoints)
    control = _enum(wire_protocol.WatchpointControl, command.mem, "watchpoint control value")
    needs = _WATCHPOINT_VALUE.get(control)
    if needs and (command.data is None or len(command.data) != wire_protocol.WORD_SIZE):
        raise _refused(f"WATCHPOINT {control.name} needs {needs}.")
    if control == wire_protocol.WatchpointControl.ENABLED:
        watched = int.from_bytes(command.data, "little")
        # The MCU reads these 4 bytes on every poll: an unmapped address faults an STM32 for good.
        if target.segment("ram", watched, 4) is None and target.registers.at(watched) is None:
            raise _refused(f"Watch address 0x{watched:X} is not in RAM (all 4 bytes) or a register of this part.")
        if watched % 4:
            log.warning("Watch address 0x%X is not 4-byte aligned — adjacent bytes will be included in the "
                        "4-byte read. Use MASK to filter only the relevant bits.", watched)
    log.info("WATCHPOINT valid: slot=%d control=%s.", command.address, control.name)


def _always(command: wire_protocol.Command, target: target_model.Target) -> None:
    """PING and RESET carry nothing to check."""


_RULES = {
    wire_protocol.CommandId.PING:       _always,
    wire_protocol.CommandId.RESET:      _always,
    wire_protocol.CommandId.READ_MEM:   _read_mem,
    wire_protocol.CommandId.WRITE_MEM:  _write_mem,
    wire_protocol.CommandId.READ_REG:   _read_reg,
    wire_protocol.CommandId.WRITE_REG:  _write_reg,
    wire_protocol.CommandId.BREAKPOINT: _breakpoint,
    wire_protocol.CommandId.WATCHPOINT: _watchpoint,
}
