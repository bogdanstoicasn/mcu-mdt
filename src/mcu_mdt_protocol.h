#ifndef MCU_MDT_PROTOCOL_H
#define MCU_MDT_PROTOCOL_H

#include <stdint.h>
#include "mcu_mdt_config.h"

/* Protocol specific definitions */ 

#define MDT_START_BYTE 0xAA
#define MDT_END_BYTE   0x55

/* For simplicity the packets with more data will be split in multiple packets
 * Example: if data filed is 16 => the split is 16 / 4 = 4 packets
 */
#define MDT_PACKET_SIZE   18
#define MDT_FENCE_SIZE  4
#define MDT_PACKET_MAX_SIZE (MDT_PACKET_SIZE + MDT_FENCE_SIZE)

#define MDT_DATA_MAX_SIZE 4

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

typedef enum {
    MDT_FLAG_MEM_ID_PRESENT = 0x01,
    MDT_FLAG_LENGTH_PRESENT  = 0x02,
    MDT_FLAG_ACK_NACK        = 0x04,
    MDT_FLAG_SEQ_PRESENT     = 0x08,
    MDT_FLAG_LAST_PACKET     = 0x10,
    MDT_FLAG_STATUS_ERROR    = 0x20
} mdt_flags_t;

typedef enum {
    MDT_CMD_READ_MEM    = 0x01,
    MDT_CMD_WRITE_MEM   = 0x02,
    MDT_CMD_READ_REG    = 0x03,
    MDT_CMD_WRITE_REG   = 0x04,
    MDT_CMD_PING        = 0x05,
    MDT_CMD_RESET       = 0x06
} mdt_cmd_t;

typedef struct {
    uint8_t cmd_id; /* Command ID */
    uint8_t flags;  /* Flags */
    uint8_t seq;    /* Sequence number for multi-packet commands */
    uint8_t mem_id; /* Memory ID */
    uint32_t address; /* Address */
    uint16_t length;  /* Length */
    uint8_t data[MDT_DATA_MAX_SIZE]; /* Data */
    uint16_t crc;    /* CRC16 */
} mdt_packet_t;

uint16_t mdt_crc16(const uint8_t *data, uint16_t len);

/* Function to validate a MDT packet */
uint8_t mdt_packet_validate(const uint8_t *buf, uint16_t len);

uint8_t mdt_dispatch(uint8_t *buf);

#endif /* MCU_MDT_PROTOCOL_H */