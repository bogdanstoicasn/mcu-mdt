#ifndef MCU_MDT_PRIVATE_H
#define MCU_MDT_PRIVATE_H

#include "mcu_mdt_protocol.h"
#include <stdint.h>

typedef uint32_t mdt_fence_t;

/* Buffer structure */
typedef struct {
    mdt_fence_t fence_pre;

    uint8_t idx;
    uint8_t started;
    uint8_t buf[MDT_PACKET_SIZE];

    mdt_fence_t fence_post;

} mdt_buffer_t;

/* Event structure */
typedef struct {
    uint32_t address;
    uint32_t data;
    uint16_t length;
    uint8_t  seq;
    uint8_t  mem_id;

    volatile uint8_t pending;
} mdt_event_t;

/* Event type enumeration */
typedef enum {
    INTERNAL_MDT_EVENT_TYPE_NONE = 0,
    INTERNAL_MDT_EVENT_BUFFER_OVERFLOW = 1,
    INTERNAL_MDT_EVENT_FAILED_PACKET = 2,
    INTERNAL_MDT_EVENT_BREAKPOINT_HIT = 3,
    INTERNAL_MDT_EVENT_WATCHPOINT_HIT = 4,
    /* TODO: Add more event types */
} mdt_event_type_t;

void mdt_event_wrapper(
    uint8_t seq,
    uint8_t mem_id,
    uint32_t address,
    uint16_t length,
    uint32_t data);

#endif /* MCU_MDT_PRIVATE_H */