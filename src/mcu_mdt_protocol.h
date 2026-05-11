#ifndef MCU_MDT_PROTOCOL_H
#define MCU_MDT_PROTOCOL_H

#include <stdint.h>
#include "mcu_mdt_config.h"

/* Protocol specific definitions */ 

#define MDT_START_BYTE 0xAA
#define MDT_END_BYTE   0x55


#define MDT_PACKET_SIZE   18

/* For simplicity the packets with more data will be split in multiple packets
 * Example: if data filed is 16 => the split is 16 / 4 = 4 packets
 */
#define MDT_DATA_MAX_SIZE 4

/* Offsets within the packet */
#define MDT_OFFSET_START     0
#define MDT_OFFSET_CMD_ID    1
#define MDT_OFFSET_FLAGS     2
#define MDT_OFFSET_SEQ       3
#define MDT_OFFSET_MEM_ID    4
#define MDT_OFFSET_ADDRESS   5
#define MDT_OFFSET_LENGTH    9
#define MDT_OFFSET_DATA      11
#define MDT_OFFSET_CRC       15
#define MDT_OFFSET_END       17

/** @brief Flags for the MDT packet
    *  - MEM_ID_PRESENT: Indicates that the mem_id field is present and valid.
    *  - LENGTH_PRESENT: Indicates that the length field is present and valid.
    *  - ACK_NACK: Indicates whether this packet is an acknowledgment (ACK) or negative acknowledgment (NACK).
    *  - SEQ_PRESENT: Indicates that the seq field is present and valid (used for multi-packet commands).
    *  - LAST_PACKET: Indicates that this is the last packet in a multi-packet command sequence.
    *  - STATUS_ERROR: Indicates that the packet contains an error status (used in responses).
    *  - EVENT: Indicates that this packet is an event notification rather than a command response.
*/
typedef enum {
    INTERNAL_MDT_FLAG_MEM_ID_PRESENT  = 0x01,
    INTERNAL_MDT_FLAG_LENGTH_PRESENT  = 0x02,
    INTERNAL_MDT_FLAG_ACK_NACK        = 0x04,
    INTERNAL_MDT_FLAG_SEQ_PRESENT     = 0x08,
    INTERNAL_MDT_FLAG_LAST_PACKET     = 0x10,
    INTERNAL_MDT_FLAG_STATUS_ERROR    = 0x20,
    INTERNAL_MDT_FLAG_EVENT           = 0x40,
} mdt_flags_t;

/** @brief Command IDs for the MDT packet
 * - NONE: No command, should not be called.
 * - READ_MEM: Read memory command.
 * - WRITE_MEM: Write memory command.
 * - READ_REG: Read register command.
 * - WRITE_REG: Write register command.
 * - PING: Ping command to check connectivity.
 * - RESET: Command to request a reset of the target device.
 * - BREAKPOINT: Command to manage breakpoints (set/clear).
 * - WATCHPOINT: Command to manage watchpoints (set/clear).
 * Note: The actual command handlers will be defined in the implementation file and will correspond to these command IDs.
*/
typedef enum {
    INTERNAL_MDT_CMD_NONE        = 0x00,
    INTERNAL_MDT_CMD_READ_MEM    = 0x01,
    INTERNAL_MDT_CMD_WRITE_MEM   = 0x02,
    INTERNAL_MDT_CMD_READ_REG    = 0x03,
    INTERNAL_MDT_CMD_WRITE_REG   = 0x04,
    INTERNAL_MDT_CMD_PING        = 0x05,
    INTERNAL_MDT_CMD_RESET       = 0x06,
    INTERNAL_MDT_CMD_BREAKPOINT  = 0x07,
    INTERNAL_MDT_CMD_WATCHPOINT  = 0x08,
} mdt_cmd_t;


/* Number of bytes covered by the CRC (excludes START, CRC itself, END) */
#define MDT_CRC_COVER_LEN  (MDT_PACKET_SIZE - 1 - 2 - 1)

/** @brief Type definition for MDT command handlers */
typedef uint8_t (*mdt_cmd_handler_t)(uint8_t *buf);

/** @brief Function to calculate CRC16 for a given data buffer 
 * @param data Pointer to the data buffer.
 * @param len Length of the data buffer.
 * @return The calculated CRC16 checksum.
*/
uint16_t mdt_crc16(const uint8_t *data, uint16_t len);

/** @brief Function to validate a MDT packet
 * @param buf Pointer to the packet buffer.
 * @param len Length of the packet buffer.
 * @return 1 if the packet is valid, 0 otherwise.
 */
uint8_t mdt_packet_validate(const uint8_t *buf, uint16_t len);

/** @brief Function to dispatch a MDT packet
 * @param buf Pointer to the packet buffer.
 * @return 1 if the packet was handled successfully, 0 otherwise.
 */
uint8_t mdt_dispatch(uint8_t *buf);

/** @brief Function to request a reset of the target device
 * @return None
 */
void mdt_request_reset(void);

#endif /* MCU_MDT_PROTOCOL_H */