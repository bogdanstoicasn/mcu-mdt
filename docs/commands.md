# MCU MDT Commands Reference

This document describes all supported MCU MDT commands, their parameters, and expected behavior.

---

## Memory Types

| Name      | Value | Description                          |
|-----------|-------|--------------------------------------|
| RAM       | 0     | MCU internal RAM                     |
| FLASH     | 1     | MCU program memory (read-only by default) |
| EEPROM    | 2     | MCU internal EEPROM                  |
| DISABLED  | 0     | Breakpoint control: disabled        |
| ENABLED   | 1     | Breakpoint control: enabled         |
| RESET     | 2     | Breakpoint control: reset hit count / state |
| NEXT      | 3     | Breakpoint control: continue to next breakpoint |

---

## Commands

### ## READ_MEM (ID: 0x01)

**Description:** Reads `len` bytes from the specified memory type.  

**Parameters:**

| Name      | Type    | Description                     |
|-----------|---------|---------------------------------|
| mem_type  | str     | Memory type: RAM, FLASH, EEPROM |
| address   | uint32  | Start address to read from      |
| len       | uint32  | Number of bytes to read         |

**Behavior:** Returns the requested bytes in the response packet. Attempting to read outside valid memory ranges will generate an error.

---

### ## WRITE_MEM (ID: 0x02)

**Description:** Writes `len` bytes to the specified memory type.  

**Parameters:**

| Name      | Type    | Description                     |
|-----------|---------|---------------------------------|
| mem_type  | str     | Memory type: RAM, FLASH, EEPROM |
| address   | uint32  | Start address to write to       |
| len       | uint32  | Number of bytes to write        |
| data      | bytes   | Data to write                   |

**Behavior:** Writing to FLASH may be restricted; RAM and EEPROM writes are allowed. Out-of-range writes are rejected.

---

### ## READ_REG (ID: 0x03)

**Description:** Reads a single MCU register at the specified address.  

**Parameters:**

| Name      | Type    | Description                     |
|-----------|---------|---------------------------------|
| address   | uint32  | Register address to read        |

**Behavior:** Returns the register value in the response packet.

---

### ## WRITE_REG (ID: 0x04)

**Description:** Writes data to a single MCU register.  

**Parameters:**

| Name      | Type    | Description                     |
|-----------|---------|---------------------------------|
| address   | uint32  | Register address to write       |
| data      | bytes   | Value to write                  |

**Behavior:** Only writes valid memory-mapped registers; invalid addresses are rejected.

---

### ## PING (ID: 0x05)

**Description:** Checks communication with the MCU.  

**Behavior:** The MCU responds with an ACK if the communication link is alive.

---

### ## RESET (ID: 0x06)

**Description:** Resets the MCU.  

**Behavior:** All breakpoints and runtime state are cleared. MCU restarts from its reset vector.

---

### ## EXIT (ID: 0x07)

**Description:** Exits the PC-side CLI.  

**Behavior:** This command has no effect on the MCU.

---

### ## HELP (ID: 0x08)

**Description:** Displays help information for all available commands.  

**Behavior:** PC-side only.

---

### ## CLEAR (ID: 0x09)

**Description:** Clears the PC console screen.  

**Behavior:** PC-side only.

---

### ## BREAKPOINT (ID: 0x0A)

**Description:** Triggers a software breakpoint in the MCU firmware.  

**Parameters:**

| Name      | Type    | Description                                 |
|-----------|---------|---------------------------------------------|
| address   | uint32  | Breakpoint ID (0 to `MDT_MAX_BREAKPOINTS-1`) |
| mem_type  | str     | Control: DISABLED, ENABLED, RESET, NEXT   |

**Behavior:**

- **DISABLED (0):** Turn breakpoint off.  
- **ENABLED (1):** Enable breakpoint. MCU will pause execution when reached.  
- **RESET (2):** Reset hit count / state.  
- **NEXT (3):** If paused at this breakpoint, continue to the next one.  

**Notes:**

- Breakpoints only work if `mcu_mdt_poll()` is called frequently in the main loop.  
- Using blocking delays may temporarily pause breakpoint handling.  