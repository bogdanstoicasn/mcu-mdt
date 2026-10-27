# MCU MDT Commands Reference

Every command, its parameters, and what it does. Names are case-insensitive. Numbers are hex
unless the parameter says decimal: `10` as a slot id is slot 16, `10` as a length is ten bytes.
`0x` works on both.

| Parameter type | Accepts |
|---|---|
| hex | `1F` or `0x1F` |
| decimal | `10`, or hex with `0x` |
| address | a hex address, or a RAM variable of the ELF (`rx_buffer`; a local static `count` matches `count.0`) |
| register | a hex address, or a register name (see READ_REG) |
| bytes | a hex string: `DEADBEEF` or `0xDEADBEEF` |
| choice | one of the names in the tables below |


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

A command takes only the names of its own table (READ_MEM: RAM, FLASH, EEPROM). `BREAKPOINT 0 MASK`
is rejected even though MASK and NEXT are both 3. Each parameter's `values` in
`pc_tool/configs/commands.yaml` are the names it takes and the numbers sent.


## Protocol Commands

These commands are serialized and sent over UART to the MCU.


### READ_MEM (ID: 0x01)

**Description:** Reads `len` bytes from the specified memory zone starting at `address`.

**Parameters:**

| Name    | Type    | Description                              |
|---------|---------|------------------------------------------|
| zone    | choice  | Memory zone: RAM, FLASH, EEPROM          |
| address | address | Start address, or a RAM variable         |
| len     | decimal | Number of bytes to read                  |

**Behavior:** Each reply carries 4 bytes in DATA. More than 4 bytes are read one word per packet,
and every reply is shown. The PC tool refuses a range that leaves the part's memory of that zone.


### WRITE_MEM (ID: 0x02)

**Description:** Writes `len` bytes to the specified memory zone starting at `address`,
or erases a flash page (zone `ERASE`).

**Parameters:**

| Name    | Type    | Description                              |
|---------|---------|------------------------------------------|
| zone    | choice  | Memory zone: RAM, FLASH, EEPROM, ERASE   |
| address | address | Start address, or a RAM variable         |
| len     | decimal | Number of bytes to write (the data's length) |
| data    | bytes   | Data to write (ignored for ERASE)        |

**Behavior by zone:**

- **RAM**: direct SRAM write, always allowed. Out-of-range addresses are rejected by
  the PC tool.
- **FLASH**: half-word (16-bit) programming on STM32. The target area must be erased
  first using the `ERASE` zone. Flash writes that overlap the running firmware image are
  rejected by the PC tool to prevent self-corruption. Only addresses past the end of
  the firmware image (read from the ELF) are accepted.
- **EEPROM**: AVR only. Passed through to `eeprom_write_block()`.
- **ERASE**: STM32 only. Erases the flash page containing `address`. The page
  boundary is computed on the MCU (`data` and `len` are ignored by the firmware). The PC
  tool rejects the command if the page overlaps the running firmware image. Always
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

| Name    | Type     | Description                                |
|---------|----------|--------------------------------------------|
| address | register | Register address (hex) or name (see below) |

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

Array registers take either spelling: `DMA_CH[3]` is `DMA_CH3`. SVD cluster registers are
joined with `_`, as the vendor headers join them (`CTIMER0_MR0`, `CH0_CTRL`).

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

| Name    | Type     | Description                                    |
|---------|----------|------------------------------------------------|
| address | register | Register address (hex) or name (see READ_REG)  |
| data    | bytes    | Value to write                                 |

**Behavior:** Accepts the same name formats as READ_REG. A register the description file marks
read-only is refused.

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


### BREAKPOINT (ID: 0x07)

**Description:** Controls a software breakpoint by slot ID.

**Parameters:**

| Name    | Type   | Description                                         |
|---------|--------|-----------------------------------------------------|
| id      | hex    | Breakpoint slot (0 to `MDT_MAX_BREAKPOINTS-1`, `breakpoints` in `build_info.yaml`) |
| control | choice | Control value: DISABLED, ENABLED, RESET, NEXT       |

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
- Maximum slots: `MDT_MAX_BREAKPOINTS`, set with `make ... BREAKPOINTS=` (default 4, max 8).


### WATCHPOINT (ID: 0x08)

**Description:** Controls a memory watchpoint by slot ID. Fires a `WATCHPOINT_HIT` event when
monitored bits change value.

**Parameters:**

| Name    | Type   | Description                                              |
|---------|--------|----------------------------------------------------------|
| id      | hex     | Watchpoint slot (0 to `MDT_MAX_WATCHPOINTS-1`, `watchpoints` in `build_info.yaml`) |
| control | choice  | Control value: DISABLED, ENABLED, RESET, MASK            |
| value   | address | ENABLED: the address or RAM variable to watch. MASK: the 32-bit mask. Optional for DISABLED and RESET |

```
WATCHPOINT 0 ENABLED rx_count     # watch a variable of the ELF
WATCHPOINT 0 MASK 000000FF        # only its low byte
WATCHPOINT 0 RESET                # done; the value can be left out
```

**Behavior:**

- **ENABLED**: arms the watchpoint at the address provided in `data`. Takes an initial snapshot
  and fires a `WATCHPOINT_HIT` event whenever any masked bits at that address change. Default mask
  is `0xFFFFFFFF` (all bits).
- **DISABLED**: disarms the watchpoint. The slot address and snapshot are preserved.
- **RESET**: disarms and clears the slot (address, snapshot, mask all zeroed).
- **MASK**: sets the bit mask for an already-active slot. Only the bits set in the mask are
  compared on each sample. Slot must be active (ENABLED) for MASK to take effect.

**Notes:**
- Watchpoints are sampled whenever events are polled: every `mcu_mdt_poll()` pass in poll mode,
  every PC poll in interrupt mode. Several changes between two samples collapse into one event
  (old = value at the last report, new = latest value).
- The MCU reads 4 bytes byte-by-byte at the watched address, making it safe at any alignment.
  Unaligned addresses produce a PC-side warning but are not rejected. Watching a variable
  narrower than 4 bytes warns too, with the MASK that keeps only its bytes.
- The 4 watched bytes must lie in RAM, or the address must be a register of the part (from its
  ATDF/SVD). Anything else is rejected: the MCU reads the address on every sample, and an
  unmapped address faults an STM32. A register that changes when read (a USART data register,
  some status flags) is changed by every sample too: watch those only if that is intended.
- Maximum slots: `MDT_MAX_WATCHPOINTS`, set with `make ... WATCHPOINTS=` (default 4, max 8).


## CLI-Only Commands

These commands are handled entirely on the PC side and are never sent over UART.

| Command | Description                    |
|---------|--------------------------------|
| HELP    | Print available commands       |
| EXIT    | Close the serial link and quit |
| CLEAR   | Clear the console screen       |

The prompt keeps a history (arrow keys) in `~/.mcu_mdt_history`, and TAB completes command
names. In a script, these three are skipped with a warning.


## Scripts

```bash
mcu-mdt build/f030f4/build_info.yaml --script commands.txt
```

One command per line; blank lines and `#` comments are skipped. The script stops at the first
line that fails (parse error, refused by the rules, no reply), and the tool exits with status 1.
Nothing is printed while it runs: the log file in `logs/` has the whole session.


## Notes

- All multi-byte fields (address, length, data) are little-endian.
- Data payload per packet is 4 bytes maximum. Larger transfers are split automatically by the PC.
- Flash writes and erases on STM32 are protected: any command that would overwrite the firmware
  image is rejected by the PC tool before the packet is sent. The protected range is the
  part of the firmware ELF that loads into flash, which the PC tool reads at start-up.
- Adding a new command: add its id to `mdt_cmd_t` in `mcu_mdt_protocol.h` and to `CommandId` in
  `pc_tool/wire_protocol.py`, a handler in `mcu_mdt_protocol.c`, and an entry in
  `pc_tool/configs/commands.yaml` (each parameter names its `type`, the packet `field` it fills,
  and a choice's `values`). A rule in `pc_tool/command_rules.py` if it needs one.
  `test_wire_contract.py` checks the ids match on both sides.
