from logger import log, LogLevel
from common.dataclasses import Command

def parse_line(line: str, command_dict: dict) -> Command | None:
    """ Parse line into command and arguments."""
    tokens = line.strip().split()
    if not tokens:
        return None
    
    try:
        name = tokens[0].upper()

        if name not in command_dict:
            return None
        
        id = command_dict[name]['id']
        address = int(tokens[1], 16) if len(tokens) > 1 else 0
        length = int(tokens[2]) if len(tokens) > 2 else None

        # Parse data if present and convert to bytes
        # Data must be in hex format without 0x prefix
        data = bytes.fromhex(tokens[3]) if len(tokens) > 3 else None

        if length is not None and data is not None and len(data) != length:
            log(log_level=LogLevel.ERROR, module="parser", msg=f"Data length {len(data)} does not match expected length {length}", code=line)
            return None

        return Command(name=name, id=id, address=address, data=data, length=length)
    except (KeyError, ValueError, IndexError) as e:
        log(log_level=LogLevel.ERROR, module="parser", msg=f"Failed to parse line: {line}", code=str(e))

        return None
    

    