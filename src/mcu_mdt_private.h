#ifndef MCU_MDT_PRIVATE_H
#define MCU_MDT_PRIVATE_H

#include "mcu_mdt_config.h"
#include "mcu_mdt_protocol.h"
#include <stdint.h>

/* Buffer structure */
typedef struct {

#ifdef MDT_FENCE_ENABLE
    mdt_fence_t fence_pre;
#endif

    uint16_t idx;
    uint8_t started;
    uint8_t buf[MDT_PACKET_SIZE];

#ifdef MDT_FENCE_ENABLE
    mdt_fence_t fence_post;
#endif
} mdt_buffer_t;

#ifdef MDT_FENCE_ENABLE
#define MDT_BUFFER_INIT { .fence_pre = MDT_FENCE_PATTERN, .fence_post = MDT_FENCE_PATTERN}
#else
#define MDT_BUFFER_INIT { 0 }
#endif

#endif /* MCU_MDT_PRIVATE_H */