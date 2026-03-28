from common.dataclasses import Command
from common.enums import CommandId, MemType, BreakpointControl, WatchpointControl, MDT_MAX_BREAKPOINTS, MDT_MAX_WATCHPOINTS
from common.logger import MDTLogger


def validate_commands(operation: Command, mcu_metadata: dict) -> bool:
    """
    Validate the command against the MCU metadata.

    Args:
        operation (Command): The command to validate.
        mcu_metadata (dict): The MCU metadata containing registers, memories, etc.

    Returns:
        bool: True if valid, False otherwise.
    """
    if operation.id == CommandId.READ_MEM:
        MDTLogger.info(f"Validating READ_MEM command: {operation}")
        return validate_read_mem(operation, mcu_metadata)
    elif operation.id == CommandId.WRITE_MEM:
        MDTLogger.info(f"Validating WRITE_MEM command: {operation}")
        return validate_write_mem(operation, mcu_metadata)
    elif operation.id == CommandId.READ_REG:
        MDTLogger.info(f"Validating READ_REG command: {operation}")
        return validate_read_reg(operation, mcu_metadata)
    elif operation.id == CommandId.WRITE_REG:
        MDTLogger.info(f"Validating WRITE_REG command: {operation}")
        return validate_write_reg(operation, mcu_metadata)
    elif operation.id == CommandId.BREAKPOINT:
        MDTLogger.info(f"Validating BREAKPOINT command: {operation}")
        return validate_breakpoint(operation)
    elif operation.id == CommandId.WATCHPOINT:
        MDTLogger.info(f"Validating WATCHPOINT command: {operation}")
        return validate_watchpoint(operation)

    return False


# ------------------------------------------------------------------
# Internal helper
# ------------------------------------------------------------------

def _resolve_group_base(module: dict, rg_name: str) -> int:
    """
    Resolve the absolute base address for a register group.

    For ATDF (AVR): the true base address lives on the module instance,
    not on the register group itself. The register group offset is relative
    to the instance and is usually 0.

    For SVD (STM32): there are no separate instances — the base address is
    stored directly on the register group offset field, so we fall back to
    reading it from there when no matching instance is found.

    Args:
        module (dict): A single module entry from mcu_metadata["modules"].
        rg_name (str): The name of the register group to resolve.

    Returns:
        int: Absolute base address of the register group.
    """
    for inst in module.get("instances", []):
        if inst.get("register_group") == rg_name:
            offset = inst.get("offset") or 0
            if isinstance(offset, str):
                return int(offset, 0)
            return offset

    # SVD fallback — base address stored directly on the group
    return 0


# ------------------------------------------------------------------
# Memory validators
# ------------------------------------------------------------------

def validate_read_mem(operation: Command, mcu_metadata: dict) -> bool:
    """
    Validate a READ_MEM command.

    Args:
        operation (Command): The READ_MEM command to validate.
        mcu_metadata (dict): The MCU metadata containing memory definitions.

    Returns:
        bool: True if valid, False otherwise.
    """
    try:
        mem_type = MemType(operation.mem)
    except ValueError:
        MDTLogger.error(f"Invalid memory type: {operation.mem}", code=3)
        return False

    memories = mcu_metadata.get("memories", {})
    if not memories:
        MDTLogger.error("No memory definitions found in MCU metadata.", code=3)
        return False

    addr   = operation.address
    length = operation.length

    memtype_to_atdf_type = {
        MemType.FLASH:  "flash",
        MemType.RAM:    "ram",
        MemType.EEPROM: "eeprom",
    }

    wanted_mem_type = memtype_to_atdf_type.get(mem_type)
    if not wanted_mem_type:
        MDTLogger.error(f"Unsupported memory type: {mem_type}", code=3)
        return False

    candidates = [
        seg for seg in memories.values()
        if seg.get("type") == wanted_mem_type
    ]

    if not candidates:
        MDTLogger.error(f"No memory segments found for type: {wanted_mem_type}", code=3)
        return False

    for seg in candidates:
        seg_start = seg.get("start")
        seg_size  = seg.get("size")

        if seg_start is None or seg_size is None:
            continue

        if isinstance(seg_start, str):
            seg_start = int(seg_start, 0)
        if isinstance(seg_size, str):
            seg_size = int(seg_size, 0)

        seg_end = seg_start + seg_size

        if addr >= seg_start and (addr + length) <= seg_end:
            MDTLogger.info(
                f"READ_MEM valid: {mem_type.name} "
                f"addr={hex(addr)} len={length} within {hex(seg_start)}..{hex(seg_end - 1)}",
            )
            return True

    MDTLogger.error(
        f"READ_MEM out of range: {mem_type.name} "
        f"addr=0x{addr:X} len={length}",
        code=3
    )
    return False


def validate_write_mem(operation: Command, mcu_metadata: dict) -> bool:
    """
    Validate a WRITE_MEM command.

    Args:
        operation (Command): The WRITE_MEM command to validate.
        mcu_metadata (dict): The MCU metadata containing memory definitions.

    Returns:
        bool: True if valid, False otherwise.
    """
    if operation.length != len(operation.data):
        MDTLogger.error(
            f"Length field {operation.length} does not match data length {len(operation.data)}",
            code=3
        )
        return False

    try:
        mem_type = MemType(operation.mem)
    except ValueError:
        MDTLogger.error(f"Invalid memory type: {operation.mem}", code=3)
        return False

    memories = mcu_metadata.get("memories", {})
    if not memories:
        MDTLogger.error("No memory-segment definitions found in MCU metadata.", code=3)
        return False

    addr   = operation.address
    length = operation.length

    memtype_to_atdf_type = {
        MemType.RAM:    "ram",
        MemType.EEPROM: "eeprom",
        MemType.FLASH:  "flash",
    }

    wanted_type = memtype_to_atdf_type[mem_type]

    candidates = [
        seg for seg in memories.values()
        if seg.get("type") == wanted_type
    ]

    if not candidates:
        MDTLogger.error(f"No memory segments found for type: {wanted_type}", code=3)
        return False

    for seg in candidates:
        seg_start = seg.get("start")
        seg_size  = seg.get("size")

        if seg_start is None or seg_size is None:
            continue

        if isinstance(seg_start, str):
            seg_start = int(seg_start, 0)
        if isinstance(seg_size, str):
            seg_size = int(seg_size, 0)

        seg_end = seg_start + seg_size

        if addr >= seg_start and (addr + length) <= seg_end:
            if mem_type == MemType.FLASH:
                MDTLogger.warning(
                    "WARNING: Writing to FLASH memory is platform-dependent "
                    "(SPM / bootloader required). MCU may reject this command."
                )
                # TODO: Further FLASH-specific checks can be added here

            MDTLogger.info(
                f"WRITE_MEM valid: {mem_type.name} "
                f"0x{addr:X} .. 0x{addr + length - 1:X}",
            )
            return True

    MDTLogger.error(
        f"WRITE_MEM out of range: {mem_type.name} "
        f"addr=0x{addr:X} len={length}",
        code=3
    )
    return False


# ------------------------------------------------------------------
# Register validators
# ------------------------------------------------------------------

def validate_read_reg(operation: Command, mcu_metadata: dict) -> bool:
    """
    Validate a READ_REG command by absolute address.

    Resolves the true base address from the module instance list (ATDF/AVR)
    or falls back to the register group offset field (SVD/STM32).
    Register size is stored in bits and converted to bytes for range checks.

    Args:
        operation (Command): Command with .address
        mcu_metadata (dict): Parsed MCU metadata

    Returns:
        bool: True if the address corresponds to a readable register, False otherwise.
    """
    addr    = operation.address
    modules = mcu_metadata.get("modules", {})

    for module_name, module in modules.items():
        for rg_name, rg in module.get("register_groups", {}).items():

            # Resolve true base: instance offset (ATDF) or group offset (SVD)
            base = _resolve_group_base(module, rg_name)
            if base == 0:
                group_offset = rg.get("offset") or 0
                if isinstance(group_offset, str):
                    group_offset = int(group_offset, 0)
                base = group_offset

            for reg_name, reg in rg.get("registers", {}).items():

                reg_offset = reg.get("offset") or 0
                if isinstance(reg_offset, str):
                    reg_offset = int(reg_offset, 0)

                reg_size_bits = reg.get("size") or 8
                if isinstance(reg_size_bits, str):
                    reg_size_bits = int(reg_size_bits, 0)
                reg_size_bytes = max(1, reg_size_bits // 8)  # bits → bytes, minimum 1

                absolute_start = base + reg_offset
                absolute_end   = absolute_start + reg_size_bytes

                if absolute_start <= addr < absolute_end:
                    MDTLogger.info(
                        f"Found register {reg_name} in module {module_name} "
                        f"at address range 0x{absolute_start:X}-0x{absolute_end - 1:X}",
                    )
                    return True

    MDTLogger.error(f"No register found at address 0x{addr:X}", code=3)
    return False


def validate_write_reg(operation: Command, mcu_metadata: dict) -> bool:
    """
    Validate a WRITE_REG command by absolute address.

    Resolves the true base address from the module instance list (ATDF/AVR)
    or falls back to the register group offset field (SVD/STM32).
    Register size is stored in bits and converted to bytes for range checks.
    Read-only registers are rejected.

    Args:
        operation (Command): Command with .address and .data
        mcu_metadata (dict): Parsed MCU metadata

    Returns:
        bool: True if the address corresponds to a writable register, False otherwise.
    """
    addr    = operation.address
    modules = mcu_metadata.get("modules", {})

    for module_name, module in modules.items():
        for rg_name, rg in module.get("register_groups", {}).items():

            # Resolve true base: instance offset (ATDF) or group offset (SVD)
            base = _resolve_group_base(module, rg_name)
            if base == 0:
                group_offset = rg.get("offset") or 0
                if isinstance(group_offset, str):
                    group_offset = int(group_offset, 0)
                base = group_offset

            for reg_name, reg in rg.get("registers", {}).items():

                reg_offset = reg.get("offset") or 0
                if isinstance(reg_offset, str):
                    reg_offset = int(reg_offset, 0)

                reg_size_bits = reg.get("size") or 8
                if isinstance(reg_size_bits, str):
                    reg_size_bits = int(reg_size_bits, 0)
                reg_size_bytes = max(1, reg_size_bits // 8)  # bits → bytes, minimum 1

                absolute_start = base + reg_offset
                absolute_end   = absolute_start + reg_size_bytes

                if absolute_start <= addr < absolute_end:
                    rw = reg.get("rw", "read-write").lower()
                    if "write" not in rw:
                        MDTLogger.error(
                            f"Register {reg_name} at 0x{absolute_start:X} is read-only ({rw})",
                            code=3
                        )
                        return False
                    MDTLogger.info(
                        f"Found register {reg_name} in module {module_name} "
                        f"at address range 0x{absolute_start:X}-0x{absolute_end - 1:X}",
                    )
                    return True

    MDTLogger.error(f"WRITE_REG address 0x{addr:X} not found in any register", code=3)
    return False


# ------------------------------------------------------------------
# Breakpoint validator
# ------------------------------------------------------------------

def validate_breakpoint(operation: Command) -> bool:
    """
    Validate a BREAKPOINT command.

    Args:
        operation (Command): The BREAKPOINT command to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    if operation.address < 0 or operation.address >= MDT_MAX_BREAKPOINTS:
        MDTLogger.error(
            f"Invalid breakpoint ID: {operation.address}. "
            f"Must be between 0 and {MDT_MAX_BREAKPOINTS - 1}.",
            code=3
        )
        return False

    try:
        control_value = BreakpointControl(operation.mem)
    except ValueError:
        MDTLogger.error(f"Invalid breakpoint control value: {operation.mem}", code=3)
        return False

    for control in BreakpointControl:
        if control_value == control:
            MDTLogger.info(f"Valid breakpoint control value: {control.name} ({control.value})")
            return True

    MDTLogger.error(f"Invalid breakpoint control value: {operation.mem}", code=3)
    return False


# ------------------------------------------------------------------
# Watchpoint validator
# ------------------------------------------------------------------

def validate_watchpoint(operation: Command) -> bool:
    """
    Validate a WATCHPOINT command.

    Slot ID is in operation.address, control is in operation.mem,
    and the watched address is packed in operation.data (4 bytes LE).
    """
    if operation.address < 0 or operation.address >= MDT_MAX_WATCHPOINTS:
        MDTLogger.error(
            f"Invalid watchpoint ID: {operation.address}. "
            f"Must be between 0 and {MDT_MAX_WATCHPOINTS - 1}.",
            code=3
        )
        return False

    try:
        control = WatchpointControl(operation.mem)
    except ValueError:
        MDTLogger.error(f"Invalid watchpoint control value: {operation.mem}", code=3)
        return False

    if control == WatchpointControl.ENABLED:
        if operation.data is None or len(operation.data) != 4:
            MDTLogger.error("WATCHPOINT enable requires a 4-byte watch address in data.", code=3)
            return False
        watched_addr = int.from_bytes(operation.data, byteorder="little")
        if watched_addr % 4 != 0:
            MDTLogger.error(
                f"Watch address 0x{watched_addr:X} is not 4-byte aligned.", code=3
            )
            return False

    MDTLogger.info(f"Valid watchpoint: slot={operation.address} control={control.name}")
    return True