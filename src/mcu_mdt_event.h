#ifndef MCU_MDT_EVENT_H
#define MCU_MDT_EVENT_H

#include <stdint.h>
#include "mcu_mdt_config.h"

/* Event type enumeration */
typedef enum {
    INTERNAL_MDT_EVENT_TYPE_NONE       = 0,
    INTERNAL_MDT_EVENT_BUFFER_OVERFLOW = 1,
    INTERNAL_MDT_EVENT_FAILED_PACKET   = 2,
    INTERNAL_MDT_EVENT_BREAKPOINT_HIT  = 3,
    INTERNAL_MDT_EVENT_WATCHPOINT_HIT  = 4,
    /* TODO: Add more event types */
} mdt_event_type_t;

/* Store a pending event. No-op if one is already pending. */
void mdt_event_set(
    uint8_t  seq,
    uint8_t  mem_id,
    uint32_t address,
    uint16_t length,
    uint32_t data);

/* Returns 1 if an event is waiting to be sent. */
uint8_t mdt_event_pending(void);

/* Serialize and transmit the pending event packet, then clear it.
 * Guards against empty — safe to call unconditionally. */
void mdt_event_send(void);

/* CMD_ID=0 poll handler: checks watchpoints, then fills buf[] with the
 * pending event payload and clears it. If no event is pending the buffer
 * is left untouched. Returns 1 in both cases so the ACK is always sent.
 * Only compiled when MDT_FEATURE_UART_IDLE is enabled (interrupt mode). */
#if MDT_FEATURE_UART_IDLE
uint8_t mdt_event_fill_buf(uint8_t *buf);
#endif

#endif /* MCU_MDT_EVENT_H */