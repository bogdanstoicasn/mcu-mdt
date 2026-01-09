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

