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

/* Send an event to the host.*/
void mdt_send_event(mdt_event_type_t event);


#endif /* MCU_MDT_EVENT_H */