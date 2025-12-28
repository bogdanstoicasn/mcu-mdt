from common.dataclasses import Command
from common.enums import CommandId

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
        return True
    elif operation.id == CommandId.WRITE_MEM:
        print(f"Validating WRITE_MEM command: {operation}")
    elif operation.id == CommandId.READ_REG:
        print(f"Validating READ_REG command: {operation}")
    elif operation.id == CommandId.WRITE_REG:
        print(f"Validating WRITE_REG command: {operation}")
    else:
        pass

    return False
