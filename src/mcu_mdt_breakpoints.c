#include "mcu_mdt_breakpoints.h"
#include "mcu_mdt_event.h"
#include "mcu_mdt.h"

static mdt_breakpoint_state_t bp_state = {0};

void mdt_breakpoint_trigger(uint8_t id)
{
    if (id >= MDT_MAX_BREAKPOINTS)
        return;

    if (!bp_state.slots[id].enabled)
        return;

    mdt_event_set(
        id,                                 /* seq = breakpoint ID */
        INTERNAL_MDT_EVENT_BREAKPOINT_HIT,  /* mem_id = event type */
        0,                                  /* address */
        0,                                  /* length */
        bp_state.slots[id].hit_count        /* data = hit count */
    );

    bp_state.slots[id].hit_count++;

#if MDT_FEATURE_UART_IDLE
    /* STM32 interrupt mode — PendSV handles all RX automatically.
     * Spin here: flush the pending event, sample watchpoints, and
     * wait for the PC to send NEXT or DISABLE. */
    while (bp_state.slots[id].enabled)
    {
        if (bp_state.slots[id].next)
        {
            bp_state.slots[id].next = INTERNAL_MDT_BP_DISABLE;
            break;
        }
    }
#else
    /* Poll mode (AVR) — must service RX manually in the spin loop.
     * mcu_mdt_poll() flushes the pending event and drains the RX buffer. */
    while (bp_state.slots[id].enabled)
    {
        mcu_mdt_poll();

        if (bp_state.slots[id].next)
        {
            bp_state.slots[id].next = INTERNAL_MDT_BP_DISABLE;
            break;
        }
    }
#endif
    /* NOTE: If the PC disconnects while a breakpoint is active the MCU
         * will spin here indefinitely. A hardware-independent timeout is not
         * implemented in v1.0. To recover, reset the MCU. */
}

static inline __attribute__((always_inline)) void mdt_breakpoint_enable(uint8_t id)
{
    bp_state.slots[id].enabled = INTERNAL_MDT_BP_ENABLE;
}

static inline __attribute__((always_inline)) void mdt_breakpoint_disable(uint8_t id)
{
    bp_state.slots[id].enabled = INTERNAL_MDT_BP_DISABLE;
}

static inline __attribute__((always_inline)) void mdt_breakpoint_reset(uint8_t id)
{
    bp_state.slots[id].enabled   = INTERNAL_MDT_BP_DISABLE;
    bp_state.slots[id].hit_count = INTERNAL_MDT_BP_DISABLE;
    bp_state.slots[id].next      = INTERNAL_MDT_BP_DISABLE;
}

static inline __attribute__((always_inline)) void mdt_breakpoint_next(uint8_t id)
{
    if (id < MDT_MAX_BREAKPOINTS && bp_state.slots[id].enabled)
        bp_state.slots[id].next = INTERNAL_MDT_BP_ENABLE;
}

static const mdt_breakpoint_handler_t bkp_handlers[] = {
    [INTERNAL_MDT_BP_DISABLE] = mdt_breakpoint_disable,
    [INTERNAL_MDT_BP_ENABLE]  = mdt_breakpoint_enable,
    [INTERNAL_MDT_BP_RESET]   = mdt_breakpoint_reset,
    [INTERNAL_MDT_BP_NEXT]    = mdt_breakpoint_next,
};

uint8_t mdt_breakpoint_dispatch(uint8_t control, uint32_t id)
{
    if (id >= MDT_MAX_BREAKPOINTS)
        return 0;

    if (control >= sizeof(bkp_handlers) / sizeof(bkp_handlers[0]))
        return 0;

    bkp_handlers[control]((uint8_t)id);

    return 1;
}
