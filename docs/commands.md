# MCU MDT Commands Reference

This document describes all supported MCU MDT commands, their parameters, and expected behavior.


## Memory Zones

Used with READ_MEM, WRITE_MEM, READ_REG, WRITE_REG.

| Name   | Value | Description                               |
|--------|-------|-------------------------------------------|
| RAM    | 0     | MCU internal SRAM                         |
| FLASH  | 1     | MCU program memory (read-only by default) |
| EEPROM | 2     | MCU internal EEPROM                       |

## Breakpoint Control Values

Used with the BREAKPOINT command.

| Name     | Value | Description                          |
|----------|-------|--------------------------------------|
| DISABLED | 0     | Disable the breakpoint               |
| ENABLED  | 1     | Enable the breakpoint                |
| RESET    | 2     | Reset hit count and state            |
| NEXT     | 3     | Resume execution from the breakpoint |


## Protocol Commands

These commands are serialized and sent over UART to the MCU.


### READ_MEM (ID: 0x01)

**Description:** Reads `len` bytes from the specified memory zone starting at `address`.

**Parameters:**

| Name     | Type   | Description                     |
|----------|--------|---------------------------------|
| mem_type | str    | Memory zone: RAM, FLASH, EEPROM |
| address  | uint32 | Start address to read from      |
| len      | uint32 | Number of bytes to read         |

**Behavior:** Returns the requested bytes in the response data field. Transfers larger than 4 bytes
are split into multiple packets automatically. Reading outside valid memory ranges returns an error.


### WRITE_MEM (ID: 0x02)

**Description:** Writes `len` bytes to the specified memory zone starting at `address`.

**Parameters:**

| Name     | Type   | Description                     |
|----------|--------|---------------------------------|
| mem_type | str    | Memory zone: RAM, FLASH, EEPROM |
| address  | uint32 | Start address to write to       |
| len      | uint32 | Number of bytes to write        |
| data     | bytes  | Data to write                   |

**Behavior:** RAM and EEPROM writes are allowed. FLASH writes are rejected by default. Out-of-range
addresses are rejected. Transfers larger than 4 bytes are split into multiple packets automatically.


### READ_REG (ID: 0x03)

**Description:** Reads a single value from a memory-mapped register at `address`.

**Parameters:**

| Name    | Type   | Description              |
|---------|--------|--------------------------|
| address | uint32 | Register address to read |

**Behavior:** Returns the register value (1 byte) in the response data field.


### WRITE_REG (ID: 0x04)

**Description:** Writes a value to a memory-mapped register at `address`.

**Parameters:**

| Name    | Type   | Description               |
|---------|--------|---------------------------|
| address | uint32 | Register address to write |
| data    | bytes  | Value to write (1 byte)   |

**Behavior:** Invalid or out-of-range addresses are rejected.


### PING (ID: 0x05)

**Description:** Checks that the communication link to the MCU is alive.

**Behavior:** MCU responds with an ACK packet. No side effects.


### RESET (ID: 0x06)

**Description:** Resets the MCU.

**Behavior:** MCU restarts from its reset vector. All runtime state and breakpoints are cleared.

> **Note:** Not yet implemented in firmware.


### BREAKPOINT (ID: 0x0A)

**Description:** Controls a software breakpoint by ID.

**Parameters:**

| Name     | Type   | Description                                  |
|----------|--------|----------------------------------------------|
| id       | uint32 | Breakpoint ID (0 to `MDT_MAX_BREAKPOINTS-1`) |
| mem_type | str    | Control: DISABLED, ENABLED, RESET, NEXT      |

**Behavior:**

- **ENABLED** — arms the breakpoint. MCU will pause execution the next time
  `MDT_BREAKPOINT(id)` is reached in firmware.
- **DISABLED** — disarms the breakpoint. Execution passes through without pausing.
- **RESET** — clears hit count and state without changing enabled status.
- **NEXT** — if the MCU is currently paused at this breakpoint, resumes execution.

**Notes:**
- `mcu_mdt_poll()` must be called frequently in the main loop for breakpoints to work.
- Blocking calls like `delay()` temporarily freeze breakpoint handling while blocking.
- Maximum number of breakpoints is defined by `MDT_MAX_BREAKPOINTS` in `mcu_mdt_config.h`.


## CLI-Only Commands

These commands are handled entirely on the PC side and are never sent over UART.

| Command | Description                        |
|---------|------------------------------------|
| HELP    | Print available commands           |
| EXIT    | Close the serial link and quit     |
| CLEAR   | Clear the console screen           |
| PING    | Also usable as a CLI shortcut      |


## Notes

- All multi-byte fields (address, length) are little-endian.
- Data payload per packet is 4 bytes maximum. Larger transfers are split automatically by the PC tool.
- Adding a new command requires: adding the ID to `mdt_cmd_t` in `mcu_mdt_protocol.h`, adding a
  case in `mdt_dispatch()`, and adding the command definition to `commands.yaml`.