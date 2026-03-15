# STM32 Platform

## Overview

The STM32 HAL currently supports Cortex-M0 based devices from the STM32F030x4/x6/x8/xC and STM32F070x6/xB family.
The core, peripheral registers, and UART driver are identical across all supported parts.
Only Flash and RAM sizes differ, which is handled automatically by the linker script
based on the `MCU` variable passed at build time.


## Building
```bash
make PLATFORM=stm32 MCU=<mcu> PORT=<port>
```

Example:
```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0
```

Optional — override CPU frequency (default is 48MHz):
```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0 F_CPU=48000000UL
```

Build output is placed in `build/<MCU>/`:
```
build/F030F4/
├── libmcu_mdt_stm32.a     # static library to link against
├── mcu_mdt.h              # public header
├── mcu_mdt_config.h       # configuration header
├── mcu_mdt_example.elf    # example binary
├── mcu_mdt_example.bin    # ready to flash with st-flash
├── mcu_mdt_example.hex    # ready to flash with other tools
├── Makefile.example       # user Makefile for custom projects
├── linker.ld              # linker script (needed for user builds)
├── main.c                 # example main
└── build_info.yaml        # platform/mcu/port metadata
```


## Flashing
```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0 flash
```

Uses `st-flash` to write the binary to flash starting at `0x08000000`.
Requires [stlink tools](https://github.com/stlink-org/stlink) installed.


## Using the Library in Your Own Project

After building, go to `build/<MCU>/` and rename `Makefile.example` to `Makefile`.
Drop your `.c` files alongside `main.c` and run:
```bash
make MCU=F030F4 PORT=/dev/ttyUSB0
```

All `.c` files in the directory are picked up automatically. The library, headers,
linker script, and example are all self-contained in the build directory. No need
to touch the MDT source tree.

Minimal `main.c`:
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


## Cleaning
```bash
make PLATFORM=stm32 MCU=F030F4 clean   # removes build/F030F4/
make wipe                               # removes entire build/ directory
```


## Supported MCUs

### Cortex-M0 (STM32F030xx / STM32F070xx)

Reference manual: RM0360

UART driver uses USART1 on PA9 (TX) and PA10 (RX) with AF1.
Clock assumes 48 MHz PCLK2 — adjust `F_CPU` if running at a different frequency.

| MCU      | Part Numbers                  | Flash  | RAM   | Notes                      |
|----------|-------------------------------|--------|-------|----------------------------|
| F030F4   | STM32F030F4P6                 | 16 KB  | 4 KB  | Primary development target |
| F030F6   | STM32F030F6P6                 | 32 KB  | 4 KB  |                            |
| F030F8   | STM32F030F8P6                 | 64 KB  | 8 KB  |                            |
| F030C6   | STM32F030C6T6                 | 32 KB  | 4 KB  | LQFP48, more pins          |
| F030C8   | STM32F030C8T6                 | 64 KB  | 8 KB  | LQFP48, more pins          |
| F030CC   | STM32F030CCT6                 | 256 KB | 32 KB | LQFP48, largest F030       |
| F070F6   | STM32F070F6P6                 | 32 KB  | 6 KB  | USB device support         |
| F070CB   | STM32F070CBT6                 | 128 KB | 16 KB | USB device support         |
| F070RB   | STM32F070RBT6                 | 128 KB | 16 KB | LQFP64, USB device support |

All parts in this table share the same core, peripheral register map, and startup file.
The linker script selects Flash and RAM sizes automatically based on the `MCU` value.

## Adding a New STM32 Core

To add support for a new Cortex core (e.g. Cortex-M4 for STM32F4xx):

1. Create `hal/stm32/cortex-m4/` with:
   - `Makefile` — copy from `cortex-m0/` and adjust `CPU_FLAGS`
   - `uart.c` / `uart.h` — UART driver for the target family
   - `hal_stm.c` — HAL implementation
   - `commands.c` / `commands.h` — memory read/write implementation
   - `startup_<device>.c` — startup file for the target
   - `linker.ld` — linker script for the target
2. Add the MCU family mapping in `hal/stm32/Makefile` router.
3. Zero changes to `src/`.
