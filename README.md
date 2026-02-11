# mcu-mdt

A software only memory debugging tool

## Overview

**MCU-MDT** is a lightweight, portable UART-based debugger and memory inspection toolkit for microcontrollers.
It provides a non-intrusive, HAL-based debugging interface that can be integrated into bare-metal firmware with minimal application code.

The project is designed for low-resource MCUs and follows industry-standard embedded software architecture, focusing on portability, determinism, and clean separation between hardware and protocol logic.

## How to build

To build the MCU-MDT project, follow these steps:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/bogdanstoicasn/mcu-mdt.git
    cd mcu-mdt
    ```

2. **Make**:
    Use the provided Makefile to build the project:
    ```bash
    make PLATFORM=<platform_name> MCU=<mcu_name> PORT=<uart_port>
    ```

    Replace `<platform_name>`, `<mcu_name>`, and `<uart_port>` with the appropriate values for your target platform, microcontroller, and UART port.
    Example:
    ```bash
    make PLATFORM=stm32 MCU=stm32f103 PORT=/dev/ttyUSB0
    ```

3. **Flash the firmware**:
    ```bash
    make PLATFORM=stm32 MCU=stm32f103 PORT=/dev/ttyUSB0 flash
    ```

4. **Run the host application**:
    ```bash
    cd ./pc_tool
    python3 main.py <path_to_config.yaml>
    ```

## BEWARE

To keep the microcontroller lightweight and portable across low-resource devices, all semantic validation (address ranges, memory legality, command correctness) is performed on the PC side using ATDF/SVD metadata. The MCU firmware implements only protocol framing, CRC validation, and command execution.
