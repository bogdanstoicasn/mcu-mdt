#ifndef MCU_MDT_EVENT_H
#define MCU_MDT_EVENT_H

#include <stdint.h>
#include "mcu_mdt_config.h"

#define MDT_EVENT_QUEUE_SIZE ...

typedef enum {
    MDT_EVENT_TYPE_NONE = 0,
    MDT_EVENT_BUFFER_OVERFLOW = 1,
    MDT_EVENT_FAILED_PACKET = 2,
    MDT_EVENT_BREAKPOINT_HIT = 3,
    // TODO: Add more event types
} mdt_event_type_t;

/* Push an event to the queue. Returns 1 on success, 0 if queue is full */
uint8_t mdt_event_push(mdt_event_type_t event);

/* Return the number of pending events */
uint8_t mdt_event_pending(void);

/* Send all pending events to the host */
void mdt_event_send_pending(void);


#endif /* MCU_MDT_EVENT_H */