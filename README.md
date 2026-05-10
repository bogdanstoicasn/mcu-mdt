# mcu-mdt

A software-only memory debugging tool for microcontrollers, built over UART.

## Overview

**MCU-MDT** is a lightweight, portable UART-based debugger and memory inspection toolkit for
microcontrollers. It provides a non-intrusive, HAL-based debugging interface that can be
integrated into bare-metal firmware with minimal application code.

The project targets hobbyists and students who want embedded debugging capabilities without
a JTAG/SWD probe. UART is available on virtually every MCU — even on boards without an
exposed debug header or with the SWD pins unavailable.

**Supported platforms:**
- **AVR** — ATmega family (80+ MCUs via ATDF database)
- **STM32 Cortex-M0** — STM32F030xx, STM32F070xx
- **STM32 Cortex-M3** — STM32F103xx (all densities, including XL dual-bank)

**Capabilities:**
- Read and write SRAM at any address
- Read and write flash (STM32, with page erase support)
- Read and write memory-mapped peripheral registers by address or by name (`RCC_CR`, `USART1_SR`)
- Software breakpoints (`MDT_BREAKPOINT(id)`) — MCU pauses and stays responsive
- Memory watchpoints with bit masking — fires an event when watched bits change
- EEPROM read/write (AVR)
- Firmware self-protection — PC validator rejects any command that would overwrite the running firmware

**What you need:**
- A USB-UART adapter (€2–5) connected to the MCU's TX/RX pins
- Python 3.10+ on the PC
- The AVR or ARM GCC toolchain for firmware builds

## Getting Started

1. **Clone the repository**

```bash
git clone https://github.com/bogdanstoicasn/mcu-mdt.git
cd mcu-mdt
```

2. **Build the firmware**

Platform-specific build instructions are in `docs/<platform>/info.md`.

```bash
# AVR
make PLATFORM=avr MCU=atmega328p PORT=/dev/ttyACM0

# STM32 Cortex-M0
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0

# STM32 Cortex-M3
make PLATFORM=stm32 MCU=F103C8 PORT=/dev/ttyUSB0
```

3. **Flash the firmware**

```bash
make PLATFORM=avr   MCU=atmega328p PORT=/dev/ttyACM0 flash  # avrdude
make PLATFORM=stm32 MCU=F030F4     PORT=/dev/ttyUSB0 flash  # st-flash
```

4. **Run the host tool**

```bash
python3 mcu_mdt.py build/<MCU>/build_info.yaml
```

5. **Start debugging**

```
PING
READ_MEM  RAM   0x20000000 4
WRITE_MEM RAM   0x20000004 4 DEADBEEF
READ_REG  RCC_CR
WRITE_MEM ERASE 0x08004000 4 00000000
WRITE_MEM FLASH 0x08004000 4 CAFEBABE
BREAKPOINT 0 ENABLED
WATCHPOINT 0 ENABLED 0x20000008
```


## Architecture Note

To keep the firmware lightweight and portable across low-resource microcontrollers, **MCU-MDT**
performs all semantic validation on the PC side.

This includes:

- Address range validation against SVD (STM32) or ATDF (AVR) device databases
- Memory legality checks (is this address in RAM/Flash/EEPROM for this MCU?)
- Firmware protection (reject any flash write or erase that touches the running firmware)
- Command parameter validation
- Register name resolution (`PERIPHERAL_REGISTER` format)

The MCU firmware implements only:

- Protocol framing, parsing, and CRC validation
- Command execution and memory access

This design allows the firmware to remain minimal, deterministic, and portable, while
the PC side handles all complex validation and tooling.


## Documentation

| Document | Description |
|---|---|
| `docs/architecture.md` | System design, HAL contract, protocol rationale, memory safety |
| `docs/protocol.md` | Packet format, field descriptions, CRC algorithm, event packets |
| `docs/commands.md` | All commands with parameters, behavior, and platform availability |
| `docs/avr/info.md` | AVR build, flash, ATDF support, supported MCU list |
| `docs/stm32/info.md` | STM32 build, flash, interrupt vs poll mode, XL-density, flash write |
| `docs/testing.md` | Test suite structure, how to run, what is and isn't covered |
| `docs/troubleshooting.md` | Common problems and development notes |


## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.