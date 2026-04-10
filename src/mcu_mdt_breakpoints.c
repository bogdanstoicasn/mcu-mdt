#include "mcu_mdt_breakpoints.h"
#include "mcu_mdt.h"
#include "mcu_mdt_private.h"

static mdt_breakpoint_state_t bp_state = {0};

__attribute__((noinline))
void mdt_breakpoint_trigger(uint8_t id)
{
    if (id >= MDT_MAX_BREAKPOINTS)
        return;

    if (!bp_state.slots[id].enabled)
        return;

    mdt_event_wrapper(INTERNAL_MDT_EVENT_BREAKPOINT_HIT, id);

    bp_state.slots[id].hit_count++;

    /* Cooperative loop: MCU can still service PC commands */
    while (__builtin_expect(bp_state.slots[id].enabled, INTERNAL_MDT_BP_ENABLE))
    {
        mcu_mdt_poll();
        if (bp_state.slots[id].next)
        {
            bp_state.slots[id].next = INTERNAL_MDT_BP_DISABLE;
            break;
        }
        /* TODO: watchdog timeout to avoid infinite loop if PC disconnects */
    }
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

uint8_t mdt_breakpoint_dispatch(uint8_t cmd_id, uint32_t id)
{
    if (id >= MDT_MAX_BREAKPOINTS)
        return 0;

    if (cmd_id >= sizeof(bkp_handlers) / sizeof(bkp_handlers[0]))
        return 0;
    
    bkp_handlers[cmd_id]((uint8_t)id);

    return 1;
}
