# STM32 Platform

## Overview

The STM32 HAL supports two Cortex cores:

- **Cortex-M0** — STM32F030xx and STM32F070xx families
- **Cortex-M3** — STM32F103xx family

The build system selects the correct core automatically based on the `MCU` value passed at build
time. Flash and RAM sizes are resolved by preprocessing the linker script with `#ifdef` guards —
no separate linker script per MCU variant is needed.


## Building

```bash
make PLATFORM=stm32 MCU=<mcu> PORT=<port>
```

Cortex-M0 example:
```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0
```

Cortex-M3 example:
```bash
make PLATFORM=stm32 MCU=F103C8 PORT=/dev/ttyUSB0
```

Optional — override CPU frequency:
```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0 F_CPU=48000000UL
make PLATFORM=stm32 MCU=F103C8 PORT=/dev/ttyUSB0 F_CPU=72000000UL
```

Build output is placed in `build/<MCU>/`:
```
build/F030F4/
├── libmcu_mdt_stm32.a         # static library to link against
├── mcu_mdt.h                  # public header
├── mcu_mdt_config.h           # configuration header
├── mcu_mdt_hal.h              # HAL contract header
├── ring_buffer.h              # ring buffer (needed by HAL)
├── mcu_mdt_example.elf        # example binary
├── mcu_mdt_example.bin        # ready to flash with st-flash
├── mcu_mdt_example.hex        # ready to flash with other tools
├── Makefile.example           # user Makefile for custom projects
├── linker.ld                  # linker script (needed for user builds)
├── startup_stm32f030xx.c      # startup file
├── main.c                     # example main
└── build_info.yaml            # platform/mcu/port metadata
```


## Flashing

```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0 flash
```

Uses `st-flash` to write the binary to flash at `0x08000000`.
Requires [stlink tools](https://github.com/stlink-org/stlink) installed.

> **Note:** `st-flash` performs a mass erase before writing. All existing flash content is erased.


## Using the Library in Your Own Project

After building, go to `build/<MCU>/` and rename `Makefile.example` to `Makefile`.
Drop your `.c` files alongside `main.c` and run:
```bash
make MCU=F030F4 PORT=/dev/ttyUSB0
```

All `.c` files in the directory are picked up automatically. The library, headers,
linker script, and startup file are all self-contained in the build directory.

Minimal `main.c` — poll mode:
```c
#include "mcu_mdt.h"

int main(void) {
    mcu_mdt_init();

    while (1) {
        mcu_mdt_poll();

        // your application code here
        MDT_BREAKPOINT(0); // optional breakpoint
    }
}
```

Minimal `main.c` — interrupt mode (IDLE callback handles RX, SysTick samples watchpoints):
```c
#include "mcu_mdt.h"

void SysTick_Handler(void) {
    mcu_mdt_watchpoint_check();
}

int main(void) {
    mcu_mdt_init(); // registers IDLE callback automatically

    while (1) {
        // mcu_mdt_poll(); // still needed to flush events

        // your application code here
    }
}
```


## Cleaning

```bash
make PLATFORM=stm32 MCU=F030F4 clean   # removes build/F030F4/
make wipe                               # removes entire build/ directory
```


## Supported MCUs

### Cortex-M0 (STM32F030xx / STM32F070xx)

Reference manual: RM0360

UART: USART1 on PA9 (TX) / PA10 (RX), AF1. Ring-buffer driven with RXNE, TXE, and IDLE interrupts.
IDLE interrupt triggers PendSV (lowest priority) for packet processing.
Clock assumes 8 MHz HSI by default — pass `F_CPU` if running at a different frequency.
FLASH write supported via half-word (16-bit) programming only (Cortex-M0 hard-faults on other widths).

| MCU    | Part Numbers       | Flash  | RAM   | Notes                      |
|--------|--------------------|--------|-------|----------------------------|
| F030F4 | STM32F030F4P6      | 16 KB  | 4 KB  | Primary development target |
| F030F6 | STM32F030F6P6      | 32 KB  | 4 KB  |                            |
| F030F8 | STM32F030F8P6      | 64 KB  | 8 KB  |                            |
| F030C6 | STM32F030C6T6      | 32 KB  | 4 KB  | LQFP48                     |
| F030C8 | STM32F030C8T6      | 64 KB  | 8 KB  | LQFP48                     |
| F030CC | STM32F030CCT6      | 256 KB | 32 KB | LQFP48, largest F030       |
| F070F6 | STM32F070F6P6      | 32 KB  | 6 KB  | USB device support         |
| F070CB | STM32F070CBT6      | 128 KB | 16 KB | USB device support         |
| F070RB | STM32F070RBT6      | 128 KB | 16 KB | LQFP64, USB device support |

### Cortex-M3 (STM32F103xx)

Reference manual: RM0008

UART: USART1 on PA9 (TX) / PA10 (RX), configured via CRH register (F1 GPIO style).
Ring-buffer driven with RXNE, TXE, and IDLE interrupts. IDLE flag cleared by SR→DR read sequence
(required on F1 series). FLASH write is not implemented on M3.

| MCU density | Example parts                       | Flash       | RAM         |
|-------------|-------------------------------------|-------------|-------------|
| F103x4      | STM32F103C4, R4, T4                 | 16 KB       | 6 KB        |
| F103x6      | STM32F103C6, R6, T6                 | 32 KB       | 10 KB       |
| F103x8      | STM32F103C8, R8, T8, V8            | 64 KB       | 20 KB       |
| F103xB      | STM32F103CB, RB, TB, VB            | 128 KB      | 20 KB       |
| F103xC      | STM32F103RC, VC, ZC                | 256 KB      | 48 KB       |
| F103xD      | STM32F103RD, VD, ZD                | 384 KB      | 64 KB       |
| F103xE      | STM32F103RE, VE, ZE                | 512 KB      | 64 KB       |
| F103xF      | STM32F103RF, VF, ZF                | 768 KB      | 96 KB       |
| F103xG      | STM32F103RG, VG, ZG                | 1024 KB     | 96 KB       |

Any package variant (C=LQFP48, R=LQFP64, T=VFQFPN36, V=LQFP100, Z=LQFP144) at a given density
maps to the same linker script entry. Pass the density letter in the `MCU` argument:

```bash
make PLATFORM=stm32 MCU=F103C8 PORT=/dev/ttyUSB0   # LQFP48 64KB flash
make PLATFORM=stm32 MCU=F103RB PORT=/dev/ttyUSB0   # LQFP64 128KB flash
```


## Adding a New STM32 Core

To add support for a new Cortex core (e.g. Cortex-M4 for STM32F4xx):

1. Create `hal/stm32/cortex-m4/` with:
   - `hal_stm.c` — implements all 11 HAL functions directly (UART driver + memory access)
   - `uart.h` — peripheral register structs and bit masks for the target family
   - `Makefile` — copy from `cortex-m0/` and adjust `CPU_FLAGS` and MCU mapping
   - `startup_<device>.c` — startup file for the target
   - `linker.ld` — linker script with `#ifdef` guards for flash/RAM sizes
2. Add the MCU family mapping in `hal/stm32/Makefile` router.
3. `src/` is never modified.


## Processing Mode

STM32 supports two distinct modes for handling incoming UART packets. The mode is
selected at build time and written into `build_info.yaml` so the PC tool knows whether
to send periodic event poll packets.

### Interrupt mode (default)

```
MDT_USE_UART_IDLE=1   - default, set in the Makefile
```

The USART1 peripheral fires three interrupt sources:

- **RXNE** — a byte arrived, pushed into the RX ring buffer immediately
- **IDLE** — the RX line went quiet after a burst (i.e. a full packet just landed)
- **TXE** — TX register empty, next byte popped from TX ring buffer and sent

When the IDLE interrupt fires, PendSV is triggered at the lowest interrupt priority.
`PendSV_Handler` calls `mdt_process_pending()` which drains the RX ring buffer and
dispatches the packet. Your `main()` loop runs freely between PendSV invocations.

Because `mcu_mdt_poll()` is never called in this mode, the MCU cannot push events
autonomously. Instead the PC tool sends a CMD_ID=0 poll packet every 500 ms. The
MCU's `handle_reserved()` responds with any pending event payload, and the PC
`rx_worker` routes the response to the event queue.

**Minimal `main.c` — interrupt mode:**
```c
#include "mcu_mdt.h"

int main(void)
{
    mcu_mdt_init(); /* registers IDLE callback automatically */

    while (1)
    {
        /* application code runs freely — UART handled by ISR + PendSV */
    }
}
```

Use this mode when your application does not have a tight cooperative main loop —
for example if it uses `HAL_Delay()`, blocking I2C/SPI transactions, or any other
operation that stalls the loop for more than a few milliseconds.



### Poll mode

```
make PLATFORM=stm32 MCU=F030F4 PORT=... MDT_USE_UART_IDLE=0
```

RXNE and TXE interrupts still run (the ring buffers are always ISR-driven), but the
IDLE interrupt is not used. Your `main()` loop must call `mcu_mdt_poll()` regularly.
Each call flushes any pending event, drains the RX ring buffer, and checks watchpoints.

```
main loop
  └── mcu_mdt_poll()
        ├── 1. flush pending event if TX idle
        ├── 2. fence + overflow guard
        ├── 3. drain RX ring buffer → packet dispatch
        └── 4. mcu_mdt_watchpoint_check()
```

**Minimal `main.c` — poll mode:**
```c
#include "mcu_mdt.h"

int main(void)
{
    mcu_mdt_init();

    while (1)
    {
        mcu_mdt_poll();
        /* application code here */
    }
}
```

In poll mode the PC tool does **not** send CMD_ID=0 poll packets — `build_info.yaml`
will contain `uart_idle: 0` and the PC tool's `event_poll_worker` thread is not
started. Events are delivered automatically by `mcu_mdt_poll()` at step 1.

Use this mode when your main loop is tight and runs frequently (every few ms or less),
or when you want deterministic, application-controlled timing for packet processing.



### Which mode to choose

| Situation | Recommended mode |
|---|---|
| Application uses `HAL_Delay()` or blocking calls | Interrupt |
| Application has no main loop (RTOS task-based) | Interrupt |
| Tight cooperative main loop running continuously | Poll |
| You want deterministic packet timing | Poll |
| Default / unsure | Interrupt |

The choice has **no effect on the protocol** — packet format, CRC, commands, and
events are identical in both modes. The only difference is which side initiates
event delivery.


## Notes

1. Do not use USART1 in your application code — it is owned by the MDT UART driver.
2. The IDLE interrupt + PendSV path is enabled by default (`MDT_HAL_HAS_UART_IDLE=1` set in the
   Makefile). To disable and use pure poll mode, pass `-DMDT_USE_UART_IDLE=0` in your CFLAGS.
3. SVD files for register validation are in `pc_tool/mcu_db/stm32/`. Add an SVD + YAML config
   to support a new STM32 family in the PC tool validator.
