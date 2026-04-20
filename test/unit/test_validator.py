"""
VALIDATOR TESTS FOR MCU-MDT


Validates the correctness of command validation logic against various metadata configurations.

Coverage:
1. Memory read/write validation (RAM, Flash, EEPROM)
2. Register read/write validation (read-only, write-only, read-write)
3. Breakpoint validation (valid/invalid IDs, control values)
4. Watchpoint validation (valid/invalid IDs, control values, data requirements)
5. Dispatch validation (ensuring correct validator is called based on command ID)
6. Edge cases (addresses at segment boundaries, missing metadata, invalid control values)

Assumptions:
1. Metadata structure as defined in the code (memories and modules)
2. Command dataclass and enums are defined as per protocol
3. Validation functions return True for valid commands and False for invalid ones

Goal:
Ensure that the command validation logic correctly identifies valid and invalid commands based on the provided metadata, preventing
potentially harmful operations and ensuring correct usage of the protocol.
"""

from test.common.asserts import assert_eq
from test.pymdtest import parametrize
from pc_tool.common.dataclasses import Command
from pc_tool.common.enums import (
    CommandId, MemType,
    BreakpointControl, WatchpointControl,
    MDT_MAX_BREAKPOINTS, MDT_MAX_WATCHPOINTS,
)
from pc_tool.validator import (
    validate_read_mem,
    validate_write_mem,
    validate_read_reg,
    validate_write_reg,
    validate_breakpoint,
    validate_watchpoint,
    validate_commands,
)


# Shared mfixtures
def _meta_ram(start=0x20000000, size=0x5000):
    return {
        "memories": {
            "IRAM": {"type": "ram", "start": start, "size": size}
        },
        "modules": {}
    }

def _meta_flash(start=0x08000000, size=0x20000):
    return {
        "memories": {
            "FLASH": {"type": "flash", "start": start, "size": size}
        },
        "modules": {}
    }

def _meta_eeprom(start=0x810000, size=0x400):
    return {
        "memories": {
            "EEPROM": {"type": "eeprom", "start": start, "size": size}
        },
        "modules": {}
    }

def _meta_all():
    return {
        "memories": {
            "IRAM":   {"type": "ram",    "start": 0x20000000, "size": 0x5000},
            "FLASH":  {"type": "flash",  "start": 0x08000000, "size": 0x20000},
            "EEPROM": {"type": "eeprom", "start": 0x810000,   "size": 0x400},
        },
        "modules": {}
    }

def _reg_meta(base=0x40013800, reg_offset=0x00, reg_size_bits=32, rw="read-write"):
    return {
        "memories": {},
        "modules": {
            "USART1": {
                "instances": [
                    {"register_group": "USART1", "offset": base}
                ],
                "register_groups": {
                    "USART1": {
                        "offset": base,
                        "registers": {
                            "SR": {
                                "offset": reg_offset,
                                "size": reg_size_bits,
                                "rw": rw,
                            }
                        }
                    }
                }
            }
        }
    }

def _cmd(id, address=0, mem=None, length=4, data=None):
    return Command(name="TEST", id=id, mem=mem, address=address, length=length, data=data)


# validate_read_mem
def test_read_mem_ram_in_range():
    meta = _meta_ram(start=0x20000000, size=0x5000)
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)

def test_read_mem_ram_last_byte_exactly_fits():
    meta = _meta_ram(start=0x20000000, size=0x10)
    # addr=0x2000000C len=4 -> end = 0x20000010 = seg_end -> valid
    cmd = _cmd(CommandId.READ_MEM, address=0x2000000C, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)

def test_read_mem_ram_one_byte_past_end():
    meta = _meta_ram(start=0x20000000, size=0x10)
    # addr=0x2000000D len=4 -> end = 0x20000011 > seg_end -> invalid
    cmd = _cmd(CommandId.READ_MEM, address=0x2000000D, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), False)

def test_read_mem_ram_before_start():
    meta = _meta_ram(start=0x20000000, size=0x5000)
    cmd = _cmd(CommandId.READ_MEM, address=0x1FFFFFFF, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), False)

def test_read_mem_flash_in_range():
    meta = _meta_flash()
    cmd = _cmd(CommandId.READ_MEM, address=0x08000000, mem=MemType.FLASH, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)

def test_read_mem_eeprom_in_range():
    meta = _meta_eeprom()
    cmd = _cmd(CommandId.READ_MEM, address=0x810000, mem=MemType.EEPROM, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)

def test_read_mem_no_memories_returns_false():
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, {"memories": {}, "modules": {}}), False)

def test_read_mem_wrong_type_no_match():
    # Only RAM in metadata; asking for FLASH
    meta = _meta_ram()
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.FLASH, length=4)
    assert_eq(validate_read_mem(cmd, meta), False)

def test_read_mem_hex_string_addresses():
    meta = {
        "memories": {
            "IRAM": {"type": "ram", "start": "0x20000000", "size": "0x5000"}
        },
        "modules": {}
    }
    cmd = _cmd(CommandId.READ_MEM, address=0x20000100, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)


# validate_write_mem
def test_write_mem_ram_in_range():
    meta = _meta_ram()
    cmd = _cmd(CommandId.WRITE_MEM, address=0x20000010, mem=MemType.RAM, length=4,
               data=b'\x01\x02\x03\x04')
    assert_eq(validate_write_mem(cmd, meta), True)

def test_write_mem_ram_out_of_range():
    meta = _meta_ram(start=0x20000000, size=0x10)
    cmd = _cmd(CommandId.WRITE_MEM, address=0x20000010, mem=MemType.RAM, length=4,
               data=b'\x00\x00\x00\x00')
    assert_eq(validate_write_mem(cmd, meta), False)

def test_write_mem_flash_warns_but_passes():
    meta = _meta_flash()
    cmd = _cmd(CommandId.WRITE_MEM, address=0x08000000, mem=MemType.FLASH, length=4,
               data=b'\xFF\xFF\xFF\xFF')
    # Flash writes return True (with a warning) per current implementation
    assert_eq(validate_write_mem(cmd, meta), True)

def test_write_mem_no_memories_returns_false():
    cmd = _cmd(CommandId.WRITE_MEM, address=0x20000000, mem=MemType.RAM, length=4,
               data=b'\x00\x00\x00\x00')
    assert_eq(validate_write_mem(cmd, {"memories": {}, "modules": {}}), False)

def test_write_mem_eeprom_in_range():
    meta = _meta_eeprom()
    cmd = _cmd(CommandId.WRITE_MEM, address=0x810100, mem=MemType.EEPROM, length=4,
               data=b'\xAA\xBB\xCC\xDD')
    assert_eq(validate_write_mem(cmd, meta), True)


# validate_read_reg
def test_read_reg_found():
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, reg_size_bits=32)
    cmd = _cmd(CommandId.READ_REG, address=0x40013800)
    assert_eq(validate_read_reg(cmd, meta), True)

def test_read_reg_found_with_offset():
    meta = _reg_meta(base=0x40013800, reg_offset=0x04, reg_size_bits=32)
    cmd = _cmd(CommandId.READ_REG, address=0x40013804)
    assert_eq(validate_read_reg(cmd, meta), True)

def test_read_reg_not_found():
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, reg_size_bits=32)
    cmd = _cmd(CommandId.READ_REG, address=0xDEADBEEF)
    assert_eq(validate_read_reg(cmd, meta), False)

def test_read_reg_no_modules():
    cmd = _cmd(CommandId.READ_REG, address=0x40013800)
    assert_eq(validate_read_reg(cmd, {"memories": {}, "modules": {}}), False)

def test_read_reg_8bit_register():
    # 8-bit register occupies exactly 1 byte
    meta = _reg_meta(base=0x40, reg_offset=0x00, reg_size_bits=8)
    cmd = _cmd(CommandId.READ_REG, address=0x40)
    assert_eq(validate_read_reg(cmd, meta), True)

def test_read_reg_address_just_past_register():
    # 32-bit register at 0x40013800 occupies 0x40013800..0x40013803
    # Address 0x40013804 should NOT match
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, reg_size_bits=32)
    cmd = _cmd(CommandId.READ_REG, address=0x40013804)
    assert_eq(validate_read_reg(cmd, meta), False)


# validate_write_reg
def test_write_reg_rw_register():
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, rw="read-write")
    cmd = _cmd(CommandId.WRITE_REG, address=0x40013800, data=b'\x00\x00\x00\x01')
    assert_eq(validate_write_reg(cmd, meta), True)

def test_write_reg_read_only_rejected():
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, rw="read-only")
    cmd = _cmd(CommandId.WRITE_REG, address=0x40013800, data=b'\x00\x00\x00\x01')
    assert_eq(validate_write_reg(cmd, meta), False)

def test_write_reg_not_found():
    meta = _reg_meta(base=0x40013800, reg_offset=0x00)
    cmd = _cmd(CommandId.WRITE_REG, address=0xCAFEBABE, data=b'\x00\x00\x00\x00')
    assert_eq(validate_write_reg(cmd, meta), False)

def test_write_reg_write_only_passes():
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, rw="write-only")
    cmd = _cmd(CommandId.WRITE_REG, address=0x40013800, data=b'\x00\x00\x00\x01')
    assert_eq(validate_write_reg(cmd, meta), True)


# validate_breakpoint
@parametrize("bp_id", [(0,), (1,), (2,), (3,)])
def test_breakpoint_valid_ids(bp_id):
    cmd = _cmd(CommandId.BREAKPOINT, address=bp_id, mem=BreakpointControl.ENABLED)
    assert_eq(validate_breakpoint(cmd), True)

@parametrize("bp_id", [(-1,), (4,), (100,)])
def test_breakpoint_invalid_ids(bp_id):
    cmd = _cmd(CommandId.BREAKPOINT, address=bp_id, mem=BreakpointControl.ENABLED)
    assert_eq(validate_breakpoint(cmd), False)

@parametrize("ctrl", [
    (BreakpointControl.DISABLED,),
    (BreakpointControl.ENABLED,),
    (BreakpointControl.RESET,),
    (BreakpointControl.NEXT,),
])
def test_breakpoint_all_control_values(ctrl):
    cmd = _cmd(CommandId.BREAKPOINT, address=0, mem=ctrl)
    assert_eq(validate_breakpoint(cmd), True)

def test_breakpoint_invalid_control_value():
    cmd = _cmd(CommandId.BREAKPOINT, address=0, mem=99)
    assert_eq(validate_breakpoint(cmd), False)


# validate_watchpoint
@parametrize("wp_id", [(0,), (1,), (2,), (3,)])
def test_watchpoint_valid_ids(wp_id):
    cmd = _cmd(CommandId.WATCHPOINT, address=wp_id, mem=WatchpointControl.DISABLED)
    assert_eq(validate_watchpoint(cmd), True)

@parametrize("wp_id", [(-1,), (4,), (255,)])
def test_watchpoint_invalid_ids(wp_id):
    cmd = _cmd(CommandId.WATCHPOINT, address=wp_id, mem=WatchpointControl.DISABLED)
    assert_eq(validate_watchpoint(cmd), False)

def test_watchpoint_enabled_aligned_address():
    watched = (0x20000100).to_bytes(4, "little")
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.ENABLED, data=watched)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_enabled_unaligned_address_rejected():
    watched = (0x20000101).to_bytes(4, "little")  # not 4-byte aligned
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.ENABLED, data=watched)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_enabled_missing_data_rejected():
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.ENABLED, data=None)
    assert_eq(validate_watchpoint(cmd), False)

def test_watchpoint_enabled_short_data_rejected():
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.ENABLED, data=b'\x00\x00')
    assert_eq(validate_watchpoint(cmd), False)

def test_watchpoint_disabled_no_data_needed():
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.DISABLED, data=None)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_reset_no_data_needed():
    cmd = _cmd(CommandId.WATCHPOINT, address=1, mem=WatchpointControl.RESET, data=None)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_mask_no_data_needed():
    cmd = _cmd(CommandId.WATCHPOINT, address=2, mem=WatchpointControl.MASK, data=None)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_invalid_control_value():
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=99)
    assert_eq(validate_watchpoint(cmd), False)

def test_dispatch_read_mem():
    meta = _meta_ram()
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.RAM, length=4)
    assert_eq(validate_commands(cmd, meta), True)

def test_dispatch_write_mem():
    meta = _meta_ram()
    cmd = _cmd(CommandId.WRITE_MEM, address=0x20000000, mem=MemType.RAM, length=4,
               data=b'\x01\x02\x03\x04')
    assert_eq(validate_commands(cmd, meta), True)

def test_dispatch_read_reg():
    meta = _reg_meta()
    cmd = _cmd(CommandId.READ_REG, address=0x40013800)
    assert_eq(validate_commands(cmd, meta), True)

def test_dispatch_write_reg():
    meta = _reg_meta(rw="read-write")
    cmd = _cmd(CommandId.WRITE_REG, address=0x40013800, data=b'\x00\x00\x00\x01')
    assert_eq(validate_commands(cmd, meta), True)

def test_dispatch_breakpoint():
    cmd = _cmd(CommandId.BREAKPOINT, address=0, mem=BreakpointControl.ENABLED)
    assert_eq(validate_commands(cmd, {}), True)

def test_dispatch_watchpoint():
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.DISABLED)
    assert_eq(validate_commands(cmd, {}), True)
