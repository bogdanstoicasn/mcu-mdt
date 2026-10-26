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
5. Control values: memory zones, breakpoint and watchpoint controls
"""

import re
from pathlib import Path

import yaml

from pc_tool.common import enums
from pc_tool.common.dataclasses import CommandPacket
from test.common.asserts import assert_eq

_ROOT = Path(__file__).resolve().parents[2]

# C name -> Python name, where the two sides spell a member differently.
_FLAG_ALIASES = {"EVENT": "EVENT_PACKET"}
_CONTROL_ALIASES = {"DISABLE": "DISABLED", "ENABLE": "ENABLED"}
# Commands that exist only on the PC and are never sent to the MCU.
_PC_ONLY_COMMANDS = {"EXIT", "HELP", "CLEAR"}


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
    assert_eq(c_size, enums.MDT_PACKET_SIZE)


def test_field_offsets():
    _assert_same(_c_defines("src/mcu_mdt_protocol.h", "MDT_OFFSET_"), _py(enums.MDTOffset), "MDT_OFFSET_*")


def test_fence_bytes():
    c = _c_defines("src/mcu_mdt_protocol.h", "MDT_")
    assert_eq((c["START_BYTE"], c["END_BYTE"]),
              (enums.FenceType.START_BYTE, enums.FenceType.END_BYTE))
    assert_eq((c["START_BYTE"], c["END_BYTE"]),
              (CommandPacket.START_BYTE, CommandPacket.END_BYTE))


def test_flags():
    c = _c_members("src/mcu_mdt_protocol.h", "INTERNAL_MDT_FLAG_", _FLAG_ALIASES)
    _assert_same(c, _py(enums.MDTFlags), "INTERNAL_MDT_FLAG_*")


def test_command_ids_c_vs_python():
    c = _c_members("src/mcu_mdt_protocol.h", "INTERNAL_MDT_CMD_")
    assert_eq(c.pop("NONE"), 0)                       # id 0 is reserved for CMD_ID=0 polls/events
    _assert_same(c, _py(enums.CommandId, skip=_PC_ONLY_COMMANDS), "INTERNAL_MDT_CMD_*")
    pc_only_ids = {enums.CommandId[n].value for n in _PC_ONLY_COMMANDS}
    assert pc_only_ids.isdisjoint(c.values()), "a PC-only command reuses an MCU command id"


def test_command_ids_yaml_vs_python():
    yaml_ids = {name: spec["id"] for name, spec in
                yaml.safe_load(_text("pc_tool/configs/commands.yaml"))["commands"].items()}
    _assert_same(yaml_ids, _py(enums.CommandId), "commands.yaml ids")


def test_event_types():
    c = _c_members("src/mcu_mdt_event.h", "", None)
    c = {name: value for name, value in c.items() if name.startswith("INTERNAL_MDT_EVENT_")}
    _assert_same(c, _py(enums.EventType), "INTERNAL_MDT_EVENT_*")


def test_memory_zones():
    c = _c_members("inc/mcu_mdt_hal.h", "MDT_MEM_ZONE_", {"SRAM": "RAM"})
    _assert_same(c, _py(enums.MemType), "MDT_MEM_ZONE_*")


def test_breakpoint_and_watchpoint_controls():
    bp = _c_members("src/mcu_mdt_breakpoints.h", "INTERNAL_MDT_BP_", _CONTROL_ALIASES)
    wp = _c_members("src/mcu_mdt_watchpoint.h", "INTERNAL_MDT_WP_", _CONTROL_ALIASES)
    _assert_same(bp, _py(enums.BreakpointControl), "INTERNAL_MDT_BP_*")
    _assert_same(wp, _py(enums.WatchpointControl), "INTERNAL_MDT_WP_*")


def test_commands_yaml_control_values():
    expected = {}
    for enum_cls in (enums.MemType, enums.BreakpointControl, enums.WatchpointControl):
        for name, value in _py(enum_cls).items():
            assert_eq(expected.setdefault(name, value), value, conflicting_name=name)
    yaml_values = yaml.safe_load(_text("pc_tool/configs/commands.yaml"))["control_values"]
    _assert_same(dict(yaml_values), expected, "commands.yaml control_values")
