#ifndef MCU_MDT_PRIVATE_H
#define MCU_MDT_PRIVATE_H

#include "mcu_mdt_config.h"
#include <stdint.h>

#define START_BYTE 0xAA
#define END_BYTE   0x55

/* Packet structure */
typedef struct {
    uint8_t buf[MDT_PACKET_MAX_SIZE];
    uint8_t idx;
    uint8_t started;
} mdt_packet_t;

#endif /* MCU_MDT_PRIVATE_H */