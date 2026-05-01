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
    INTERNAL_MDT_FLAG_MEM_ID_PRESENT  = 0x01,
    INTERNAL_MDT_FLAG_LENGTH_PRESENT  = 0x02,
    INTERNAL_MDT_FLAG_ACK_NACK        = 0x04,
    INTERNAL_MDT_FLAG_SEQ_PRESENT     = 0x08,
    INTERNAL_MDT_FLAG_LAST_PACKET     = 0x10,
    INTERNAL_MDT_FLAG_STATUS_ERROR    = 0x20,
    INTERNAL_MDT_FLAG_EVENT           = 0x40,
} mdt_flags_t;

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

/* Number of bytes covered by the CRC (excludes START, CRC itself, END) */
#define MDT_CRC_COVER_LEN  (MDT_PACKET_SIZE - 1 - 2 - 1)

/* Command handler define */
typedef uint8_t (*mdt_cmd_handler_t)(uint8_t *buf);

uint16_t mdt_crc16(const uint8_t *data, uint16_t len);

/* Function to validate a MDT packet */
uint8_t mdt_packet_validate(const uint8_t *buf, uint16_t len);

/* Function to dispatch a MDT packet */
uint8_t mdt_dispatch(uint8_t *buf);

/* Request a reset after the current packet's ACK has been sent. */
void mdt_request_reset(void);

#endif /* MCU_MDT_PROTOCOL_H */