import argparse
from logger import log, LogLevel
from common.dataclasses import Command

def parse_args():
    """
    Parse CLI line into list of arguments using argparse.
    """
    parser = argparse.ArgumentParser(
        description="MCU MDT Debugger CLI"
    )
    parser.add_argument(
        "build_info",
        type=str,
        help="Path to build_info.yaml file",
    )

    return parser.parse_args()

def parse_line(line: str, command_dict: dict, mem_types: dict) -> Command | None:
    """
    Parse CLI line into a Command object according to YAML definition.
    """
    tokens = line.strip().split()
    if not tokens:
        return None

    name = tokens[0].upper()
    if name not in command_dict:
        log(LogLevel.ERROR, "parser", f"Unknown command: {name}")
        return None

    cmd_info = command_dict[name]
    params = cmd_info.get("params", [])
    id_ = cmd_info["id"]

    # Check argument count
    expected_args = len(params)
    provided_args = len(tokens) - 1
    if provided_args != expected_args:
        log(LogLevel.ERROR, "parser",
            f"{name} expects {expected_args} parameter(s), got {provided_args}",
            code=line)
        return None

    # normalize mem_types keys to lowercase
    mem_types_normalized = {k.lower(): v for k, v in mem_types.items()}

    parsed_args = {}
    try:
        for i, param in enumerate(params):
            pname = param["name"]
            ptype = param["type"]
            pvalue = tokens[i + 1]

            if ptype.startswith("uint"):
                parsed_args[pname] = int(pvalue, 0)

            elif ptype == "bytes":
                try:
                    parsed_args[pname] = bytes.fromhex(pvalue)
                except ValueError:
                    log(LogLevel.ERROR, "parser", f"Invalid hex data for {pname}", code=pvalue)
                    return None

            elif ptype == "str" and pname == "mem_type":
                # case-insensitive lookup
                mem_key = pvalue.lower()
                if mem_key not in mem_types_normalized:
                    log(LogLevel.ERROR, "parser",
                        f"Invalid memory type '{pvalue}'. Expected one of: {', '.join(mem_types.keys())}",
                        code=line)
                    return None
                parsed_args[pname] = mem_types_normalized[mem_key]

            else:
                parsed_args[pname] = pvalue

        return Command(
            name=name,
            id=id_,
            mem=parsed_args.get("mem_type"),
            address=parsed_args.get("address", 0),
            length=parsed_args.get("len"),
            data=parsed_args.get("data")
        )

    except (ValueError, IndexError, KeyError) as e:
        log(LogLevel.ERROR, "parser", f"Failed to parse line: {line}", code=str(e))
        return None
