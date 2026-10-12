#ifndef MCU_MDT_EVENT_H
#define MCU_MDT_EVENT_H

#include <stdint.h>
#include "mcu_mdt_config.h"

/**
 * Events are derived from state, not queued. Each source (breakpoints,
 * watchpoints, error counters) remembers what it has not reported yet; the
 * event module just asks the sources, one at a time, "anything to report?".
 * Nothing can be dropped. Several changes between two polls collapse into
 * one event carrying the latest state.
 */

/**
 * @brief Enum representing the types of events that can be reported to the host.
 */
typedef enum {
    INTERNAL_MDT_EVENT_TYPE_NONE       = 0,
    INTERNAL_MDT_EVENT_BUFFER_OVERFLOW = 1,
    INTERNAL_MDT_EVENT_FAILED_PACKET   = 2,
    INTERNAL_MDT_EVENT_BREAKPOINT_HIT  = 3,
    INTERNAL_MDT_EVENT_WATCHPOINT_HIT  = 4,
    /* TODO: Add more event types */
} mdt_event_type_t;

/** @brief One event, as reported to the host. */
typedef struct {
    uint32_t address;
    uint32_t data;
    uint16_t length;
    uint8_t  seq;    /* event source id (breakpoint / watchpoint slot, 0 for system events) */
    uint8_t  type;   /* mdt_event_type_t */
} mdt_event_t;

/**
 * @brief Count a system error (BUFFER_OVERFLOW or FAILED_PACKET).
 * @note Call only from the packet-processing context (the one that also
 *       sends the replies), so no locking is needed.
 */
void mdt_event_error(uint8_t type);

/**
 * @brief Fetch the next thing to report and mark it reported.
 *        Priority: breakpoints, watchpoints, buffer overflow, failed packet.
 * @param ev Filled in when 1 is returned.
 * @return 1 if an event was produced, 0 if nothing is pending.
 */
uint8_t mdt_event_next(mdt_event_t *ev);

/**
 * @brief Poll mode: send ONE pending event as an unsolicited packet.
 * @note Does nothing unless the TX buffer is empty, so a packet is never
 *       truncated. Safe to call unconditionally.
 */
void mdt_event_send(void);

/**
 * @brief CMD_ID=0 poll handler: fills buf[] in place with one pending event
 *        and sets FLAG_EVENT. If nothing is pending the buffer is untouched.
 * @param buf Packet buffer to fill in place.
 * @return Always 1 so the ACK is sent.
 * @note Only compiled when MDT_FEATURE_UART_IDLE is enabled (interrupt mode).
 */
#if MDT_FEATURE_UART_IDLE
uint8_t mdt_event_fill_buf(uint8_t *buf);
#endif

#endif /* MCU_MDT_EVENT_H */
