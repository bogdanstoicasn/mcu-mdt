# MCU MDT Protocol Documentation


## Packet Format

Every packet is exactly **18 bytes**. All fields are always present.

| Offset | Size    | Field      | Description                                        |
|--------|---------|------------|----------------------------------------------------|
| 0      | 1 byte  | START      | Always 0xAA                                        |
| 1      | 1 byte  | CMD_ID     | Command identifier                                 |
| 2      | 1 byte  | FLAGS      | Control and status flags                           |
| 3      | 1 byte  | SEQ        | Sequence number for multi-packet transfers         |
| 4      | 1 byte  | MEM_ID     | Memory zone, breakpoint/watchpoint control value   |
| 5-8    | 4 bytes | ADDRESS    | Target address (little-endian)                     |
| 9-10   | 2 bytes | LENGTH     | Data length in bytes (little-endian)               |
| 11-14  | 4 bytes | DATA       | Payload (max 4 bytes per packet)                   |
| 15-16  | 2 bytes | CRC        | CRC16 over bytes 1..14 (little-endian)             |
| 17     | 1 byte  | END        | Always 0x55                                        |


## Field Descriptions

- **START / END** — framing bytes, used for synchronization and as a second integrity check on
  top of CRC. If the receiver loses sync it discards bytes until 0xAA is seen again.

- **CMD_ID** — identifies the command. See commands reference for full list.

- **FLAGS** — bitmask controlling packet behavior. See Flags section below.

- **SEQ** — sequence number for transfers larger than 4 bytes. Increments per packet,
  wraps at 0xFF. Unused (0) for single-packet commands.

- **MEM_ID** — memory zone (RAM/FLASH/EEPROM) for memory commands, breakpoint control
  value (ENABLE/DISABLE/RESET/NEXT) for breakpoint commands, or watchpoint control value
  (ENABLE/DISABLE/RESET/MASK) for watchpoint commands.

- **ADDRESS** — 4-byte little-endian target address. For breakpoint and watchpoint commands
  this field carries the slot ID instead.

- **LENGTH** — number of bytes involved in the transfer. Zero for commands with no data
  (PING, RESET).

- **DATA** — up to 4 bytes of payload per packet. On read commands the MCU writes the result
  here. On watchpoint ENABLE, this carries the address to watch (little-endian). On watchpoint
  MASK, this carries the 32-bit mask value.

- **CRC** — CRC16 calculated over bytes 1 through 14 (CMD_ID to DATA inclusive, excluding
  START and END). Little-endian. Always present, always verified by the MCU.


## Flags

| Bit | Name            | Description                                           |
|-----|-----------------|-------------------------------------------------------|
| 0   | MEM_ID_PRESENT  | MEM_ID field is valid for this command                |
| 1   | LENGTH_PRESENT  | LENGTH field is valid for this command                |
| 2   | ACK_NACK        | Set by MCU in response — packet is a reply            |
| 3   | SEQ_PRESENT     | SEQ field is valid, part of a multi-packet transfer   |
| 4   | LAST_PACKET     | This is the last packet in a multi-packet sequence    |
| 5   | STATUS_ERROR    | Set by MCU in response — command failed               |
| 6   | EVENT           | Unsolicited event from MCU, no response expected      |


## Serialization

- Fields are concatenated in offset order as shown in the table above.
- Multi-byte fields (ADDRESS, LENGTH, DATA, CRC) are little-endian.
- CRC is computed over bytes 1..14 after all other fields are filled in.
- START and END bytes are not included in CRC calculation.


## Deserialization

- START byte (0xAA) at offset 0 is used for frame synchronization.
- END byte (0x55) at offset 17 is verified after the full 18 bytes are received.
- CRC is recomputed over bytes 1..14 and compared against the received CRC at offset 15-16.
- If START, END, or CRC check fails the packet is discarded, a NACK is sent back, and a
  FAILED_PACKET event is queued for the next poll cycle.
- Flag bits are inspected to determine the meaning of MEM_ID, SEQ, and LENGTH fields.


## NACK Packets

When the MCU receives a packet that fails CRC or framing validation it sends a NACK response:

- `ACK_NACK` (bit 2) and `STATUS_ERROR` (bit 5) flags are both set.
- `CMD_ID` echoes the `CMD_ID` from the failed packet.
- `SEQ` echoes the `SEQ` from the failed packet.
- All other fields are zero.
- A valid CRC is computed and included.

> **Note:** The PC-side `is_nack_packet()` currently also requires `cmd_id == 0`, which conflicts
> with the firmware echoing the original `cmd_id`. This mismatch is a known issue — see
> architecture doc Known Issues section.


## Multi-Packet Transfers

Transfers larger than 4 bytes are split by the PC tool into multiple 4-byte chunks:

- Each chunk is sent as a separate packet with SEQ incrementing from 0.
- `SEQ_PRESENT` flag is set on all packets in the sequence.
- `LAST_PACKET` flag is set on the final packet.
- The MCU processes each packet independently and responds to each one.
- The PC tool collects responses in order via the `rx_worker` thread.


## Event Packets

The MCU can send unsolicited event packets to the PC at any time:

- `EVENT` flag (bit 6) is set.
- `CMD_ID` is 0.
- `SEQ` carries the event source ID (breakpoint slot, watchpoint slot, or 0 for system events).
- `MEM_ID` carries the event type (see table below).
- `ADDRESS` carries context data (e.g. old value for watchpoints, buffer address for overflow).
- `DATA` carries the new value or additional debug info.
- No response is expected from the PC.
- The PC `rx_worker` routes event packets to a separate event queue.

| Event Type      | Value | MEM_ID | SEQ         | ADDRESS           | DATA              |
|-----------------|-------|--------|-------------|-------------------|-------------------|
| NONE            | 0     | —      | —           | —                 | —                 |
| BUFFER_OVERFLOW | 1     | 1      | 0           | buffer address    | overflow index    |
| FAILED_PACKET   | 2     | 2      | 0           | buffer address    | 0                 |
| BREAKPOINT_HIT  | 3     | 3      | breakpoint id | 0               | hit count         |
| WATCHPOINT_HIT  | 4     | 4      | watchpoint id | old value       | new value         |


## CRC Algorithm

CRC16, initial value 0xFFFF, no final XOR. Same algorithm used on both MCU (C) and PC (Python).

```c
uint16_t mdt_crc16(const uint8_t *data, uint16_t len) {
    uint16_t crc = 0xFFFF;
    while (len--) {
        uint8_t x = (uint8_t)(crc >> 8) ^ *data++;
        x ^= (x >> 4);
        crc = (crc << 8) ^ ((uint16_t)(x << 12))
                         ^ ((uint16_t)(x << 5))
                         ^ ((uint16_t)x);
    }
    return crc;
}
```
