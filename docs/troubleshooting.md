# Troubleshooting

This document covers common problems encountered during development and use of MCU-MDT,
and the steps taken to resolve them.


## Connection and Communication


### No response to PING

**Symptoms:** `PING` returns no response or times out immediately.

**Check in order:**

1. Baud rate mismatch. The firmware baud rate is set at compile time via
   `MDT_UART_BAUDRATE` in `mcu_mdt_config.h` (default 19200). The PC tool reads
   `MDT_BAUD` from the environment. If they differ, every byte is corrupted.
   ```bash
   MDT_BAUD=19200 python3 mcu_mdt.py build/F030F4/build_info.yaml
   ```

2. Wrong port. Check which port the MCU is on:
   ```bash
   ls /dev/tty{ACM,USB}*   # Linux
   ls /dev/cu.*             # macOS
   ```

3. TX/RX crossed. MCU TX → USB-UART RX, MCU RX → USB-UART TX. Swap the wires
   if in doubt.

4. Wrong CPU frequency. The UART baud rate divisor is `F_CPU / BAUDRATE`. If
   `F_CPU` does not match the actual clock (e.g. PLL not configured, external
   crystal missing), the baud rate will be wrong. Pass the correct frequency:
   ```bash
   make PLATFORM=stm32 MCU=F030F4 PORT=... F_CPU=8000000UL
   ```

5. USART not enabled. On STM32, check that `RCC_APB2ENR_USART1EN` is set in
   `RCC->apb2enr`. If your application resets peripheral clocks, USART1 may
   be disabled.


### UART communication is intermittent or garbled

**Cause:** Incorrect CPU frequency leading to a slightly wrong baud rate divisor. At
low speeds (9600–19200 baud) a 5–10% clock error may still pass most bytes but corrupt
others randomly.

**Fix:** Verify the actual system clock. On STM32 the default is the 8 MHz HSI.
If the application configures a PLL or uses an external oscillator, pass the real
`F_CPU` at build time. A multimeter or oscilloscope on the TX pin confirms the actual
bit period.


### Bad CRC errors on every packet

**Symptoms:** Every command returns a NACK; the hardware test `test_hw_bad_crc_triggers_nack`
passes but legitimate commands fail.

**Cause:** Byte corruption in transit. On a shared bus (RS-485, long cables),
line capacitance causes bit errors. On short USB-UART cables this is rare.

Also check: if `mcu_mdt_poll()` is not called frequently enough between packets, the
RX ring buffer can overflow and corrupt the byte stream. The MCU sends a
`BUFFER_OVERFLOW` event in this case — watch for it on the PC.


### MCU unresponsive after a RESET command

The RESET command triggers `AIRCR` on STM32 or a watchdog-based reset on AVR. The MCU
reinitializes completely. Wait ~100 ms before sending the next packet. The PC tool's
connection does not re-open automatically — exit and restart `mcu_mdt.py` after a reset.


## Flash Operations


### FLASH write returns error even after ERASE

**Cause 1 — Halfword alignment.** On STM32, flash writes must be halfword-aligned
(address must be divisible by 2). The PC validator rejects unaligned writes, but if
you bypass the validator the MCU returns an error.

**Cause 2 — Address inside firmware.** The PC validator rejects any write or erase
that would touch the firmware image. Check `firmware_end_address` in `build_info.yaml`
and ensure your target address is above it:
```yaml
firmware_end_address: 0x080034a0   # must write above this
```

**Cause 3 — HSI not running.** RM0360 and RM0008 require the HSI oscillator to be
active during flash operations. The HAL enables it automatically in `flash_unlock()`,
but if your application explicitly disables HSI after startup it may be off by the time
a flash command arrives. The flash operation then hangs on the BSY poll or completes
with PGERR. Re-enable HSI or restructure the clock configuration.

**Cause 4 — Page not erased.** Writing to a non-erased flash cell sets PGERR and the
MCU returns an error response. Always run `WRITE_MEM ERASE` on the page first.


### ERASE command rejected by the PC validator

The PC validator computes the full page that would be erased from the given address and
`flash_page_size` (from `build_info.yaml`). If any part of that page falls within
`[firmware_start_address, firmware_end_address)` the command is rejected.

Free flash starts at `firmware_end_address`. The first erasable page is the one whose
base address is at or above `firmware_end_address`. Page size is 1 KB or 2 KB depending
on the MCU density — see `flash_page_size` in `build_info.yaml`.

```
# Example: firmware_end = 0x08003000, page_size = 0x400
# First safe erase: 0x08003000
WRITE_MEM ERASE 0x08003000 4 00000000   ✅
WRITE_MEM ERASE 0x08002C00 4 00000000   ❌ overlaps firmware
```


### Flash write works in debug but not in release

If your application changes the system clock configuration (switching from HSI to PLL or
HSE), the UART baud rate divisor becomes wrong after the clock switch unless `F_CPU`
matches the new clock. Recompute the baud rate register value for the new clock and
rebuild, or keep MDT's UART initialization after the clock switch.


## Breakpoints


### Breakpoint never fires

1. `MDT_BREAKPOINT(id)` must be placed in the user code path that executes.
2. The breakpoint slot must be enabled: `BREAKPOINT 0 ENABLED`.
3. In poll mode, `mcu_mdt_poll()` must be called frequently in the main loop.
   Breakpoints are checked inside `mcu_mdt_poll()` — a loop that never reaches
   `mcu_mdt_poll()` (e.g. blocked in a delay) will never fire the event.
4. In interrupt mode (STM32 default), the PendSV handler processes incoming
   packets. If PendSV is starved by higher-priority interrupts the breakpoint
   command may not be received.


### MCU stays stuck at breakpoint

Send `BREAKPOINT <id> NEXT` from the PC to resume execution. If the PC tool has
exited or the UART link is broken, `BREAKPOINT <id> DISABLED` also resumes.
On AVR in poll mode, a hardware reset also clears the breakpoint state.


## Watchpoints


### Watchpoint fires immediately after being enabled

The watchpoint takes an initial snapshot when ENABLED. If the watched address
changes between the ENABLE command being processed and the next
`mcu_mdt_watchpoint_check()` call, a hit fires immediately. This is correct behavior
— the address changed. Use `WATCHPOINT <id> RESET` followed by `WATCHPOINT <id> ENABLED`
to re-arm and take a fresh snapshot.


### Watchpoint never fires despite value changing

1. Check the mask: if `WATCHPOINT <id> MASK` was used with a mask that does not cover
   the changing bits, the change is invisible. Default mask is `0xFFFFFFFF`.
2. `mcu_mdt_watchpoint_check()` must be called periodically. On STM32 in interrupt mode
   it is not called automatically — call it from a SysTick handler or timer ISR.


## Build System


### Linker script not found or wrong memory sizes

The STM32 linker script is preprocessed by the Makefile before linking to resolve
`#ifdef MCU_<name>` guards. The preprocessed output is `build/<MCU>/linker_pp.ld`.
If you see wrong flash or RAM sizes, check that the `MCU` variable matches an entry
in the `ifeq` chain in `hal/stm32/cortex-m0/Makefile` or `hal/stm32/cortex-m3/Makefile`.


### `Reset_Handler` crashes immediately

On Cortex-M, startup code is marked `__attribute__((naked))` deliberately. Without
`naked`, the compiler generates a function prologue that tries to set up a stack frame
before the stack pointer is initialized — which causes an immediate fault.
The startup file must not be modified to remove `naked` or `noreturn`.


### `build_info.yaml` shows wrong firmware size

`build_info.yaml` is generated after linking, from `wc -c` on the `.bin` file. If the
`.bin` file is stale (from a previous build), the size will be wrong. Run `make clean`
and rebuild from scratch.


## Register Access


### READ_REG by name returns "register not found"

The name is looked up in two stages: qualified `PERIPHERAL_REGISTER` first, then bare
name fallback. If the peripheral or register name does not match the SVD/ATDF database
exactly (case-insensitive), the lookup returns `None` and the command is rejected.

Use the exact name from the SVD or ATDF file. For STM32, peripheral names are uppercase
(`RCC`, `GPIOA`, `USART1`). Register names follow the same case as the SVD
(`CR`, `IDR`, `SR`). Examples:
```
READ_REG RCC_CR        ✅
READ_REG rcc_cr        ✅  (case-insensitive)
READ_REG RCC.CR        ❌  (dot separator not supported, use underscore)
READ_REG CR            ✅  (bare fallback, first match wins)
```


## Known Issues

- **NACK format mismatch** — `is_nack_packet()` on the PC side requires `cmd_id == 0`,
  but the firmware echoes the original `cmd_id` in the NACK. The hardware tests
  `test_hw_bad_crc_triggers_nack` and `test_hw_nack_seq_mirrors_request_seq` are
  affected. One side needs to be updated to agree on the format.

- **`RESET` command not implemented in firmware** — the MCU returns an error flag.
  A hardware reset via the physical NRST pin or the ST-Link is the current workaround.

- **UART IDLE interrupt mode not covered by hardware tests** — all hardware tests run
  the poll path. The STM32 interrupt-driven path (`MDT_USE_UART_IDLE=1`) is the
  default but has no dedicated hardware test suite.