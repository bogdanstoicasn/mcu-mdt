import os
import atexit
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
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
    """Parse CLI arguments using argparse."""
    parser = argparse.ArgumentParser(description="MCU MDT Debugger CLI")
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


# ---------------------------------------------------------------------------
# Register name -> address resolution (used by uint32_or_str handler)
# ---------------------------------------------------------------------------

def resolve_register_address(name: str, mcu_metadata: dict) -> int | None:
    """Look up a register by name and return its absolute address."""
    name_upper = name.upper()

    for module in mcu_metadata.get("modules", {}).values():
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


# ---------------------------------------------------------------------------
# Parameter type handlers
# ---------------------------------------------------------------------------
# Each handler receives a _ParseContext and returns the parsed value, or
# raises ValueError with a human-readable message on failure.
# To add a new type: write one function and register it in _TYPE_HANDLERS.

@dataclass
class _ParseContext:
    """All state a type handler might need."""
    pname:                     str
    pvalue:                    str
    param:                     dict
    line:                      str
    mcu_metadata:              dict
    elf_symbols:               dict
    control_values_normalized: dict


def _parse_symbol_or_uint32(ctx: _ParseContext) -> int:
    """Hex address, or fall back to ELF symbol lookup (with local-static mangling)."""
    # Try numeric first
    try:
        return int(ctx.pvalue, 16 if not ctx.pvalue.startswith("0x") else 0)
    except ValueError:
        pass

    if not ctx.elf_symbols:
        MDTLogger.error(
            f"Cannot resolve symbol '{ctx.pvalue}': no ELF loaded. "
            f"Add 'elf: path/to/firmware.elf' to build_info.yaml.",
            code=ctx.line,
        )
        raise ValueError(f"no ELF for symbol '{ctx.pvalue}'")

    sym = resolve_symbol(ctx.pvalue, ctx.elf_symbols)

    if sym is None:
        # Compiler-mangled local statics appear as  varname.N  in the symbol table
        candidates = [
            s for k, s in ctx.elf_symbols.items()
            if k == ctx.pvalue or k.startswith(ctx.pvalue + ".")
        ]
        if len(candidates) == 1:
            sym = candidates[0]
            MDTLogger.info(f"Resolved '{ctx.pvalue}' -> '{sym.name}' (local static)")
        elif len(candidates) > 1:
            names = ", ".join(s.name for s in candidates)
            MDTLogger.error(
                f"Ambiguous symbol '{ctx.pvalue}': multiple local statics found: {names}. "
                f"Use the full mangled name.",
                code=ctx.line,
            )
            raise ValueError(f"ambiguous symbol '{ctx.pvalue}'")
        else:
            MDTLogger.error(
                f"Symbol '{ctx.pvalue}' not found in ELF symbol table. "
                f"Tip: only static/global variables are watchable. "
                f"Local variables live on the stack and have no fixed address.",
                code=ctx.line,
            )
            raise ValueError(f"symbol '{ctx.pvalue}' not found")

    check_watchpoint_alignment(sym)
    return sym.address


def _parse_uint32_or_str(ctx: _ParseContext) -> int:
    """Numeric address (hex default), or resolve as a register name."""
    fmt = ctx.param.get("format", "hex")
    try:
        return int(ctx.pvalue, 16 if fmt == "hex" else 0)
    except ValueError:
        pass

    addr = resolve_register_address(ctx.pvalue, ctx.mcu_metadata)
    if addr is None:
        MDTLogger.error(f"Unknown register name '{ctx.pvalue}'", code=ctx.line)
        raise ValueError(f"unknown register '{ctx.pvalue}'")
    return addr


def _parse_uint(ctx: _ParseContext) -> int:
    """Unsigned integer -- hex or decimal according to the param's format hint."""
    fmt = ctx.param.get("format", "hex")
    base = 16 if fmt == "hex" else 10
    if ctx.pvalue.lower().startswith("0x"):
        return int(ctx.pvalue, 16)
    try:
        return int(ctx.pvalue, base)
    except ValueError:
        MDTLogger.error(f"Invalid value '{ctx.pvalue}' for {ctx.pname}", code=ctx.line)
        raise


def _parse_bytes(ctx: _ParseContext) -> bytes:
    """Hex byte string, with or without the 0x prefix."""
    hex_str = ctx.pvalue.lower()
    if hex_str.startswith("0x"):
        hex_str = hex_str[2:]
    try:
        return bytes.fromhex(hex_str)
    except ValueError:
        MDTLogger.error(f"Invalid hex data for {ctx.pname}", code=ctx.pvalue)
        raise


def _parse_control_str(ctx: _ParseContext) -> int:
    """Named control value (RAM, FLASH, ENABLED, ...) looked up in control_values."""
    key = ctx.pvalue.lower()
    if key not in ctx.control_values_normalized:
        MDTLogger.error(
            f"Invalid control value '{ctx.pvalue}'. "
            f"Expected one of: {', '.join(ctx.control_values_normalized.keys())}",
            code=ctx.line,
        )
        raise ValueError(f"unknown control value '{ctx.pvalue}'")
    return ctx.control_values_normalized[key]


# Map param type strings -> handler functions.
# Exact key match is tried first; "str:control_value" is a compound key for
# the (type="str", name="control_value") combination.  uint* is caught by
# prefix fallback in _resolve_handler.
_TYPE_HANDLERS: dict[str, Callable[[_ParseContext], object]] = {
    "symbol_or_uint32": _parse_symbol_or_uint32,
    "uint32_or_str":    _parse_uint32_or_str,
    "bytes":            _parse_bytes,
    "str:control_value": _parse_control_str,
}

_UINT_PREFIX = "uint"


def _resolve_handler(ptype: str, pname: str) -> Callable[[_ParseContext], object]:
    """Return the right handler for a (type, name) pair."""
    if ptype in _TYPE_HANDLERS:
        return _TYPE_HANDLERS[ptype]
    compound_key = f"{ptype}:{pname}"
    if compound_key in _TYPE_HANDLERS:
        return _TYPE_HANDLERS[compound_key]
    if ptype.startswith(_UINT_PREFIX):
        return _parse_uint
    # Generic fallback: return the raw string unchanged
    return lambda ctx: ctx.pvalue


# ---------------------------------------------------------------------------
# Public: parse one CLI line into a Command
# ---------------------------------------------------------------------------

def parse_line(
    line: str,
    command_dict: dict,
    control_values: dict,
    mcu_metadata: dict,
    elf_symbols: dict | None = None,
) -> Command | None:
    """
    Parse a CLI line into a Command object according to the YAML command definition.

    Supports all parameter types declared in commands.yaml:
    ``uint*``, ``bytes``, ``str`` (control_value), ``uint32_or_str``,
    ``symbol_or_uint32``. Adding a new type only requires a new handler
    function and an entry in ``_TYPE_HANDLERS``.
    """
    tokens = line.strip().split()
    if not tokens:
        return None

    name = tokens[0].upper()
    if name not in command_dict:
        MDTLogger.error(f"Unknown command: {name}", code=3)
        return None

    cmd_info      = command_dict[name]
    params        = cmd_info.get("params", [])
    id_           = cmd_info["id"]

    expected_args = len(params)
    provided_args = len(tokens) - 1
    if provided_args != expected_args:
        MDTLogger.error(
            f"{name} expects {expected_args} parameter(s), got {provided_args}",
            code=line,
        )
        return None

    control_values_normalized = {k.lower(): v for k, v in control_values.items()}

    parsed_args: dict = {}
    try:
        for i, param in enumerate(params):
            pname  = param["name"]
            ptype  = param["type"]
            pvalue = tokens[i + 1]

            ctx = _ParseContext(
                pname                     = pname,
                pvalue                    = pvalue,
                param                     = param,
                line                      = line,
                mcu_metadata              = mcu_metadata,
                elf_symbols               = elf_symbols or {},
                control_values_normalized = control_values_normalized,
            )

            handler = _resolve_handler(ptype, pname)
            parsed_args[pname] = handler(ctx)

        return Command(
            name    = name,
            id      = id_,
            mem     = parsed_args.get("control_value"),
            address = parsed_args.get("address", 0),
            length  = parsed_args.get("len"),
            data    = parsed_args.get("data") or (
                # WATCHPOINT: pack wp_data (address or mask) as 4-byte little-endian
                parsed_args["wp_data"].to_bytes(4, byteorder="little")
                if "wp_data" in parsed_args else None
            ),
        )

    except (ValueError, IndexError, KeyError) as e:
        MDTLogger.error(f"Failed to parse line: {line}", code=str(e))
        return None


# Pretty print a received packet (for debugging purposes)
def parse_packet(packet: bytes) -> None:
    """Print the contents of a received packet in human-readable form."""
    cmd = deserialize_command_packet(packet)
    MDTLogger.info(f"Received packet: {cmd}")