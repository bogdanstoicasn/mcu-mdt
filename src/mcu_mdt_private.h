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

/* Event structure */
typedef union {
    struct {
        uint32_t data : 24;
        uint32_t type : 8;
    };

    uint32_t raw;
} mdt_event_t;

/* Event type enumeration */
typedef enum {
    MDT_EVENT_TYPE_NONE = 0,
    MDT_EVENT_BUFFER_OVERFLOW = 1,
    MDT_EVENT_FAILED_PACKET = 2,
    MDT_EVENT_BREAKPOINT_HIT = 3,
    // TODO: Add more event types
} mdt_event_type_t;

void mdt_event_wrapper(mdt_event_type_t type, uint32_t data);

#endif /* MCU_MDT_PRIVATE_H */