# mcu-mdt

A software-only memory debugging tool for microcontrollers.

## Overview

**MCU-MDT** is a lightweight, portable UART-based debugger and memory inspection toolkit for microcontrollers.  
It provides a non-intrusive, HAL-based debugging interface that can be integrated into bare-metal firmware with minimal application code.

The project is designed for low-resource MCUs and follows industry-standard embedded software architecture, focusing on portability, determinism, and clean separation between hardware and protocol logic.

## Getting Started

1. **Clone the repository**

```bash
git clone https://github.com/bogdanstoicasn/mcu-mdt.git
cd mcu-mdt
```

2. **Build the firmware**

Firmware instructions are platform-specific. Refer to the documentation for your target platform, which is located in `docs/<PLATFORM>/info.md`.

Each document contains detailed build instructions and supported devices.

3. **Run the host tool**

The host debugger runs on the PC and communicates with the MCU over UART. It is
written in Python.

```bash
python3 mcu_mdt.py </build/<mcu_name>/build_info.yaml>
```

## Architecture Note

To keep the firmware lightweight and portable across low-resource microcontrollers, **MCU-MDT**
performs all semantic validation on the PC-side

This includes:

- address range validation
- memory legality checks
- command correctness
- device metadata parsing(ATDF / SVD)

The MCU firmware implements only:

- protocol framing, parsing, validation(e.g. CRC)
- command execution

This design allows the firmware to be as minimal, simple and deterministic as possible, while allowing complex validation and tooling on the host side.

## License

This project is licensed under the MIT License: see the [LICENSE](LICENSE) file for details.