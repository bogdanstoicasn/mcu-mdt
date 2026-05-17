# Testing

## Overview

The test suite is split into three layers: unit, integration, and hardware.
Unit and integration tests run anywhere with no hardware attached. Hardware
tests need a real MCU flashed with the MDT firmware and a serial port.

**248 tests total.** 195 of them always run; the 53 hardware tests skip
cleanly when `MCU` is not set.


## How to run the tests

The runner is custom (`test/pymdtest.py`), not pytest. It picks up any file
matching `test_*.py`, runs every function whose name starts with `test_`,
and expands `@parametrize` cases. Assertions come from
`test/common/asserts.py`.

```bash
python3 -m test.pymdtest              # everything (hardware tests skip if MCU unset)
python3 -m test.pymdtest unit         # unit only
python3 -m test.pymdtest integration  # integration only
python3 -m test.pymdtest hardware     # hardware only (requires MCU)
```

Do not use `pytest` directly. The `@parametrize` decorator is custom and
not compatible with pytest.


## How the runner keeps tests quiet

Before each test the runner calls `_silence_logger()`, which sets the MCU-MDT
logger level to `CRITICAL` and flips `Terminal.set_quiet(True)`. After the
test it restores both. The reason both are needed:

* The logger is file-only by design (no `StreamHandler`). It only attaches a
  file handler if `enable_file_logging()` has been called, which no test
  does, so tests never produce log files.
* The `Terminal` is the other path to stdout (auto-routed warnings/errors
  plus direct `Terminal.packet`/`event`/`info` calls). Setting the logger
  level mutes the auto-routed path; `set_quiet(True)` mutes the direct
  path.

Together these guarantee zero stdout pollution from production code during
test runs. See `docs/architecture.md` for the full presentation-layer
design.


## Unit tests (`test/unit/`), 151 cases

No serial port, no MCU, no external dependencies.

### `test_crc.py` (7 cases)

CRC-CCITT (`0x1021`) validated against `binascii.crc_hqx`. Covers the
standard `123456789 -> 0x29B1` vector, empty input, and a batch of random
inputs at varying lengths. A wrong CRC would break the protocol silently,
so this suite runs first.

### `test_protocol.py` (33 cases)

Packet construction and parsing end to end: serialization, deserialization,
round-trips, the 18-byte size invariant, CRC integrity, multi-packet flags
(`SEQ_PRESENT`, `LAST_PACKET`), NACK detection, and little-endian address
encoding/decoding. Parameterized across several command shapes and
addresses.

### `test_parser.py` (42 cases)

The CLI parser layer: converts strings like
`WATCHPOINT 0 ENABLED 0x20000100` into `Command` objects. Covers all
command types, memory-type mapping, control-value mapping, hex data
decoding, and rejection of invalid input. Parameterized across all control
values for both breakpoints and watchpoints.

Register name resolution is exercised here too, covering the two-stage
lookup for `READ_REG` and `WRITE_REG`. The qualified `PERIPHERAL_REGISTER`
form (`USART1_SR`, `USART1_DR`, `USART1_BRR`) resolves to the correct
absolute address. The bare-name fallback (`SR`) works on both platforms.
Case-insensitive. Unknown peripheral returns `None` cleanly. AVR bare-name
lookups (`UDR0`, `UCSR0A`, `TWBR`, `TWDR`, `UBRR0`) resolve to the correct
I/O addresses with no underscore interference. `WRITE_REG` by qualified
name also works.

### `test_validator.py` (69 cases)

Validation against MCU metadata before a command hits the wire: memory
boundary checks (RAM, Flash, EEPROM), register access permissions
(read-only, write-only, read-write), breakpoint and watchpoint slot range
validation, and dispatch routing. Parameterized across valid and invalid
slot IDs.

Firmware protection has dedicated cases: FLASH write inside firmware is
rejected (start, mid, end-minus-one); write at `firmware_end_address` is
accepted; write spanning the boundary is rejected; no firmware info in
metadata allows write (the AVR path); ERASE of a page overlapping firmware
is rejected (page 0, mid-firmware, last firmware page); ERASE of the first
free page is accepted; ERASE well above firmware is accepted.

Watchpoint alignment is also tested. The validator only *warns* about
unaligned watch addresses; the command is still accepted because the MCU
reads 4 bytes byte-by-byte and is safe at any address. The test
`test_watchpoint_enabled_unaligned_address_accepted_with_warning` codifies
this behaviour explicitly. (The test was previously named
`..._rejected`, which was wrong: the validator does not reject, it only
warns. The name was fixed during the polish pass before freezing.)


## Integration tests (`test/integration/`), 44 cases

End-to-end pipeline through `MockUART`, an in-memory loopback, with no real
serial port. The flow under test is the full
parse -> validate -> serialize -> transmit -> receive -> deserialize path
for every command type, plus multi-packet chunking, event packet structure,
and error handling.

* **End-to-end commands.** PING, READ_MEM, WRITE_MEM, READ_REG, WRITE_REG,
  BREAKPOINT, WATCHPOINT, plus packet validation after loopback. Each runs
  the full pipeline and checks the deserialized response.
* **Chunked transfers.** A 16-byte write splits into four 4-byte packets;
  all are ACKed, a single-chunk write is marked `LAST_PACKET`, and
  addresses increment correctly across chunks.
* **Validation gating.** Out-of-range read, invalid breakpoint ID, write to
  a non-existent register: all rejected before anything hits the wire.
  Valid commands pass through cleanly.
* **MCU response handling.** ACK recognized as valid; NACK recognized
  correctly; corrupted response fails `validate_command_packet`; truncated
  response fails; wrong start byte fails.
* **Pipeline invariants.** Exactly one packet written to UART per command.
* **Event packets.** `EVENT_PACKET` flag set, event not mistaken for NACK,
  breakpoint slot ID carried in `SEQ`, event type in `DATA`, CRC valid.
  `BUFFER_OVERFLOW` recognized from the `EventType` enum.
* **Field fidelity.** Parameterized address/mem/length triples, data
  patterns, and sequence numbers: round-trip through
  serialize -> deserialize and confirm each field is preserved exactly.


## Hardware tests (`test/hardware/`), 53 cases

These need a real MCU with MDT firmware. Every test skips with `[SKIP]` if
`MCU` is not set.

```bash
MCU=F030F4 python3 -m test.pymdtest hardware
```

Environment variables are usually taken from the `build_info.yaml` for the
target firmware but can be overridden to test different configurations.
They are loaded once at module import time into `HW = HWConfig.from_env()`.

* **Link health.** Ping round-trip, 18-byte response invariant, START/END
  framing, CRC validity, CMD_ID echo, ACK flag set, STATUS_ERROR clear. If
  any of these fail the rest of the suite is meaningless.
* **Memory read.** SRAM read ACK, 4-byte data field, MEM_ID echo, Flash
  read structural validity. Flash does not assert ACK because some variants
  reject address 0; only structural validity is checked.
* **Memory write/readback.** Write ACK, then write-and-read-back of
  `0xCAFEBABE`, all-zeros, all-ones, adjacent word non-aliasing, plus four
  parameterized patterns (`0xDEADBEEF`, `0x01020304`, `0xAA55AA55`,
  `0x00FF00FF`).
* **Register access.** `READ_REG` at a known SRAM address returns a
  structurally valid packet. `WRITE_REG` + `READ_REG` round-trip verifies
  the first byte reads back correctly.
* **Protocol robustness.** Bad CRC triggers NACK, NACK has a valid CRC,
  recovery (next PING still ACKs), resync after a truncated send, NACK
  echoes the SEQ byte of the bad request, unknown CMD_ID `0xFF` sets
  STATUS_ERROR.
* **Breakpoints.** Control values parameterized across slots (ENABLED and
  DISABLED on slots 0..3, RESET on slot 0, NEXT on slot 1) all ACK.
  Invalid slot 99 NACKs. Enable-then-disable sequence both ACK. RESET
  standalone ACKs.
* **Watchpoints.** DISABLE ACKed for all 4 slots (parameterized). ENABLE
  on aligned SRAM address ACKed, disabled immediately after. RESET ACKed.
  MASK on active slot ACKed. MASK on inactive slot NACKed. Invalid slot
  NACKed.
* **Event packets.** A bad-CRC packet produces a NACK and then a
  FAILED_PACKET event with the EVENT flag set and `cmd_id == 0`. All
  received packets pass structural validation. The `rx_worker` routing
  test starts the background thread, sends a bad packet, and confirms the
  NACK lands in `response_queue` while the event (if emitted) lands in
  `event_queue`.
* **Chunked transfers.** `execute_command()` splits a 16-byte write into
  four 4-byte packets, all ACKed. An 8-byte chunked write followed by a
  single-word readback verifies the payload landed in SRAM correctly.
* **Stress.** 20 consecutive PINGs all ACKed (catches state-machine
  corruption under load). 10 interleaved write/read pairs with distinct
  patterns at the same address, each verified (catches buffer aliasing and
  ring-buffer issues under rapid I/O).


## What is not tested yet

Unit / integration:

* `event.py` threading. The routing logic of `rx_worker`,
  `event_poll_worker`, and `event_listener` has no isolated unit coverage.
  A `FakeSerialLink` that replays injected byte sequences would cover this
  without hardware.
* `commander.py`. Retry logic, timeout handling, and multi-packet assembly
  are only exercised indirectly through hardware tests.
* `loader.py`. `build_info.yaml` parsing is untested. A missing key
  produces a `KeyError` at runtime instead of a clear error.
* The Terminal presentation layer (`pc_tool/common/terminal.py`). Visual
  output is validated manually via a scratch demo, not by the automated
  suite. The audit-trail mirror to the file logger is verified informally.
  A dedicated test (capture stdout and the log file, assert on both)
  would close this gap.

Hardware:

* The `RESET` command is implemented but has no hardware test. A real test
  would verify the MCU responds to PING within a bounded time after
  reset.
* AVR vs STM32 parity. Tests run one platform at a time. There is no
  automated cross-target comparison.
* Disconnect recovery. The `EIO` clean-shutdown path in `rx_worker` is
  implemented but not tested.
* Breakpoint hold and release on hardware. The spin loop is exercised
  implicitly via the ENABLED/DISABLED test pair, but no test explicitly
  triggers `MDT_BREAKPOINT(id)` from application code and checks that the
  event arrives.


## Future work

Short term: a `FakeSerialLink` fixture to unit-test `rx_worker` routing
without hardware; a hardware test for `RESET`; `loader.py` unit tests with
valid and malformed `build_info.yaml`; a Terminal-output capture test.

Long term: Renode-based firmware tests using the existing `stm32f030.resc`
script; property-based round-trip testing for the serializer/deserializer.