from pc_tool.common.dataclasses import Command
from pc_tool.common.enums import (
    CommandId, MemType, BreakpointControl, WatchpointControl,
    MDT_MAX_BREAKPOINTS, MDT_MAX_WATCHPOINTS,
)
from pc_tool.common.logger import MDTLogger

# Map MemType enum → ATDF/SVD type string used in metadata
_MEM_TYPE_STR = {
    MemType.FLASH:  "flash",
    MemType.RAM:    "ram",
    MemType.EEPROM: "eeprom",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _int(value) -> int:
    """Coerce a string or int metadata value to int."""
    return int(value, 0) if isinstance(value, str) else (value or 0)


def _resolve_group_base(module: dict, rg_name: str, rg: dict) -> int:
    """Return the absolute base address of a register group.

    For ATDF (AVR) the true base lives on the module instance, not on the
    register group.  For SVD (STM32) there are no instances, so the base
    is stored directly on the register group's offset field.
    """
    for inst in module.get("instances", []):
        if inst.get("register_group") == rg_name:
            return _int(inst.get("offset") or 0)
    return _int(rg.get("offset") or 0)


def _find_mem_segment(mcu_metadata: dict, mem_type: MemType, addr: int, length: int):
    """Return the matching memory segment dict, or None if out of range."""
    wanted = _MEM_TYPE_STR.get(mem_type)
    if not wanted:
        MDTLogger.error(f"Unsupported memory type: {mem_type}.", code=3)
        return None

    memories = mcu_metadata.get("memories", {})
    if not memories:
        MDTLogger.error("No memory definitions found in MCU metadata.", code=3)
        return None

    candidates = [s for s in memories.values() if s.get("type") == wanted]
    if not candidates:
        MDTLogger.error(f"No memory segments found for type: {wanted}.", code=3)
        return None

    for seg in candidates:
        start = seg.get("start")
        size  = seg.get("size")
        if start is None or size is None:
            continue
        start, size = _int(start), _int(size)
        if addr >= start and (addr + length) <= start + size:
            return seg

    return None


def _find_register(mcu_metadata: dict, addr: int):
    """Return (module_name, reg_name, reg, absolute_start, absolute_end) for the
    register that contains ``addr``, or None if not found."""
    for module_name, module in mcu_metadata.get("modules", {}).items():
        for rg_name, rg in module.get("register_groups", {}).items():
            base = _resolve_group_base(module, rg_name, rg)

            for reg_name, reg in rg.get("registers", {}).items():
                offset        = _int(reg.get("offset") or 0)
                size_bits     = _int(reg.get("size") or 8)
                size_bytes    = max(1, size_bits // 8)
                abs_start     = base + offset
                abs_end       = abs_start + size_bytes

                if abs_start <= addr < abs_end:
                    return module_name, reg_name, reg, abs_start, abs_end

    return None


# ---------------------------------------------------------------------------
# Memory validators
# ---------------------------------------------------------------------------

def validate_read_mem(operation: Command, mcu_metadata: dict) -> bool:
    try:
        mem_type = MemType(operation.mem)
    except ValueError:
        MDTLogger.error(f"Invalid memory type: {operation.mem}.", code=3)
        return False

    addr, length = operation.address, operation.length
    seg = _find_mem_segment(mcu_metadata, mem_type, addr, length)

    if seg is None:
        MDTLogger.error(
            f"READ_MEM out of range: {mem_type.name} addr=0x{addr:X} len={length}.", code=3
        )
        return False

    start = _int(seg["start"])
    end   = start + _int(seg["size"])
    MDTLogger.info(
        f"READ_MEM valid: {mem_type.name} addr=0x{addr:X} len={length} "
        f"within 0x{start:X}..0x{end - 1:X}."
    )
    return True


def validate_write_mem(operation: Command, mcu_metadata: dict) -> bool:
    if operation.length != len(operation.data):
        MDTLogger.error(
            f"Length field {operation.length} does not match data length {len(operation.data)}.",
            code=3,
        )
        return False

    try:
        mem_type = MemType(operation.mem)
    except ValueError:
        MDTLogger.error(f"Invalid memory type: {operation.mem}.", code=3)
        return False

    addr, length = operation.address, operation.length
    seg = _find_mem_segment(mcu_metadata, mem_type, addr, length)

    if seg is None:
        MDTLogger.error(
            f"WRITE_MEM out of range: {mem_type.name} addr=0x{addr:X} len={length}.", code=3
        )
        return False

    if mem_type == MemType.FLASH:
        MDTLogger.warning(
            "Writing to FLASH is platform-dependent (SPM/bootloader required). "
            "MCU may reject this command."
        )

    MDTLogger.info(
        f"WRITE_MEM valid: {mem_type.name} 0x{addr:X}..0x{addr + length - 1:X}."
    )
    return True


# ---------------------------------------------------------------------------
# Register validators
# ---------------------------------------------------------------------------

def validate_read_reg(operation: Command, mcu_metadata: dict) -> bool:
    result = _find_register(mcu_metadata, operation.address)
    if result is None:
        MDTLogger.error(f"No register found at address 0x{operation.address:X}.", code=3)
        return False

    module_name, reg_name, _, abs_start, abs_end = result
    MDTLogger.info(
        f"READ_REG valid: {reg_name} in {module_name} "
        f"at 0x{abs_start:X}..0x{abs_end - 1:X}."
    )
    return True


def validate_write_reg(operation: Command, mcu_metadata: dict) -> bool:
    result = _find_register(mcu_metadata, operation.address)
    if result is None:
        MDTLogger.error(f"WRITE_REG address 0x{operation.address:X} not found.", code=3)
        return False

    module_name, reg_name, reg, abs_start, abs_end = result
    rw = reg.get("rw", "read-write").lower()

    if "write" not in rw:
        MDTLogger.error(
            f"Register {reg_name} at 0x{abs_start:X} is read-only ({rw}).", code=3
        )
        return False

    MDTLogger.info(
        f"WRITE_REG valid: {reg_name} in {module_name} "
        f"at 0x{abs_start:X}..0x{abs_end - 1:X}."
    )
    return True


# ---------------------------------------------------------------------------
# Breakpoint / watchpoint validators
# ---------------------------------------------------------------------------

def validate_breakpoint(operation: Command) -> bool:
    if not (0 <= operation.address < MDT_MAX_BREAKPOINTS):
        MDTLogger.error(
            f"Invalid breakpoint ID: {operation.address}. "
            f"Must be 0..{MDT_MAX_BREAKPOINTS - 1}.",
            code=3,
        )
        return False

    try:
        control = BreakpointControl(operation.mem)
    except ValueError:
        MDTLogger.error(f"Invalid breakpoint control value: {operation.mem}.", code=3)
        return False

    MDTLogger.info(f"BREAKPOINT valid: slot={operation.address} control={control.name}.")
    return True


def validate_watchpoint(operation: Command) -> bool:
    if not (0 <= operation.address < MDT_MAX_WATCHPOINTS):
        MDTLogger.error(
            f"Invalid watchpoint ID: {operation.address}. "
            f"Must be 0..{MDT_MAX_WATCHPOINTS - 1}.",
            code=3,
        )
        return False

    try:
        control = WatchpointControl(operation.mem)
    except ValueError:
        MDTLogger.error(f"Invalid watchpoint control value: {operation.mem}.", code=3)
        return False

    if control == WatchpointControl.ENABLED:
        if operation.data is None or len(operation.data) != 4:
            MDTLogger.error("WATCHPOINT ENABLED requires a 4-byte watch address in data.", code=3)
            return False
        watched_addr = int.from_bytes(operation.data, "little")
        if watched_addr % 4 != 0:
            MDTLogger.warning(
                f"Watch address 0x{watched_addr:X} is not 4-byte aligned — "
                f"adjacent bytes will be included in the 4-byte read. "
                f"Use MASK to filter only the relevant bits."
            )

    MDTLogger.info(f"WATCHPOINT valid: slot={operation.address} control={control.name}.")
    return True


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_DISPATCH = {
    CommandId.RESET:      lambda op, meta: True,
    CommandId.READ_MEM:   validate_read_mem,
    CommandId.WRITE_MEM:  validate_write_mem,
    CommandId.READ_REG:   validate_read_reg,
    CommandId.WRITE_REG:  validate_write_reg,
    CommandId.BREAKPOINT: lambda op, _: validate_breakpoint(op),
    CommandId.WATCHPOINT: lambda op, _: validate_watchpoint(op),
}


def validate_commands(operation: Command, mcu_metadata: dict) -> bool:
    handler = _DISPATCH.get(operation.id)
    if handler is None:
        MDTLogger.error(f"Unknown command ID: {operation.id}.", code=3)
        return False

    MDTLogger.info(f"Validating {operation.name} command: {operation}.")
    return handler(operation, mcu_metadata)