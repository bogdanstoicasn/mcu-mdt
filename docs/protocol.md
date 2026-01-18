# MCU MDT Protocol Documentation

Packet Format:

    - start_byte: Constant value 0xAA indicating the start of the packet.
    - cmd_id: Command identifier (1 byte).
    - flags: Command flags (1 byte).
    - mem_id: Optional memory identifier (1 byte), present if the command requires it.
    - address: Target address (4 bytes, little-endian).
    - length: Always present( 2 bytes, little-endian).
    - data: Always present (4 bytes max).
    - crc: Checksum (2 bytes), calculated over the entire packet except the start and end bytes.
    - end_byte: Constant value 0x55 indicating the end of the packet.

Fields:
- Start Byte: Constant value 0xAA indicating the start of the packet.
- Cmd ID: Command identifier (1 byte).
- Flags: Command flags (1 byte).
- Mem ID: Optional memory identifier (1 byte), present if the command requires it.
- Address: Target address (4 bytes, little-endian).
- Length: Optional length field (2 bytes, little-endian), present if the command involves data transfer.
- Data: Optional data payload (N bytes), present if the command includes data(split in 4 byte chunks).
- CRC: Optional checksum (1 byte), calculated over the entire packet except the start and end bytes.
- End Byte: Constant value 0x55 indicating the end of the packet.

Serialization:
- The packet is serialized by concatenating the fields in the order specified above.
- Multi-byte fields (Address and Length) are serialized in little-endian format.
- The CRC is calculated and appended if required by the command.

Deserialization:
- The packet is deserialized by reading the fields in the order specified above.
- The presence of optional fields is determined based on the command type and flags.
- The CRC is verified if present, ensuring data integrity.

Flags:
- Bit 0: mem_id present
- Bit 1: length present
- Bit 2: ACK/NACK