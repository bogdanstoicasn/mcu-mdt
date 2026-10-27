"""
C <-> PYTHON WIRE CONTRACT TESTS FOR MCU-MDT

The firmware (C headers) and the PC tool (Python enums, commands.yaml) each
hold their own copy of the protocol constants. These tests parse the C headers
and compare them with the Python side, so a value added or changed on one side
and forgotten on the other fails here instead of corrupting packets.

Coverage:
1. Packet size, field offsets and fence bytes
2. Flag bits
3. Command ids (C vs Python vs commands.yaml)
4. Event types
5. Control values: memory zones, breakpoint and watchpoint controls, and their commands.yaml names
"""

import re
from pathlib import Path

import yaml

from pc_tool import wire_protocol
from test.common.asserts import assert_eq

_ROOT = Path(__file__).resolve().parents[2]

# C name -> Python name, where the two sides spell a member differently.
_FLAG_ALIASES = {"EVENT": "EVENT_PACKET"}
_CONTROL_ALIASES = {"DISABLE": "DISABLED", "ENABLE": "ENABLED"}


def _text(rel_path: str) -> str:
    return (_ROOT / rel_path).read_text()


def _c_members(rel_path: str, prefix: str, aliases: dict | None = None) -> dict:
    """Parse ``<prefix>NAME = value`` enum members; return {NAME: value}."""
    aliases = aliases or {}
    pattern = rf"\b{prefix}(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\b"
    return {aliases.get(name, name): int(value, 0)
            for name, value in re.findall(pattern, _text(rel_path))}


def _c_defines(rel_path: str, prefix: str) -> dict:
    """Parse ``#define <prefix>NAME value``; return {NAME: value}."""
    pattern = rf"#define\s+{prefix}(\w+)\s+(0x[0-9A-Fa-f]+|\d+)\b"
    return {name: int(value, 0) for name, value in re.findall(pattern, _text(rel_path))}


def _py(enum_cls, skip=()) -> dict:
    return {name: int(member) for name, member in enum_cls.__members__.items() if name not in skip}


def _assert_same(c_side: dict, py_side: dict, what: str) -> None:
    assert_eq(c_side, py_side, what=what,
              only_in_c=sorted(set(c_side) - set(py_side)),
              only_in_python=sorted(set(py_side) - set(c_side)))


def test_packet_size():
    c_size = _c_defines("src/mcu_mdt_protocol.h", "MDT_")["PACKET_SIZE"]
    assert_eq(c_size, wire_protocol.PACKET_SIZE)


def test_field_offsets():
    _assert_same(_c_defines("src/mcu_mdt_protocol.h", "MDT_OFFSET_"), _py(wire_protocol.Offset), "MDT_OFFSET_*")


def test_fence_bytes():
    c = _c_defines("src/mcu_mdt_protocol.h", "MDT_")
    assert_eq((c["START_BYTE"], c["END_BYTE"]),
              (wire_protocol.START_BYTE, wire_protocol.END_BYTE))


def test_flags():
    c = _c_members("src/mcu_mdt_protocol.h", "INTERNAL_MDT_FLAG_", _FLAG_ALIASES)
    _assert_same(c, _py(wire_protocol.Flag), "INTERNAL_MDT_FLAG_*")


def test_command_ids_c_vs_python():
    c = _c_members("src/mcu_mdt_protocol.h", "INTERNAL_MDT_CMD_")
    assert_eq(c.pop("NONE"), 0)                       # id 0 is reserved for CMD_ID=0 polls/events
    _assert_same(c, _py(wire_protocol.CommandId), "INTERNAL_MDT_CMD_*")


def test_command_ids_yaml_vs_python():
    commands = yaml.safe_load(_text("pc_tool/configs/commands.yaml"))["commands"]
    yaml_ids = {name: spec["id"] for name, spec in commands.items() if not spec.get("local")}
    _assert_same(yaml_ids, _py(wire_protocol.CommandId), "commands.yaml ids")
    assert all("id" not in spec for spec in commands.values() if spec.get("local")), "a local command has an id"


def test_event_types():
    c = _c_members("src/mcu_mdt_event.h", "", None)
    c = {name: value for name, value in c.items() if name.startswith("INTERNAL_MDT_EVENT_")}
    _assert_same(c, _py(wire_protocol.EventType), "INTERNAL_MDT_EVENT_*")


def test_memory_zones():
    c = _c_members("inc/mcu_mdt_hal.h", "MDT_MEM_ZONE_", {"SRAM": "RAM"})
    _assert_same(c, _py(wire_protocol.MemType), "MDT_MEM_ZONE_*")


def test_breakpoint_and_watchpoint_controls():
    bp = _c_members("src/mcu_mdt_breakpoints.h", "INTERNAL_MDT_BP_", _CONTROL_ALIASES)
    wp = _c_members("src/mcu_mdt_watchpoint.h", "INTERNAL_MDT_WP_", _CONTROL_ALIASES)
    _assert_same(bp, _py(wire_protocol.BreakpointControl), "INTERNAL_MDT_BP_*")
    _assert_same(wp, _py(wire_protocol.WatchpointControl), "INTERNAL_MDT_WP_*")


def test_commands_yaml_choices_send_their_commands_values():
    """Each command takes only its own control names, and each name sends that command's value."""
    own = {"READ_MEM": wire_protocol.MemType, "WRITE_MEM": wire_protocol.MemType,
           "BREAKPOINT": wire_protocol.BreakpointControl, "WATCHPOINT": wire_protocol.WatchpointControl}
    commands = yaml.safe_load(_text("pc_tool/configs/commands.yaml"))["commands"]
    choices = [(name, param["values"]) for name, spec in commands.items()
               for param in spec.get("params", []) if param["type"] == "choice"]
    assert_eq(sorted({name for name, _ in choices}), sorted(own))
    for name, values in choices:
        assert_eq(values, {word: own[name][word].value for word in values}, command=name)
    assert_eq(set(commands["WATCHPOINT"]["params"][1]["values"]), set(_py(wire_protocol.WatchpointControl)))
    assert_eq(set(commands["BREAKPOINT"]["params"][1]["values"]), set(_py(wire_protocol.BreakpointControl)))
