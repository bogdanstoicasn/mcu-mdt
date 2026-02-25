#ifndef MCU_MDT_PRIVATE_H
#define MCU_MDT_PRIVATE_H

#include "mcu_mdt_protocol.h"
#include <stdint.h>

typedef uint32_t mdt_fence_t;

/* Buffer structure */
typedef struct {
    mdt_fence_t fence_pre;

    uint16_t idx;
    uint8_t started;
    uint8_t buf[MDT_PACKET_SIZE];

    mdt_fence_t fence_post;

} mdt_buffer_t;

#endif /* MCU_MDT_PRIVATE_H */