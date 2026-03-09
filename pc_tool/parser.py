import os
import atexit
import argparse
from pathlib import Path
from common.logger import MDTLogger
from common.dataclasses import Command, CommandPacket
from common.protocol import deserialize_command_packet

try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None


class CLIHistory:
    def __init__(self, history_filename=".mdt_history", max_length=1000):
        self.max_length = max_length

        # Project root = mcu_mdt/
        project_root = Path(__file__).resolve().parents[1]

        self.history_file = project_root / history_filename

        if readline:
            readline.set_history_length(self.max_length)

            if self.history_file.exists():
                try:
                    readline.read_history_file(str(self.history_file))
                except Exception:
                    pass

            atexit.register(self._save_history)

    def input(self, prompt="> "):
        return input(prompt)

    def _save_history(self):
        if readline:
            try:
                readline.write_history_file(str(self.history_file))
            except Exception:
                pass

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
    Supports uint (with or without 0x prefix) and bytes (also 0x optional).
    """
    tokens = line.strip().split()
    if not tokens:
        return None

    name = tokens[0].upper()
    if name not in command_dict:
        MDTLogger.error(f"Unknown command: {name}", code=3)
        return None

    cmd_info = command_dict[name]
    params = cmd_info.get("params", [])
    id_ = cmd_info["id"]

    # Check argument count
    expected_args = len(params)
    provided_args = len(tokens) - 1
    if provided_args != expected_args:
        MDTLogger.error(
            f"{name} expects {expected_args} parameter(s), got {provided_args}",
            code=line
        )
        return None

    # Normalize mem_types keys to lowercase
    mem_types_normalized = {k.lower(): v for k, v in mem_types.items()}

    parsed_args = {}
    try:
        for i, param in enumerate(params):
            pname = param["name"]
            ptype = param["type"]
            pvalue = tokens[i + 1]

            if ptype.startswith("uint"):
                # Handle optional 0x prefix
                try:
                    parsed_args[pname] = int(pvalue, 0)
                except ValueError:
                    # fallback: interpret as plain hex
                    parsed_args[pname] = int(pvalue, 16)

            elif ptype == "bytes":
                # Strip 0x prefix if present
                hex_str = pvalue.lower()
                if hex_str.startswith("0x"):
                    hex_str = hex_str[2:]
                try:
                    parsed_args[pname] = bytes.fromhex(hex_str)
                except ValueError:
                    MDTLogger.error(f"Invalid hex data for {pname}", code=pvalue)
                    return None

            elif ptype == "str" and pname == "mem_type":
                mem_key = pvalue.lower()
                if mem_key not in mem_types_normalized:
                    MDTLogger.error(
                        f"Invalid memory type '{pvalue}'. Expected one of: {', '.join(mem_types.keys())}",
                        code=line
                    )
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
        MDTLogger.error(f"Failed to parse line: {line}", code=str(e))
        return None

def parse_packet(packet: bytes) -> None:
    """
    Function that prints the contents of a received packet in a human-readable format."""

    cmd = deserialize_command_packet(packet)
    MDTLogger.info(f"Received packet: {cmd}")