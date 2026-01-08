from click import command
from common.dataclasses import Command
from common.enums import CommandId, MemType

def validate_commands(operation: Command, atdf_data: dict) -> bool:
    """
    Validate the command against the ATDF data.

    Args:
        operation (Command): The command to validate.
        atdf_data (dict): The ATDF data containing registers, memories, etc.

    Raises:
        TODO:
    """
    if operation.id == CommandId.READ_MEM:
        print(f"Validating READ_MEM command: {operation}")
        return validate_read_mem(operation, atdf_data)
    elif operation.id == CommandId.WRITE_MEM:
        print(f"Validating WRITE_MEM command: {operation}")
    elif operation.id == CommandId.READ_REG:
        print(f"Validating READ_REG command: {operation}")
        return validate_read_reg(operation, atdf_data)
    elif operation.id == CommandId.WRITE_REG:
        print(f"Validating WRITE_REG command: {operation}")
    else:
        pass

    return False

def validate_read_mem(operation: Command, atdf_data: dict) -> bool:
    """
    Validate a READ_MEM command.

    Args:
        operation (Command): The READ_MEM command to validate.
        atdf_data (dict): The ATDF data containing memory definitions.

    Returns:
        bool: True if valid, False otherwise.
    """

    try:
        mem_type = MemType(operation.mem)
    except ValueError:
        print(f"Invalid memory type: {operation.mem}")
        return False
    
    memories = atdf_data.get('memories', {})

    if not memories:
        print("No memory definitions found in ATDF data.")
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

def validate_read_reg(operation: Command, atdf_data: dict) -> bool:
    """
    Validate a READ_REG command by absolute address.
    Assumes reading the full register (length = register size).

    Args:
        operation (Command): Command with .address
        atdf_data (dict): Parsed ATDF

    Returns:
        bool: True if the address corresponds to a readable register, False otherwise
    """
    addr = operation.address
    modules = atdf_data.get("modules", {})

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


    