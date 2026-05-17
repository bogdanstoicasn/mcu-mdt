# MCU MDT Commands Reference

This document describes all supported MCU MDT commands, their parameters, and expected behavior.


## Memory Zones

Used with READ_MEM and WRITE_MEM.

| Name   | Value | Description                                                              |
|--------|-------|--------------------------------------------------------------------------|
| RAM    | 0     | MCU internal SRAM                                                        |
| FLASH  | 1     | MCU program memory (read on all platforms, write on STM32)               |
| EEPROM | 2     | MCU internal EEPROM (AVR only)                                           |
| ERASE  | 3     | Erase the flash page containing the given address (STM32 only)           |

## Breakpoint Control Values

Used with the BREAKPOINT command.

| Name     | Value | Description                          |
|----------|-------|--------------------------------------|
| DISABLED | 0     | Disable the breakpoint               |
| ENABLED  | 1     | Enable the breakpoint                |
| RESET    | 2     | Reset                                |
| NEXT     | 3     | Resume execution from the breakpoint |

## Watchpoint Control Values

Used with the WATCHPOINT command.

| Name     | Value | Description                                              |
|----------|-------|----------------------------------------------------------|
| DISABLED | 0     | Disable the watchpoint                                   |
| ENABLED  | 1     | Enable the watchpoint at the given address               |
| RESET    | 2     | Disable and clear the watchpoint slot                    |
| MASK     | 3     | Set the bit mask for an already-active watchpoint slot   |


## Protocol Commands

These commands are serialized and sent over UART to the MCU.


### READ_MEM (ID: 0x01)

**Description:** Reads `len` bytes from the specified memory zone starting at `address`.

**Parameters:**

| Name    | Type   | Description                              |
|---------|--------|------------------------------------------|
| zone    | str    | Memory zone: RAM, FLASH, EEPROM          |
| address | uint32 | Start address to read from               |
| len     | uint16 | Number of bytes to read (1–4)            |

**Behavior:** Returns the requested bytes in the DATA field of the response. Transfers larger than
4 bytes are split into multiple packets automatically. Reading outside valid memory ranges returns
an error response.


### WRITE_MEM (ID: 0x02)

**Description:** Writes `len` bytes to the specified memory zone starting at `address`,
or erases a flash page (zone `ERASE`).

**Parameters:**

| Name    | Type   | Description                              |
|---------|--------|------------------------------------------|
| zone    | str    | Memory zone: RAM, FLASH, EEPROM, ERASE   |
| address | uint32 | Start address to write to                |
| len     | uint16 | Number of bytes to write (1–4)           |
| data    | bytes  | Data to write (ignored for ERASE)        |

**Behavior by zone:**

- **RAM**: direct SRAM write, always allowed. Out-of-range addresses are rejected by
  the PC validator.
- **FLASH**: half-word (16-bit) programming on STM32. The target area must be erased
  first using the `ERASE` zone. Flash writes that overlap the running firmware image are
  rejected by the PC validator to prevent self-corruption. Only addresses at or above
  `firmware_end_address` (from `build_info.yaml`) are accepted.
- **EEPROM**: AVR only. Passed through to `eeprom_write_block()`.
- **ERASE**: STM32 only. Erases the flash page containing `address`. The page
  boundary is computed on the MCU (`data` and `len` are ignored by the firmware). The PC
  validator rejects the command if the page overlaps the running firmware image. Always
  erase before writing to flash.

**STM32 flash erase and write sequence:**
```
WRITE_MEM ERASE 0x08004000 4 00000000   # erase the page (data ignored)
WRITE_MEM FLASH 0x08004000 4 CAFEBABE   # write to the erased page
READ_MEM  FLASH 0x08004000 4            # verify
```

**Platform availability:**

| Zone   | AVR | STM32 Cortex-M0 | STM32 Cortex-M3 |
|--------|-----|-----------------|-----------------|
| RAM    | yes | yes             | yes             |
| FLASH  | no  | yes             | yes             |
| EEPROM | yes | no              | no              |
| ERASE  | no  | yes             | yes             |


### READ_REG (ID: 0x03)

**Description:** Reads a memory-mapped register by address or by name.

**Parameters:**

| Name    | Type          | Description                                |
|---------|---------------|--------------------------------------------|
| address | uint32 or str | Register address (hex) or name (see below) |

**Register names:**

Registers can be identified by name instead of raw address. The PC tool resolves the
name to an absolute address using the SVD (STM32) or ATDF (AVR) database.

Two formats are accepted:

- **Qualified**: `PERIPHERAL_REGISTER`: recommended form, unambiguous when the same
  register name exists in multiple peripherals.

  ```
  READ_REG RCC_CR        # STM32: RCC control register
  READ_REG USART1_SR     # STM32: USART1 status register
  READ_REG GPIOA_IDR     # STM32: GPIOA input data register
  READ_REG TIM1_CCMR1    # STM32: TIM1 capture/compare mode register
  ```

- **Bare**: register name only. Searches all peripherals in order; first match
  wins. Useful on AVR where register names are globally unique.

  ```
  READ_REG UDR0          # AVR: USART0 data register (no underscore → bare search)
  READ_REG SPDR          # AVR: SPI data register
  READ_REG 0x40013800    # raw hex address always works on both platforms
  ```

**Behavior:** Returns the register value in DATA. On AVR, registers are 8-bit and
1 byte is returned. On STM32, registers are 32-bit and 4 bytes are returned.


### WRITE_REG (ID: 0x04)

**Description:** Writes a value to a memory-mapped register by address or by name.

**Parameters:**

| Name    | Type          | Description                                    |
|---------|---------------|------------------------------------------------|
| address | uint32 or str | Register address (hex) or name (see READ_REG)  |
| data    | bytes         | Value to write                                 |

**Behavior:** Accepts the same name formats as READ_REG.

```
WRITE_REG RCC_CR   00000081   # STM32: by qualified name
WRITE_REG UCSR0A   00         # AVR: by bare name
WRITE_REG 0x40013800 000000FF # raw address
```


### PING (ID: 0x05)

**Description:** Checks that the communication link to the MCU is alive.

**Behavior:** MCU responds with an ACK packet. No side effects.


### RESET (ID: 0x06)

**Description:** Resets the MCU.

**Behavior:** MCU restarts from its reset vector. All runtime state and breakpoints are cleared.

> **Note:** Not yet implemented in firmware. The MCU will respond with an error flag.


### BREAKPOINT (ID: 0x07)

**Description:** Controls a software breakpoint by slot ID.

**Parameters:**

| Name    | Type   | Description                                         |
|---------|--------|-----------------------------------------------------|
| id      | uint32 | Breakpoint slot (0 to `MDT_MAX_BREAKPOINTS-1`)      |
| control | str    | Control value: DISABLED, ENABLED, RESET, NEXT       |

**Behavior:**

- **ENABLED**: arms the breakpoint. The MCU will pause the next time `MDT_BREAKPOINT(id)` is
  reached in firmware and send a `BREAKPOINT_HIT` event.
- **DISABLED**: disarms the breakpoint. Execution passes through without pausing.
- **RESET**: clears all bkpt data.
- **NEXT**: if the MCU is currently paused at this breakpoint, resumes execution.

**Notes:**
- `MDT_BREAKPOINT(id)` must be placed in user firmware code.
- `mcu_mdt_poll()` must be called frequently in the main loop for breakpoints to work in poll mode.
- Blocking calls like `delay()` temporarily freeze breakpoint handling.
- Maximum slots: `MDT_MAX_BREAKPOINTS` in `mcu_mdt_config.h` (default 4, max 8).


### WATCHPOINT (ID: 0x08)

**Description:** Controls a memory watchpoint by slot ID. Fires a `WATCHPOINT_HIT` event when
monitored bits change value.

**Parameters:**

| Name    | Type   | Description                                              |
|---------|--------|----------------------------------------------------------|
| id      | uint32 | Watchpoint slot (0 to `MDT_MAX_WATCHPOINTS-1`)           |
| control | str    | Control value: DISABLED, ENABLED, RESET, MASK            |
| data    | uint32 | ENABLED: address to watch. MASK: 32-bit mask. Others: -  |

**Behavior:**

- **ENABLED**: arms the watchpoint at the address provided in `data`. Takes an initial snapshot
  and fires a `WATCHPOINT_HIT` event whenever any masked bits at that address change. Default mask
  is `0xFFFFFFFF` (all bits).
- **DISABLED**: disarms the watchpoint. The slot address and snapshot are preserved.
- **RESET**: disarms and clears the slot (address, snapshot, mask all zeroed).
- **MASK**: sets the bit mask for an already-active slot. Only the bits set in the mask are
  compared on each sample. Slot must be active (ENABLED) for MASK to take effect.

**Notes:**
- `mcu_mdt_watchpoint_check()` must be called periodically. On AVR `mcu_mdt_poll()` calls it
  automatically. On STM32 interrupt mode you can call it from a SysTick or timer ISR.
- The MCU reads 4 bytes byte-by-byte at the watched address, making it safe at any alignment.
  Unaligned addresses produce a PC-side warning but are not rejected.
- Maximum slots: `MDT_MAX_WATCHPOINTS` in `mcu_mdt_config.h` (default 4, max 8).


## CLI-Only Commands

These commands are handled entirely on the PC side and are never sent over UART.

| Command | Description                    |
|---------|--------------------------------|
| HELP    | Print available commands       |
| EXIT    | Close the serial link and quit |
| CLEAR   | Clear the console screen       |
| HISTORY | Show command history           |


## Notes

- All multi-byte fields (address, length, data) are little-endian.
- Data payload per packet is 4 bytes maximum. Larger transfers are split automatically by the PC.
- Flash writes and erases on STM32 are protected: any command that would overwrite the firmware
  image is rejected by the PC validator before the packet is sent. The protected range is read
  from `firmware_start_address` and `firmware_end_address` in `build_info.yaml`, which the
  Makefile computes from the actual linked binary size at build time.
- Adding a new command requires: adding the ID to `mdt_cmd_t` in `mcu_mdt_protocol.h`, adding a
  handler in `mcu_mdt_protocol.c`, and adding the command definition to `pc_tool/configs/commands.yaml`.
