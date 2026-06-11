# STM32 Platform

This document covers STM32-specific reference material: supported cores,
the two processing modes, flash write/erase semantics, dual-bank
handling, and how to add a new core. For build invocation, flashing, and
user-project integration see `docs/how-to-build.md`.


## Supported cores

| Core | Families |
|---|---|
| Cortex-M0 | STM32F030xx, STM32F070xx |
| Cortex-M3 | STM32F103xx |

The build system picks the right core automatically based on the `MCU`
value passed at build time. Flash and RAM sizes are resolved by
preprocessing the linker script with `#ifdef` guards, so there is no
separate linker script per MCU variant.


## Processing modes

STM32 supports two ways of handling inbound UART packets. The mode is
selected at build time via `MDT_USE_UART_IDLE` (see
`docs/how-to-build.md` for the flag itself) and is written to
`build_info.yaml` so the PC tool knows whether to send periodic
event-poll packets.

### Interrupt mode (`MDT_USE_UART_IDLE=1`, default)

USART1 fires three interrupt sources:

* **RXNE**, a byte arrived. It is pushed into the RX ring buffer
  immediately.
* **IDLE**, the RX line went quiet after a burst (a full packet just
  landed).
* **TXE**, the TX register is empty. The next byte is popped from the TX
  ring buffer and sent.

When the IDLE interrupt fires, PendSV is triggered at the lowest
interrupt priority. `PendSV_Handler` calls `mdt_process_pending()`, which
drains the RX ring buffer and dispatches the packet. The `main()` loop
runs freely between PendSV invocations.

Because `mcu_mdt_poll()` is never called in this mode, the MCU cannot
push events on its own. Instead the PC tool sends a CMD_ID=0 poll packet
every 500 ms. The MCU's `handle_reserved()` responds with any pending
event payload, and the PC `rx_worker` routes the response to the event
queue.

Use this mode when your application does not have a tight cooperative
main loop. For example if it uses `HAL_Delay()`, blocking I2C/SPI
transactions, or any other operation that stalls the loop for more than
a few milliseconds.

### Poll mode (`MDT_USE_UART_IDLE=0`)

RXNE and TXE interrupts still run (the ring buffers are always
ISR-driven), but the IDLE interrupt is not used. The `main()` loop has
to call `mcu_mdt_poll()` regularly. Each call flushes any pending event,
drains the RX ring buffer, and checks watchpoints:

```
main loop
  └── mcu_mdt_poll()
        1. flush pending event if TX idle
        2. fence + overflow guard
        3. drain RX ring buffer -> packet dispatch
        4. mcu_mdt_watchpoint_check()
```

In poll mode the PC tool does not send CMD_ID=0 poll packets.
`build_info.yaml` will contain `uart_idle: 0` and the PC tool's
`event_poll_worker` thread is not started. Events are delivered
automatically by `mcu_mdt_poll()` at step 1.

Use this mode when your main loop is tight and runs frequently (every
few ms or less), or when you want deterministic, application-controlled
timing for packet processing.

### Which mode to choose

| Situation | Recommended mode |
|---|---|
| Application uses `HAL_Delay()` or blocking calls | Interrupt |
| Application has no main loop (RTOS task-based) | Interrupt |
| Tight cooperative main loop running continuously | Poll |
| You want deterministic packet timing | Poll |
| Default / unsure | Interrupt |

The choice has no effect on the protocol. Packet format, CRC, commands,
and events are identical in both modes. The only difference is which
side initiates event delivery.


## Cortex-M0 details (F030xx / F070xx)

Reference manual: RM0360.

* UART: USART1 on PA9 (TX) and PA10 (RX), AF1. Ring-buffer driven with
  RXNE, TXE, and IDLE interrupts. IDLE triggers PendSV (lowest priority)
  for packet processing.
* Clock assumes 8 MHz HSI by default. Pass `F_CPU` if running at a
  different frequency (see `docs/how-to-build.md`).
* Flash writes are half-word (16-bit) only. Cortex-M0 hard-faults on
  other widths. The HAL enforces this.
* HSI must be enabled for all flash write and erase operations
  (RM0360 §3.1). The HAL handles this automatically inside
  `flash_unlock()`.

| MCU    | Part numbers       | Flash  | RAM   | Page size | Notes                      |
|--------|--------------------|--------|-------|-----------|----------------------------|
| F030F4 | STM32F030F4P6      | 16 KB  | 4 KB  | 1 KB      | Primary development target |
| F030F6 | STM32F030F6P6      | 32 KB  | 4 KB  | 1 KB      |                            |
| F030F8 | STM32F030F8P6      | 64 KB  | 8 KB  | 1 KB      |                            |
| F030C6 | STM32F030C6T6      | 32 KB  | 4 KB  | 1 KB      | LQFP48                     |
| F030C8 | STM32F030C8T6      | 64 KB  | 8 KB  | 1 KB      | LQFP48                     |
| F030CC | STM32F030CCT6      | 256 KB | 32 KB | 2 KB      | LQFP48, largest F030       |
| F070F6 | STM32F070F6P6      | 32 KB  | 6 KB  | 1 KB      | USB device support         |
| F070CB | STM32F070CBT6      | 128 KB | 16 KB | 2 KB      | USB device support         |
| F070RB | STM32F070RBT6      | 128 KB | 16 KB | 2 KB      | LQFP64, USB device support |


## Cortex-M3 details (F103xx)

Reference manual: RM0008.

* UART: USART1 on PA9 (TX) and PA10 (RX), configured via the CRH
  register (F1 GPIO style). Ring-buffer driven with RXNE, TXE, and IDLE
  interrupts.
* The IDLE flag is cleared by the SR -> DR read sequence (required on
  F1 series).
* Flash writes are half-word (16-bit) only.
* HSI must be enabled for all flash operations (RM0008 §3.3.3). The HAL
  enables it automatically in `flash_unlock()`.

| Density | Example parts              | Flash   | RAM    | Page size | Notes                  |
|---------|----------------------------|---------|--------|-----------|------------------------|
| F103x4  | STM32F103C4, R4, T4        | 16 KB   | 6 KB   | 1 KB      | Low                    |
| F103x6  | STM32F103C6, R6, T6        | 32 KB   | 10 KB  | 1 KB      | Low                    |
| F103x8  | STM32F103C8, R8, T8, V8    | 64 KB   | 20 KB  | 1 KB      | Medium                 |
| F103xB  | STM32F103CB, RB, TB, VB    | 128 KB  | 20 KB  | 1 KB      | Medium                 |
| F103xC  | STM32F103RC, VC, ZC        | 256 KB  | 48 KB  | 2 KB      | High                   |
| F103xD  | STM32F103RD, VD, ZD        | 384 KB  | 64 KB  | 2 KB      | High                   |
| F103xE  | STM32F103RE, VE, ZE        | 512 KB  | 64 KB  | 2 KB      | High                   |
| F103xF  | STM32F103RF, VF, ZF        | 768 KB  | 96 KB  | 2 KB      | XL, dual-bank          |
| F103xG  | STM32F103RG, VG, ZG        | 1024 KB | 96 KB  | 2 KB      | XL, dual-bank          |

Any package variant (C=LQFP48, R=LQFP64, T=VFQFPN36, V=LQFP100,
Z=LQFP144) at a given density maps to the same linker script entry. Pass
the density letter in the `MCU` argument:

```
MCU=F103C8   # LQFP48, 64 KB flash
MCU=F103RB   # LQFP64, 128 KB flash
```


### XL-density dual-bank (F103xF, F103xG)

F103xF and F103xG have 1 MB of flash split into two independent 512 KB
banks:

| Bank | Address range             | Control registers               |
|------|---------------------------|---------------------------------|
| 1    | 0x08000000 - 0x0807FFFF   | FLASH_CR, FLASH_SR, FLASH_AR    |
| 2    | 0x08080000 - 0x080FFFFF   | FLASH_CR2, FLASH_SR2, FLASH_AR2 |

The HAL picks the right register set automatically based on the address.
Any write or erase to an address `>= 0x08080000` uses the bank 2
registers. Both banks are unlocked independently using their own key
registers.

The build system passes `-DFLASH_XL_DENSITY` for F103xF and F103xG. All
bank-2 code is compiled out on non-XL targets with
`#ifdef FLASH_XL_DENSITY`.


## Flash write and erase

STM32 flash must be erased before writing. The Cortex-M0 and Cortex-M3
flash controllers only support half-word (16-bit) writes; the HAL
enforces this.

Typical sequence from the PC tool:

```
WRITE_MEM ERASE 0x08004000 4 00000000   # erase 1 KB page at 0x08004000
WRITE_MEM FLASH 0x08004000 4 DEADBEEF   # program 4 bytes
READ_MEM  FLASH 0x08004000 4            # verify readback
```

The PC validator prevents writes and erases that would touch the running
firmware image. The firmware-occupied range
(`firmware_start_address` to `firmware_end_address`) is read from
`build_info.yaml` and checked before every FLASH write and ERASE
command.

Page sizes:

* **1 KB pages**: F030x4/x6/x8, F070x6, F103x4/x6/x8/xB (low and medium
  density).
* **2 KB pages**: F030xC, F070xB, F103xC/D/E/F/G (high, XL, and
  connectivity density).

For ERASE the MCU computes the page base address from the given address
and `FLASH_PAGE_SIZE` (injected by the Makefile at compile time). The
user can pass any address within the target page.


## Adding a new STM32 core

To add support for a new Cortex core (for example Cortex-M4 for
STM32F4xx):

1. Create `hal/stm32/cortex-m4/` with:
   * `hal_stm.c` implementing all HAL functions (UART driver + memory
     access).
   * `uart.h` with peripheral register structs and bit masks for the
     target family.
   * `commands.h` with the FLASH register map, bit defines, key values,
     and FLASH_PAGE_SIZE guard.
   * `Makefile` copied from `cortex-m0/` with `CPU_FLAGS` and MCU
     mapping adjusted.
   * `startup_<device>.c` for the target.
   * `linker.ld` with `#ifdef` guards for flash and RAM sizes.
2. Add the MCU family mapping in `hal/stm32/Makefile` (the router).
3. `src/` is not modified.


## Application notes

1. **Do not use USART1** in your application code. It is owned by the
   MDT UART driver.
2. **SVD files for register validation** live in
   `pc_tool/mcu_db/stm32/`. Add an SVD plus YAML config to support a
   new STM32 family in the PC tool validator.
3. **HSI must be running during flash operations.** The HAL enables it
   automatically in `flash_unlock()`. If your application disables HSI
   after startup, be aware that the first flash operation after MDT
   starts will re-enable it.
4. **Always erase a flash page before writing to it.** Writing to a
   non-erased page sets PGERR in FLASH_SR and the MCU returns an error
   response. The PC-side `flash_is_erased()` pre-check catches this
   before the program register is even set, providing a cleaner failure
   path.
   
## Flash operation timing constraints

A page erase stalls the CPU for up to ~40 ms, because the firmware executes
from the same flash bank being erased and the controller stalls all flash
fetches for the duration. During this window the UART RX interrupt cannot
run and the USART has only a 1-byte hardware buffer. The MDT protocol is
strictly request/response, so the PC tool never transmits while an ERASE is
pending — but any custom client must respect the same rule: **do not send
data while an ERASE or FLASH write is outstanding.**

Writes near memory boundaries: a 3–4-byte FLASH write programs two
halfwords (`address` and `address + 2`). The firmware does not know the
part's flash size, so a write whose second halfword would fall past the end
of flash is only rejected by the PC-side validator, not on-target. On
XL-density F103 parts a write straddling the bank-1/bank-2 seam
(0x0807FFFE) is handled correctly on-target (both banks are unlocked).