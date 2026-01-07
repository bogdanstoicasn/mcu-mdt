#ifndef MCU_MDT_PRIVATE_H
#define MCU_MDT_PRIVATE_H

#include "mcu_mdt_config.h"
#include <stdint.h>

#define START_BYTE 0xAA
#define END_BYTE   0x55

/* For simplicity the packets with more data will be split in multiple packets
 * Example: if data filed is 16 => the split is 16 / 4 = 4 packets
 */
#define MDT_PACKET_SIZE   17
#define MDT_DATA_MAX_SIZE 4

#define MDT_OFFSET_CMD_ID  1
#define MDT_OFFSET_FLAGS   2
#define MDT_OFFSET_MEM_ID  3
#define MDT_OFFSET_ADDRESS 4
#define MDT_OFFSET_LENGTH  8
#define MDT_OFFSET_DATA    10
#define MDT_OFFSET_CRC     14

/* Packet structure */
typedef struct {
    uint8_t buf[MDT_PACKET_MAX_SIZE];
    uint16_t idx;
    uint8_t started;
} mdt_packet_t;

#endif /* MCU_MDT_PRIVATE_H */