# STM32 Platform

This document covers STM32-specific reference material: supported cores,
the two processing modes, flash write/erase semantics, dual-bank
handling, and how to add a new core. For build invocation, flashing, and
user-project integration see `docs/how-to-build.md`.


## Supported parts

| Core | Families | Build description |
|---|---|---|
| Cortex-M0 | STM32F030xx, STM32F070xx | `build_system/stm32/tree_branch_f0.yaml` |
| Cortex-M3 | STM32F103xx | `build_system/stm32/tree_branch_f1.yaml` |

Only the parts listed as nodes in `build_system/stm32/tree_branch_*.yaml` can be
built; the MCU tables under "Cortex-M0 details" and "Cortex-M3 details" are that list. Each node carries the part's
flash size, RAM size and flash erase page. The build turns them into the linker's
`memory.ld`, the `MDT_FLASH_*` / `MDT_RAM_*` macros in `mdt_target.h` and the memory map
in `build_info.yaml` for the PC tool, so a size is written once.


## Processing modes

STM32 supports two ways of handling inbound UART packets. The mode is
selected at build time via `UART_IDLE` (see
`docs/how-to-build.md` for the flag itself) and is written to
`build_info.yaml` so the PC tool knows whether to send periodic
event-poll packets.

### Interrupt mode (`UART_IDLE=1`, default)

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

### Poll mode (`UART_IDLE=0`)

RXNE and TXE interrupts still run (the ring buffers are always
ISR-driven), but the IDLE interrupt is not used. The `main()` loop has
to call `mcu_mdt_poll()` regularly. Each call reports one pending event
(sampling the watchpoints) and drains the RX ring buffer:

```
main loop
  └── mcu_mdt_poll()
        1. report one pending event if TX idle (samples watchpoints)
        2. fence + overflow guard
        3. drain RX ring buffer -> packet dispatch
```

In poll mode the PC tool does not send CMD_ID=0 poll packets.
`build_info.yaml` will contain `uart_idle: false` and the PC tool's
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

Sizes from the STM32F030/F070 datasheets; erase page per RM0360. Parts with the same
flash and RAM size share their numbers in the YAML (`&anchor` / `*alias`).

| MCU | Part number | Flash | RAM | Page size | Package |
|---|---|---|---|---|---|
| F030F4 | STM32F030F4 | 16 KB | 4 KB | 1 KB | TSSOP20 |
| F030K6 | STM32F030K6 | 32 KB | 4 KB | 1 KB | LQFP32 |
| F030C6 | STM32F030C6 | 32 KB | 4 KB | 1 KB | LQFP48 |
| F030C8 | STM32F030C8 | 64 KB | 8 KB | 1 KB | LQFP48 |
| F030R8 | STM32F030R8 | 64 KB | 8 KB | 1 KB | LQFP64 |
| F030CC | STM32F030CC | 256 KB | 32 KB | 2 KB | LQFP48 |
| F030RC | STM32F030RC | 256 KB | 32 KB | 2 KB | LQFP64 |
| F070F6 | STM32F070F6 | 32 KB | 6 KB | 1 KB | TSSOP20, USB |
| F070C6 | STM32F070C6 | 32 KB | 6 KB | 1 KB | LQFP48, USB |
| F070CB | STM32F070CB | 128 KB | 16 KB | 2 KB | LQFP48, USB |
| F070RB | STM32F070RB | 128 KB | 16 KB | 2 KB | LQFP64, USB |

Build output is in `build/<mcu>/` with the name in lower case (`build/f030f4/`).

ST's `STM32F0x0.svd` (v1.2), used by the PC tool, lists a PVD interrupt at IRQ 1;
F030/F070 have none (RM0360), and the startup file correctly leaves that vector reserved.


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

Sizes from the STM32F103 datasheets; erase page and vector table per RM0008. Each node
in the YAML also carries its density's `MDT_VECTORS_LD/MD/HD/XL` (the vector table length,
read by the startup file) and, on XL, `FLASH_XL_DENSITY` (the second flash bank, read by the
HAL). Parts of one density share these values.

| Density | MCU | Flash | RAM | Page size | Vectors | Notes |
|---|---|---|---|---|---|---|
| x4 | F103C4, F103R4, F103T4 | 16 KB | 6 KB | 1 KB | 59 | Low |
| x6 | F103C6, F103R6, F103T6 | 32 KB | 10 KB | 1 KB | 59 | Low |
| x8 | F103C8, F103R8, F103T8, F103V8 | 64 KB | 20 KB | 1 KB | 59 | Medium (Blue Pill: F103C8) |
| xB | F103CB, F103RB, F103TB, F103VB | 128 KB | 20 KB | 1 KB | 59 | Medium |
| xC | F103RC, F103VC, F103ZC | 256 KB | 48 KB | 2 KB | 76 | High |
| xD | F103RD, F103VD, F103ZD | 384 KB | 64 KB | 2 KB | 76 | High |
| xE | F103RE, F103VE, F103ZE | 512 KB | 64 KB | 2 KB | 76 | High |
| xF | F103RF, F103VF, F103ZF | 768 KB | 96 KB | 2 KB | 76 | XL, dual-bank |
| xG | F103RG, F103VG, F103ZG | 1024 KB | 96 KB | 2 KB | 76 | XL, dual-bank |

The package letter (C=LQFP48, R=LQFP64, T=VFQFPN36, V=LQFP100, Z=LQFP144) does not change
the build; pass the part as `MCU` (`make MCU=F103C8`).

ST's `STM32F103.svd` (v1.1), used by the PC tool, has no entry for IRQ 42; RM0008 and the
CMSIS headers put USB wake-up there (`USBWakeUp_IRQn = 42`), and so does the startup file.


### XL-density dual-bank (F103xF, F103xG)

F103xF (768 KB) and F103xG (1 MB) split their flash into two independent banks;
bank 1 is always the first 512 KB:

| Bank | Address range             | Control registers               |
|------|---------------------------|---------------------------------|
| 1    | 0x08000000 - 0x0807FFFF   | FLASH_CR, FLASH_SR, FLASH_AR    |
| 2    | 0x08080000 - end of flash | FLASH_CR2, FLASH_SR2, FLASH_AR2 |

The HAL picks the right register set automatically based on the address.
Any write or erase to an address `>= 0x08080000` uses the bank 2
registers. Both banks are unlocked independently using their own key
registers.

The xF and xG nodes set `FLASH_XL_DENSITY` (in `defines:`), which reaches the HAL through
`mdt_target.h`. All bank-2 code is compiled out on non-XL targets with
`#ifdef FLASH_XL_DENSITY`.


## Startup file and vector table

The startup file (vector table, reset handler) is linked into the program, not into the
library: the branch names it in `build.startup`. `build/<mcu>/` gets a copy of it,
`linker.ld` and the generated `memory.ld` (regions `flash` and `ram`), so a user project
can link the library with them. The startup file in your project is yours to edit.

The F0 vector table has 48 entries (16 core, 32 IRQ). The build places it at the start of
flash; its first word is the top of the part's RAM (for example `0x20001000` on F030F4,
`0x20008000` on F030CC).

On F103 the table size depends on the density: 59 vectors on low/medium density, 76 on
high and XL density. The startup file reads the length from the `MDT_VECTORS_*` define of
the part's node (it includes `mdt_target.h`, which ships next to it) and stops with a
compile error if none is set.

Do not remove `naked` from the reset handler (see `troubleshooting.md`).

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
firmware image. The PC tool reads the firmware-occupied range from the ELF
(its load segments in flash: code, read-only data and the `.data` initial values,
exactly what goes into the `.bin`) and checks it before every FLASH write and ERASE
command.

Page sizes:

* **1 KB pages**: F030x4/x6/x8, F070x6, F103x4/x6/x8/xB (low and medium
  density).
* **2 KB pages**: F030xC, F070xB, F103xC/D/E/F/G (high, XL, and
  connectivity density).

For ERASE the MCU computes the page base address from the given address
and `MDT_FLASH_PAGE_SIZE` (the node's `memory.flash.page`, in `mdt_target.h`). The
user can pass any address within the target page.


## Adding a part, a family or a core

**A part of an existing family** (for example another F030): add one node to the
branch with its sizes, and a row to the table above:

```yaml
  F030CC: {memory: {flash: {size: 256K, page: 2K}, ram: {size: 32K}}}
```

**A family on an existing core:** add `build_system/stm32/tree_branch_<family>.yaml`
with the HAL directory, startup file, `-mcpu`, linker script, the OpenOCD commands, the
SVD for the PC tool (`host.mcu_db`) and the nodes. `tree_branch_f0.yaml` is the example.

**A new core** (for example Cortex-M4 for STM32F4xx):

1. Create `hal/stm32/cortex-m4/` with:
   * `hal_stm.c` implementing all HAL functions (UART driver + memory access).
   * `uart.h` with peripheral register structs and bit masks for the target family.
   * `commands.h` with the FLASH register map, bit defines and key values; the page
     size is `MDT_FLASH_PAGE_SIZE` from `mdt_target.h`.
   * `startup_<device>.c` for the target.
   * `linker.ld` that includes `memory.ld` and places sections in `flash` and `ram`.
2. Add its branch YAML as above, and the SVD under `pc_tool/mcu_db/stm32/`.
3. `src/`, the Makefile, the generator and the PC tool are not modified.


## Application notes

1. **Do not use USART1** in your application code. It is owned by the
   MDT UART driver.
2. **SVD files for register validation** live in
   `pc_tool/mcu_db/stm32/`. The branch YAML names the one its parts use
   (`host.mcu_db`); memory sizes come from the build, not from the SVD.
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