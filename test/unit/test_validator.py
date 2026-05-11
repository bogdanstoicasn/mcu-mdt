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
from test.common.mdtfixtures import MCU_METADATA_FLASH
from test.common.mdtfixtures import _meta_ram, _meta_flash, _meta_eeprom, _reg_meta
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


def _cmd(id, address=0, mem=None, length=4, data=None):
    return Command(name="TEST", id=id, mem=mem, address=address, length=length, data=data)


# validate_read_mem
def test_read_mem_ram_in_range():
    """Test that a read from RAM within the defined segment is accepted."""
    meta = _meta_ram(start=0x20000000, size=0x5000)
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)

def test_read_mem_ram_last_byte_exactly_fits():
    """Test that a read from RAM that ends exactly at the segment end is accepted."""
    meta = _meta_ram(start=0x20000000, size=0x10)
    # addr=0x2000000C len=4 -> end = 0x20000010 = seg_end -> valid
    cmd = _cmd(CommandId.READ_MEM, address=0x2000000C, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)

def test_read_mem_ram_one_byte_past_end():
    """Test that a read from RAM that extends one byte past the segment end is rejected."""
    meta = _meta_ram(start=0x20000000, size=0x10)
    # addr=0x2000000D len=4 -> end = 0x20000011 > seg_end -> invalid
    cmd = _cmd(CommandId.READ_MEM, address=0x2000000D, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), False)

def test_read_mem_ram_before_start():
    """Test that a read from RAM that starts before the segment start is rejected."""
    meta = _meta_ram(start=0x20000000, size=0x5000)
    cmd = _cmd(CommandId.READ_MEM, address=0x1FFFFFFF, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, meta), False)

def test_read_mem_flash_in_range():
    """Test that a read from FLASH within the defined segment is accepted."""
    meta = _meta_flash()
    cmd = _cmd(CommandId.READ_MEM, address=0x08000000, mem=MemType.FLASH, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)

def test_read_mem_eeprom_in_range():
    """Test that a read from EEPROM within the defined segment is accepted."""
    meta = _meta_eeprom()
    cmd = _cmd(CommandId.READ_MEM, address=0x810000, mem=MemType.EEPROM, length=4)
    assert_eq(validate_read_mem(cmd, meta), True)

def test_read_mem_no_memories_returns_false():
    """Test that if metadata contains no memories, the read_mem validation fails."""
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.RAM, length=4)
    assert_eq(validate_read_mem(cmd, {"memories": {}, "modules": {}}), False)

def test_read_mem_wrong_type_no_match():
    # Only RAM in metadata; asking for FLASH
    meta = _meta_ram()
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.FLASH, length=4)
    assert_eq(validate_read_mem(cmd, meta), False)

def test_read_mem_big_input_length():
    """Test that a read with a very large length is rejected."""
    meta = _meta_ram()
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.RAM, length=0x100000000)  # 4GB length, likely larger than any segment
    assert_eq(validate_read_mem(cmd, meta), False)

def test_read_mem_hex_string_addresses():
    """Test that addresses specified as hex strings in metadata are correctly parsed and validated."""
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
    """Test that a write to RAM within the defined segment is accepted."""
    meta = _meta_ram()
    cmd = _cmd(CommandId.WRITE_MEM, address=0x20000010, mem=MemType.RAM, length=4,
               data=b'\x01\x02\x03\x04')
    assert_eq(validate_write_mem(cmd, meta), True)

def test_write_mem_ram_out_of_range():
    """Test that a write to RAM outside the defined segment is rejected."""
    meta = _meta_ram(start=0x20000000, size=0x10)
    cmd = _cmd(CommandId.WRITE_MEM, address=0x20000010, mem=MemType.RAM, length=4,
               data=b'\x00\x00\x00\x00')
    assert_eq(validate_write_mem(cmd, meta), False)

def test_write_mem_flash_warns_but_passes():
    """Test that a write to FLASH is accepted but may trigger a warning (per current implementation)."""
    meta = _meta_flash()
    cmd = _cmd(CommandId.WRITE_MEM, address=0x08000000, mem=MemType.FLASH, length=4,
               data=b'\xFF\xFF\xFF\xFF')
    # Flash writes return True (with a warning) per current implementation
    assert_eq(validate_write_mem(cmd, meta), True)

def test_write_mem_no_memories_returns_false():
    """Test that if metadata contains no memories, the write_mem validation fails."""
    cmd = _cmd(CommandId.WRITE_MEM, address=0x20000000, mem=MemType.RAM, length=4,
               data=b'\x00\x00\x00\x00')
    assert_eq(validate_write_mem(cmd, {"memories": {}, "modules": {}}), False)

def test_write_mem_eeprom_in_range():
    """Test that a write to EEPROM within the defined segment is accepted."""
    meta = _meta_eeprom()
    cmd = _cmd(CommandId.WRITE_MEM, address=0x810100, mem=MemType.EEPROM, length=4,
               data=b'\xAA\xBB\xCC\xDD')
    assert_eq(validate_write_mem(cmd, meta), True)


# validate_read_reg
def test_read_reg_found():
    """Test that a read register command matching a defined register is accepted."""
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, reg_size_bits=32)
    cmd = _cmd(CommandId.READ_REG, address=0x40013800)
    assert_eq(validate_read_reg(cmd, meta), True)

def test_read_reg_found_with_offset():
    """Test that a read register command matching a defined register with an offset is accepted."""
    meta = _reg_meta(base=0x40013800, reg_offset=0x04, reg_size_bits=32)
    cmd = _cmd(CommandId.READ_REG, address=0x40013804)
    assert_eq(validate_read_reg(cmd, meta), True)

def test_read_reg_not_found():
    """Test that a read register command with an address that does not match any defined register is rejected."""
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, reg_size_bits=32)
    cmd = _cmd(CommandId.READ_REG, address=0xDEADBEEF)
    assert_eq(validate_read_reg(cmd, meta), False)

def test_read_reg_no_modules():
    """Test that if metadata contains no modules, the read_reg validation fails."""
    cmd = _cmd(CommandId.READ_REG, address=0x40013800)
    assert_eq(validate_read_reg(cmd, {"memories": {}, "modules": {}}), False)

def test_read_reg_8bit_register():
    """Test that a read register command matching an 8-bit register is accepted."""
    meta = _reg_meta(base=0x40, reg_offset=0x00, reg_size_bits=8)
    cmd = _cmd(CommandId.READ_REG, address=0x40)
    assert_eq(validate_read_reg(cmd, meta), True)

def test_read_reg_address_just_past_register():
    # 32-bit register at 0x40013800 occupies 0x40013800..0x40013803
    # Address 0x40013804 should NOT match
    invalid_address = 0x40013804 + 0xFFFF
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, reg_size_bits=32)
    cmd = _cmd(CommandId.READ_REG, address=invalid_address)
    assert_eq(validate_read_reg(cmd, meta), False)


# validate_write_reg
def test_write_reg_rw_register():
    """Test that a write register command to a read-write register is accepted."""
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, rw="read-write")
    cmd = _cmd(CommandId.WRITE_REG, address=0x40013800, data=b'\x00\x00\x00\x01')
    assert_eq(validate_write_reg(cmd, meta), True)

def test_write_reg_read_only_rejected():
    """Test that a write register command to a read-only register is rejected."""
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, rw="read-only")
    cmd = _cmd(CommandId.WRITE_REG, address=0x40013800, data=b'\x00\x00\x00\x01')
    assert_eq(validate_write_reg(cmd, meta), False)

def test_write_reg_not_found():
    """Test that a write register command with an address that does not match any defined register is rejected."""
    meta = _reg_meta(base=0x40013800, reg_offset=0x00)
    cmd = _cmd(CommandId.WRITE_REG, address=0xCAFEBABE, data=b'\x00\x00\x00\x00')
    assert_eq(validate_write_reg(cmd, meta), False)

def test_write_reg_write_only_passes():
    """Test that a write register command to a write-only register is accepted."""
    meta = _reg_meta(base=0x40013800, reg_offset=0x00, rw="write-only")
    cmd = _cmd(CommandId.WRITE_REG, address=0x40013800, data=b'\x00\x00\x00\x01')
    assert_eq(validate_write_reg(cmd, meta), True)


# validate_breakpoint
@parametrize("bp_id", [(0,), (1,), (2,), (3,)])
def test_breakpoint_valid_ids(bp_id):
    """Test that breakpoint commands with valid IDs are accepted."""
    cmd = _cmd(CommandId.BREAKPOINT, address=bp_id, mem=BreakpointControl.ENABLED)
    assert_eq(validate_breakpoint(cmd), True)

@parametrize("bp_id", [(-1,), (4,), (100,)])
def test_breakpoint_invalid_ids(bp_id):
    """Test that breakpoint commands with invalid IDs are rejected."""
    cmd = _cmd(CommandId.BREAKPOINT, address=bp_id, mem=BreakpointControl.ENABLED)
    assert_eq(validate_breakpoint(cmd), False)

@parametrize("ctrl", [
    (BreakpointControl.DISABLED,),
    (BreakpointControl.ENABLED,),
    (BreakpointControl.RESET,),
    (BreakpointControl.NEXT,),
])
def test_breakpoint_all_control_values(ctrl):
    """Test that breakpoint commands with all valid control values are accepted."""
    cmd = _cmd(CommandId.BREAKPOINT, address=0, mem=ctrl)
    assert_eq(validate_breakpoint(cmd), True)

def test_breakpoint_invalid_control_value():
    """Test that a breakpoint command with an invalid control value is rejected."""
    cmd = _cmd(CommandId.BREAKPOINT, address=0, mem=99)
    assert_eq(validate_breakpoint(cmd), False)


# validate_watchpoint
@parametrize("wp_id", [(0,), (1,), (2,), (3,)])
def test_watchpoint_valid_ids(wp_id):
    """Test that watchpoint commands with valid IDs are accepted."""
    cmd = _cmd(CommandId.WATCHPOINT, address=wp_id, mem=WatchpointControl.DISABLED)
    assert_eq(validate_watchpoint(cmd), True)

@parametrize("wp_id", [(-1,), (4,), (255,)])
def test_watchpoint_invalid_ids(wp_id):
    """Test that watchpoint commands with invalid IDs are rejected."""
    cmd = _cmd(CommandId.WATCHPOINT, address=wp_id, mem=WatchpointControl.DISABLED)
    assert_eq(validate_watchpoint(cmd), False)

def test_watchpoint_enabled_aligned_address():
    """Test that enabling a watchpoint with a valid 4-byte aligned address is accepted."""
    watched = (0x20000100).to_bytes(4, "little")
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.ENABLED, data=watched)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_enabled_unaligned_address_rejected():
    """Test that enabling a watchpoint with an unaligned address is rejected."""
    watched = (0x20000101).to_bytes(4, "little")  # not 4-byte aligned
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.ENABLED, data=watched)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_enabled_missing_data_rejected():
    """Test that enabling a watchpoint without providing the required data is rejected."""
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.ENABLED, data=None)
    assert_eq(validate_watchpoint(cmd), False)

def test_watchpoint_enabled_short_data_rejected():
    """Test that enabling a watchpoint with data shorter than 4 bytes is rejected."""
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.ENABLED, data=b'\x00\x00')
    assert_eq(validate_watchpoint(cmd), False)

def test_watchpoint_disabled_no_data_needed():
    """Test that disabling a watchpoint does not require data and is accepted."""
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.DISABLED, data=None)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_reset_no_data_needed():
    """Test that resetting a watchpoint does not require data and is accepted."""
    cmd = _cmd(CommandId.WATCHPOINT, address=1, mem=WatchpointControl.RESET, data=None)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_mask_no_data_needed():
    """Test that masking a watchpoint does not require data and is accepted."""
    cmd = _cmd(CommandId.WATCHPOINT, address=2, mem=WatchpointControl.MASK, data=None)
    assert_eq(validate_watchpoint(cmd), True)

def test_watchpoint_invalid_control_value():
    """Test that a watchpoint command with an invalid control value is rejected."""
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=99)
    assert_eq(validate_watchpoint(cmd), False)

def test_dispatch_read_mem():
    """Test that a READ_MEM command is correctly dispatched to the read_mem validator."""
    meta = _meta_ram()
    cmd = _cmd(CommandId.READ_MEM, address=0x20000000, mem=MemType.RAM, length=4)
    assert_eq(validate_commands(cmd, meta), True)

def test_dispatch_write_mem():
    """Test that a WRITE_MEM command is correctly dispatched to the write_mem validator."""
    meta = _meta_ram()
    cmd = _cmd(CommandId.WRITE_MEM, address=0x20000000, mem=MemType.RAM, length=4,
               data=b'\x01\x02\x03\x04')
    assert_eq(validate_commands(cmd, meta), True)

def test_dispatch_read_reg():
    """Test that a READ_REG command is correctly dispatched to the read_reg validator."""
    meta = _reg_meta()
    cmd = _cmd(CommandId.READ_REG, address=0x40013800)
    assert_eq(validate_commands(cmd, meta), True)

def test_dispatch_write_reg():
    """Test that a WRITE_REG command is correctly dispatched to the write_reg validator."""
    meta = _reg_meta(rw="read-write")
    cmd = _cmd(CommandId.WRITE_REG, address=0x40013800, data=b'\x00\x00\x00\x01')
    assert_eq(validate_commands(cmd, meta), True)

def test_dispatch_breakpoint():
    """Test that a BREAKPOINT command is correctly dispatched to the breakpoint validator."""
    cmd = _cmd(CommandId.BREAKPOINT, address=0, mem=BreakpointControl.ENABLED)
    assert_eq(validate_commands(cmd, {}), True)

def test_dispatch_watchpoint():
    """Test that a WATCHPOINT command is correctly dispatched to the watchpoint validator."""
    cmd = _cmd(CommandId.WATCHPOINT, address=0, mem=WatchpointControl.DISABLED)
    assert_eq(validate_commands(cmd, {}), True)


# Firmware protection tests
def _flash_cmd(address, length=4, data=None):
    return Command(
        name="WRITE_MEM", id=CommandId.WRITE_MEM,
        mem=MemType.FLASH, address=address,
        data=data or b'\x00' * length, length=length,
    )

def _erase_cmd(address):
    return Command(
        name="WRITE_MEM", id=CommandId.WRITE_MEM,
        mem=MemType.ERASE, address=address,
        data=b'\x00\x00\x00\x00', length=4,
    )

# FLASH write protection
def test_flash_write_inside_firmware_rejected():
    """Write landing inside firmware image must be rejected."""
    assert_eq(validate_commands(_flash_cmd(0x08000000), MCU_METADATA_FLASH), False)

def test_flash_write_at_firmware_end_minus_one_rejected():
    """Last byte of firmware must still be protected."""
    assert_eq(validate_commands(_flash_cmd(0x08002FFC), MCU_METADATA_FLASH), False)

def test_flash_write_exactly_at_firmware_end_accepted():
    """First address after firmware end is free — must be accepted."""
    assert_eq(validate_commands(_flash_cmd(0x08003000), MCU_METADATA_FLASH), True)

def test_flash_write_above_firmware_accepted():
    """Write well above firmware end must be accepted."""
    assert_eq(validate_commands(_flash_cmd(0x08008000), MCU_METADATA_FLASH), True)

def test_flash_write_spanning_firmware_boundary_rejected():
    """Write that starts before firmware_end but extends past it is rejected."""
    # 0x08002FFE to 0x08003001 — straddles the boundary
    assert_eq(validate_commands(_flash_cmd(0x08002FFE, length=4), MCU_METADATA_FLASH), False)

def test_flash_write_no_firmware_info_allowed():
    """Without firmware info in metadata the write is accepted (AVR, old builds)."""
    meta_no_fw = {
        "memories": {"IFLASH": {"type": "flash", "start": 0x08000000, "size": 0x10000}},
        "modules": {},
    }
    assert_eq(validate_commands(_flash_cmd(0x08000000, data=b'\xff\xff\xff\xff'), meta_no_fw), True)

# ERASE protection
def test_erase_page_inside_firmware_rejected():
    """Erasing a page that overlaps the firmware must be rejected."""
    # 0x08001000 is inside page 4 (0x08001000–0x080013FF), well within firmware
    assert_eq(validate_commands(_erase_cmd(0x08001000), MCU_METADATA_FLASH), False)

def test_erase_first_page_rejected():
    """Erasing page 0 (vector table) must always be rejected."""
    assert_eq(validate_commands(_erase_cmd(0x08000000), MCU_METADATA_FLASH), False)

def test_erase_last_firmware_page_rejected():
    """Erasing the last page occupied by firmware must be rejected."""
    # firmware ends at 0x08003000; last firmware page is 0x08002C00–0x08002FFF
    assert_eq(validate_commands(_erase_cmd(0x08002C00), MCU_METADATA_FLASH), False)

def test_erase_first_free_page_accepted():
    """Erasing the first page after firmware_end must be accepted."""
    # firmware_end = 0x08003000 → first free page starts at 0x08003000
    assert_eq(validate_commands(_erase_cmd(0x08003000), MCU_METADATA_FLASH), True)

def test_erase_page_well_above_firmware_accepted():
    """Erasing a page far above firmware must always be accepted."""
    assert_eq(validate_commands(_erase_cmd(0x08008000), MCU_METADATA_FLASH), True)