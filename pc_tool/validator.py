from click import command
from common.dataclasses import Command
from common.enums import CommandId, MemType

def validate_commands(operation: Command, mcu_metadata: dict) -> bool:
    """
    Validate the command against the ATDF data.

    Args:
        operation (Command): The command to validate.
        mcu_metadata (dict): The MCU metadata containing registers, memories, etc.

    Raises:
        TODO:
    """
    if operation.id == CommandId.READ_MEM:
        print(f"Validating READ_MEM command: {operation}")
        return validate_read_mem(operation, mcu_metadata)
    elif operation.id == CommandId.WRITE_MEM:
        print(f"Validating WRITE_MEM command: {operation}")
        return validate_write_mem(operation, mcu_metadata)
    elif operation.id == CommandId.READ_REG:
        print(f"Validating READ_REG command: {operation}")
        return validate_read_reg(operation, mcu_metadata)
    elif operation.id == CommandId.WRITE_REG:
        print(f"Validating WRITE_REG command: {operation}")
    else:
        pass

    return False

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
        print(f"Invalid memory type: {operation.mem}")
        return False
    
    memories = mcu_metadata.get('memories', {})

    if not memories:
        print("No memory definitions found in MCU metadata.")
        return False
    
    addr = operation.address
    length = operation.length

    # Map logical MemType to ATDF memory type strings
    memtype_to_atdf_type = {
        MemType.FLASH: "flash",
        MemType.RAM: "ram",
        MemType.EEPROM: "eeprom",
    }

    wanted_mem_type = memtype_to_atdf_type.get(mem_type)

    if not wanted_mem_type:
        print(f"Unsupported memory type: {mem_type}")
        return False
    
    # Find all related segments
    candidates = [
        seg for seg in memories.values()
        if seg.get('type') == wanted_mem_type
    ]

    if not candidates:
        print(f"No memory segments found for type: {wanted_mem_type}")
        return False
    
    # The candidate has start and size
    for seg in candidates:
        seg_start = seg.get('start')
        seg_size = seg.get('size')

        if seg_start is None or seg_size is None:
            continue

        seg_end = seg_start + seg_size

        if addr >= seg_start and (addr + length) <= seg_end:
            print(f"Address {hex(addr)} with length {length} is valid in segment {seg}")
            return True

    return False

def validate_read_reg(operation: Command, mcu_metadata: dict) -> bool:
    """
    Validate a READ_REG command by absolute address.
    Assumes reading the full register (length = register size).

    Args:
        operation (Command): Command with .address
        mcu_metadata (dict): Parsed ATDF

    Returns:
        bool: True if the address corresponds to a readable register, False otherwise
    """
    addr = operation.address
    modules = mcu_metadata.get("modules", {})

    for module_name, module in modules.items():
        for rg_name, rg in module.get("register_groups", {}).items():

            group_offset = rg.get("offset") or 0
            if isinstance(group_offset, str):
                group_offset = int(group_offset, 0)

            for reg_name, reg in rg.get("registers", {}).items():

                reg_offset = reg.get("offset") or 0
                if isinstance(reg_offset, str):
                    reg_offset = int(reg_offset, 0)

                reg_size = reg.get("size") or 1
                if isinstance(reg_size, str):
                    reg_size = int(reg_size, 0)

                absolute_start = group_offset + reg_offset
                absolute_end = absolute_start + reg_size

                if absolute_start <= operation.address < absolute_end:
                    print(f"Found register {reg_name} in module {module_name} at address range 0x{absolute_start:X}-0x{absolute_end - 1:X}")
                    return True

    print(f"No register found at address 0x{operation.address:X}")
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

    # Check if len differs from data length
    if operation.length != len(operation.data):
        print(f"Length field {operation.length} does not match data length {len(operation.data)}")
        return False

    try:
        mem_type = MemType(operation.mem)
    except ValueError:
        print(f"Invalid memory type: {operation.mem}")
        return False

    memories = mcu_metadata.get("memories", {})
    if not memories:
        print("No memory-segment definitions found in MCU metadata.")
        return False

    addr = operation.address
    length = operation.length

    memtype_to_atdf_type = {
        MemType.RAM: "ram",
        MemType.EEPROM: "eeprom",
        MemType.FLASH: "flash",
    }

    wanted_type = memtype_to_atdf_type[mem_type]

    # Find candidate segments
    candidates = [
        seg for seg in memories.values()
        if seg.get("type") == wanted_type
    ]

    print(f"candidates: {candidates}")

    if not candidates:
        print(f"No memory segments found for type: {wanted_type}")
        return False
    
    for seg in candidates:
        seg_start = seg.get("start")
        seg_size = seg.get("size")

        if seg_start is None or seg_size is None:
            continue

        if isinstance(seg_start, str):
            seg_start = int(seg_start, 0)
        if isinstance(seg_size, str):
            seg_size = int(seg_size, 0)

        seg_end = seg_start + seg_size

        if addr >= seg_start and (addr + length) <= seg_end:

            if mem_type == MemType.FLASH:
                print(
                    "WARNING: Writing to FLASH memory is platform-dependent "
                    "(SPM / bootloader required). MCU may reject this command."
                )
                # TODO: Further FLASH-specific checks can be added here

            print(
                f"WRITE_MEM valid: {mem_type.name} "
                f"0x{addr:X} .. 0x{addr + length - 1:X}"
            )
            return True

    print(
        f"WRITE_MEM out of range: {mem_type.name} "
        f"addr=0x{addr:X} len={length}"
    )
    return False  