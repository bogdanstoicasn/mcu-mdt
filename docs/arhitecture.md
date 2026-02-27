# Architecture

## Purpose

This document describes the high-level architecture of the **MCU Debug Tool (MDT)** project. It explains the design goals, layering, module responsibilities, and data flow between the PC-side tool and the MCU-side firmware library.

The goal of this architecture is to provide a **portable, deterministic, and extensible UART-based memory debugger** that can be reused across multiple MCU families with minimal platform-specific code.

---

## Design Goals

- **Portability**: Core logic is platform-agnostic C; MCU-specific details are isolated in HAL layers.
- **Determinism**: No dynamic memory allocation, bounded buffers, predictable execution.
- **Minimal MCU Complexity**: MCU firmware performs only binary protocol handling and memory access.
- **PC-Side Intelligence**: Parsing, validation, YAML handling, and user interaction live entirely on the PC.
- **Single Entry Point**: MCU exposes a minimal public API with a single polling function.
- **Non-blocking Operation**: UART I/O is byte-oriented and cooperative.

---

## Core Principles

Portable C code with HAL abstraction

No MCU-side complexity

Deterministic behavior

## System Overview

The system consists of two main components:

```
+--------------------+        UART        +---------------------+
| PC Debug Tool      | <---------------> | MCU Firmware (MDT)  |
|                    |                   |                     |
| - CLI              |                   | - Protocol Engine   |
| - YAML Command DB  |                   | - Command Dispatch  |
| - Validation       |                   | - Memory Access     |
| - Serialization    |                   | - HAL Abstraction   |
+--------------------+                   +---------------------+
```

---

## PC-Side Architecture

### Responsibilities

The PC tool is responsible for:

- Parsing user input (CLI commands)
- Handling CLI-only commands (HELP, EXIT, CLEAR, HISTORY)
- Loading and interpreting `commands.yaml`
- Validating command parameters and memory ranges
- Serializing commands into binary packets
- UART communication with the target MCU

The MCU **never** parses text or YAML.

### Layering

```
CLI
 ├── CLI Commands (local-only)
 ├── Validator
 │    ├── Command schema validation
 │    ├── Memory range validation (ATDF-based)
 ├── Protocol Encoder/Decoder
 └── UART Transport
```

### Validation Model

- CLI-only commands are handled immediately and never sent over UART.
- Protocol commands follow a strict flow:

```
parse → validate → serialize → send
```

- Memory validation maps logical memory types (RAM / FLASH / EEPROM) to ATDF memory segments.
- FLASH writes are rejected by default unless explicitly enabled.


## Ideeas to put into the thesis:

Fencing is tightly coupled to the internal packet buffer structure and does not represent a reusable abstraction. Therefore it is implemented as a private core mechanism rather than a separate module.

The user calls mcu_mdt_poll() in the main loop to maintain deterministic execution. This design avoids hidden interrupts or background threads, which keeps the library portable across MCUs with minimal dependencies and predictable timing.

This debugger implements cooperative software breakpoints, where execution is voluntarily paused by instrumented firmware code. Unlike hardware breakpoints (e.g., ARM FPB or AVR OCD), this method is fully portable and requires no debug hardware support.

Breakpoints reside in static memory and rely on the C runtime zero-initialization of the .bss segment, ensuring deterministic disabled state at boot without requiring explicit initialization.

The MCU MDT debugger is cooperative: it relies on the function mcu_mdt_poll() being called frequently in the main loop to service software breakpoints and PC commands.

Both UART RX and TX are handled by ISRs, so mcu_mdt_poll() only processes completed packets (18 bytes each) and dispatches commands. This makes the poll function very fast, with negligible CPU overhead.

As a result, it is safe and recommended for users to call mcu_mdt_poll() in their main loop. Blocking functions such as delay() will temporarily pause debugger responsiveness, but overall this design keeps the ISR small, safe, and the system portable across different MCUs.