#ifndef MCU_MDT_PRIVATE_H
#define MCU_MDT_PRIVATE_H

#include "mcu_mdt_config.h"
#include "mcu_mdt_protocol.h"
#include <stdint.h>

/* Buffer structure */
typedef struct {
    uint8_t buf[MDT_PACKET_MAX_SIZE];
    uint16_t idx;
    uint8_t started;
} mdt_buffer_t;

uint32_t handle_command(uint8_t *packet);

#endif /* MCU_MDT_PRIVATE_H */