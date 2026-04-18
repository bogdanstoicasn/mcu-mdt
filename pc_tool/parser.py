import os
import atexit
import argparse
from pathlib import Path
from pc_tool.common.logger import MDTLogger
from pc_tool.common.dataclasses import Command, CommandPacket
from pc_tool.common.protocol import deserialize_command_packet
from pc_tool.common.elf_symbols import resolve_symbol, check_watchpoint_alignment

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
    parser.add_argument(
        "--script",
        type=str,
        required=False,
        default=None,
        help="Path to a script file with commands to execute (exits after completion)",
    )

    return parser.parse_args()

def resolve_register_address(name: str, mcu_metadata: dict) -> int | None:
    """Look up a register by name and return its absolute address."""
    name_upper = name.upper()
    modules = mcu_metadata.get("modules", {})

    for module in modules.values():
        for rg_name, rg in module.get("register_groups", {}).items():
            base = 0
            for inst in module.get("instances", []):
                if inst.get("register_group") == rg_name:
                    offset = inst.get("offset") or 0
                    base = int(offset, 0) if isinstance(offset, str) else offset
                    break
            if base == 0:
                group_offset = rg.get("offset") or 0
                base = int(group_offset, 0) if isinstance(group_offset, str) else group_offset

            for reg_name, reg in rg.get("registers", {}).items():
                if reg_name.upper() == name_upper:
                    reg_offset = reg.get("offset") or 0
                    reg_offset = int(reg_offset, 0) if isinstance(reg_offset, str) else reg_offset
                    return base + reg_offset

    return None

def parse_line(line: str, command_dict: dict, control_values: dict, mcu_metadata: dict,
               elf_symbols: dict = None) -> Command | None:
    """
    Parse CLI line into a Command object according to YAML definition.
    Supports uint (with or without 0x prefix), bytes (also 0x optional),
    and symbol_or_uint32 (symbol name from ELF or hex address).
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
 
    # Normalize control_values keys to lowercase
    control_values_normalized = {k.lower(): v for k, v in control_values.items()}
 
    parsed_args = {}
    try:
        for i, param in enumerate(params):
            pname = param["name"]
            ptype = param["type"]
            pvalue = tokens[i + 1]
 
            if ptype == "symbol_or_uint32":
                # Try hex address first, then fall back to ELF symbol lookup
                try:
                    parsed_args[pname] = int(pvalue, 16 if not pvalue.startswith("0x") else 0)
                except ValueError:
                    if not elf_symbols:
                        MDTLogger.error(
                            f"Cannot resolve symbol '{pvalue}': no ELF loaded. "
                            f"Add 'elf: path/to/firmware.elf' to build_info.yaml.",
                            code=line
                        )
                        return None
                    sym = resolve_symbol(pvalue, elf_symbols)
                    if sym is None:
                        # Search for compiler-mangled local static variants (e.g. var_my.0)
                        candidates = [s for k, s in elf_symbols.items()
                                    if k == pvalue or k.startswith(pvalue + ".")]
                        if len(candidates) == 1:
                            sym = candidates[0]
                            MDTLogger.info(f"Resolved '{pvalue}' -> '{sym.name}' (local static)")
                        elif len(candidates) > 1:
                            names = ", ".join(s.name for s in candidates)
                            MDTLogger.error(
                                f"Ambiguous symbol '{pvalue}': multiple local statics found: {names}. "
                                f"Use the full mangled name.",
                                code=line
                            )
                            return None
                        else:
                            MDTLogger.error(
                                f"Symbol '{pvalue}' not found in ELF symbol table. "
                                f"Tip: only static/global variables are watchable. "
                                f"Local variables live on the stack and have no fixed address.",
                                code=line
                            )
                            return None
                    check_watchpoint_alignment(sym)
                    parsed_args[pname] = sym.address

            elif ptype == "uint32_or_str":
                # Try numeric first using format hint, then resolve as register name
                fmt = param.get("format", "hex")
                try:
                    parsed_args[pname] = int(pvalue, 16 if fmt == "hex" else 0)
                except ValueError:
                    addr = resolve_register_address(pvalue, mcu_metadata)
                    if addr is None:
                        MDTLogger.error(f"Unknown register name '{pvalue}'", code=line)
                        return None
                    parsed_args[pname] = addr
 
            elif ptype.startswith("uint"):
                fmt = param.get("format", "hex")
                base = 16 if fmt == "hex" else 10
                # always allow 0x prefix regardless of format
                if pvalue.lower().startswith("0x"):
                    parsed_args[pname] = int(pvalue, 16)
                else:
                    try:
                        parsed_args[pname] = int(pvalue, base)
                    except ValueError:
                        MDTLogger.error(f"Invalid value '{pvalue}' for {pname}", code=line)
                        return None
 
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
 
            elif ptype == "str" and pname == "control_value":
                control_key = pvalue.lower()
                if control_key not in control_values_normalized:
                    MDTLogger.error(
                        f"Invalid control value '{pvalue}'. Expected one of: {', '.join(control_values_normalized.keys())}",
                        code=line
                    )
                    return None
                parsed_args[pname] = control_values_normalized[control_key]
 
            else:
                parsed_args[pname] = pvalue
 
        return Command(
            name=name,
            id=id_,
            mem=parsed_args.get("control_value"),
            address=parsed_args.get("address", 0),
            length=parsed_args.get("len"),
            data=parsed_args.get("data") or (
                # WATCHPOINT: pack wp_data (address or mask) as 4-byte little-endian
                parsed_args["wp_data"].to_bytes(4, byteorder="little")
                if "wp_data" in parsed_args else None
            )
        )
 
    except (ValueError, IndexError, KeyError) as e:
        MDTLogger.error(f"Failed to parse line: {line}", code=str(e))
        return None

def parse_packet(packet: bytes) -> None:
    """
    Function that prints the contents of a received packet in a human-readable format."""

    cmd = deserialize_command_packet(packet)
    MDTLogger.info(f"Received packet: {cmd}")
