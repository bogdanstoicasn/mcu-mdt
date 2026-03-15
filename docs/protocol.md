# MCU MDT Protocol Documentation



## Packet Format

Every packet is exactly **18 bytes**. All fields are always present.

| Offset | Size    | Field      | Description                              |
|--------|---------|------------|------------------------------------------|
| 0      | 1 byte  | START      | Always 0xAA                              |
| 1      | 1 byte  | CMD_ID     | Command identifier                       |
| 2      | 1 byte  | FLAGS      | Control and status flags                 |
| 3      | 1 byte  | SEQ        | Sequence number for multi-packet transfers |
| 4      | 1 byte  | MEM_ID     | Memory zone or breakpoint control value  |
| 5-8    | 4 bytes | ADDRESS    | Target address (little-endian)           |
| 9-10   | 2 bytes | LENGTH     | Data length in bytes (little-endian)     |
| 11-14  | 4 bytes | DATA       | Payload (max 4 bytes per packet)         |
| 15-16  | 2 bytes | CRC        | CRC16 over bytes 1..14 (little-endian)   |
| 17     | 1 byte  | END        | Always 0x55                              |


## Field Descriptions

- **START / END** — framing bytes, used for synchronization and as a second integrity check on
  top of CRC. If the receiver loses sync it discards bytes until 0xAA is seen again.

- **CMD_ID** — identifies the command. See commands reference for full list.

- **FLAGS** — bitmask controlling packet behavior. See Flags section below.

- **SEQ** — sequence number for transfers larger than 4 bytes. Increments per packet,
  wraps at 0xFF. Unused (0) for single-packet commands.

- **MEM_ID** — memory zone (RAM/FLASH/EEPROM) for memory commands, or breakpoint control
  value (ENABLE/DISABLE/RESET/NEXT) for breakpoint commands.

- **ADDRESS** — 4-byte little-endian target address. For breakpoint commands this field
  carries the breakpoint ID instead.

- **LENGTH** — number of bytes involved in the transfer. For commands with no data (PING,
  RESET) this is 0.

- **DATA** — up to 4 bytes of payload per packet. Larger transfers are split into multiple
  packets by the PC tool. On read commands the MCU writes the result into this field.

- **CRC** — CRC16 calculated over bytes 1 through 14 (CMD_ID to DATA inclusive, excluding
  START and END). Little-endian. Always present and always verified by the MCU.


## Flags

| Bit | Name            | Description                                      |
|-----|-----------------|--------------------------------------------------|
| 0   | MEM_ID_PRESENT  | MEM_ID field is valid for this command           |
| 1   | LENGTH_PRESENT  | LENGTH field is valid for this command           |
| 2   | ACK_NACK        | Set by MCU in response — packet is a reply       |
| 3   | SEQ_PRESENT     | SEQ field is valid, part of a multi-packet transfer |
| 4   | LAST_PACKET     | This is the last packet in a multi-packet sequence |
| 5   | STATUS_ERROR    | Set by MCU in response — command failed          |
| 6   | EVENT           | Unsolicited event from MCU, no response expected |


## Serialization

- Fields are concatenated in offset order as shown in the table above.
- Multi-byte fields (ADDRESS, LENGTH, CRC) are little-endian.
- CRC is computed over bytes 1..14 after all other fields are filled in.
- START and END bytes are not included in CRC calculation.


## Deserialization

- START byte (0xAA) at offset 0 is used for frame synchronization.
- END byte (0x55) at offset 17 is verified after the full 18 bytes are received.
- CRC is recomputed over bytes 1..14 and compared against the received CRC at offset 15-16.
- If START, END, or CRC check fails the packet is discarded and a FAILED_PACKET event
  is sent to the PC.
- Flag bits are inspected to determine the meaning of MEM_ID, SEQ, and LENGTH fields.


## Multi-Packet Transfers

Transfers larger than 4 bytes are split by the PC tool into multiple 4-byte chunks:

- Each chunk is sent as a separate packet with SEQ incrementing from 0.
- SEQ_PRESENT flag is set on all packets in the sequence.
- LAST_PACKET flag is set on the final packet.
- The MCU processes each packet independently and responds to each one.
- The PC tool reassembles the responses in order.


## Event Packets

The MCU can send unsolicited event packets to the PC at any time:

- EVENT flag (bit 6) is set.
- CMD_ID is 0 (not a command response).
- DATA carries the event type in the high byte and event data in the lower 3 bytes.
- No response is expected from the PC.

| Event Type | Value | Description                                      |
|------------|-------|--------------------------------------------------|
| NONE       | 0     | No event                                         |
| BUFFER_OVERFLOW | 1 | Receive buffer fence corrupted               |
| FAILED_PACKET | 2  | Packet failed CRC or framing validation          |
| BREAKPOINT_HIT | 3 | Breakpoint was triggered, MCU is now paused    |


## CRC Algorithm

CRC16, initial value 0xFFFF, no final XOR. Same algorithm used on both MCU (C) and PC (Python).
```c
uint16_t mdt_crc16(const uint8_t *data, uint16_t len) {
    uint16_t crc = 0xFFFF;
    uint8_t x;
    while (len--) {
        x = crc >> 8 ^ *data++;
        x ^= x >> 4;
        crc = (crc << 8) ^ ((uint16_t)(x << 12))
                         ^ ((uint16_t)(x << 5))
                         ^ ((uint16_t)x);
    }
    return crc;
}
```