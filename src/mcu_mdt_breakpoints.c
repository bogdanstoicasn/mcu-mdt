#include "mcu_mdt_breakpoints.h"
#include "mcu_mdt.h"
#include "mcu_mdt_private.h"

static volatile mdt_breakpoint_state_t bp_state = {0};

__attribute__((noinline))
void mdt_breakpoint_trigger(uint8_t id)
{
    if (id >= MDT_MAX_BREAKPOINTS)
        return;

    if (!bp_state.slots[id].enabled)
        return;

    mdt_event_wrapper(MDT_EVENT_BREAKPOINT_HIT, id);

    bp_state.slots[id].hit_count++;

    /* Cooperative loop: MCU can still service PC commands */
    while (__builtin_expect(bp_state.slots[id].enabled, MDT_BP_ENABLE))
    {
        mcu_mdt_poll();
        if (bp_state.slots[id].next)
        {
            bp_state.slots[id].next = MDT_BP_DISABLE;
            break;
        }
        /* TODO: watchdog timeout to avoid infinite loop if PC disconnects */
    }
}

static inline __attribute__((always_inline)) void mdt_breakpoint_enable(uint8_t id)
{
    bp_state.slots[id].enabled = MDT_BP_ENABLE;
}

static inline __attribute__((always_inline)) void mdt_breakpoint_disable(uint8_t id)
{
    bp_state.slots[id].enabled = MDT_BP_DISABLE;
}

static inline __attribute__((always_inline)) void mdt_breakpoint_reset(uint8_t id)
{
    bp_state.slots[id].enabled   = MDT_BP_DISABLE;
    bp_state.slots[id].hit_count = MDT_BP_DISABLE;
    bp_state.slots[id].next      = MDT_BP_DISABLE;
}

static inline __attribute__((always_inline)) void mdt_breakpoint_next(uint8_t id)
{
    if (id < MDT_MAX_BREAKPOINTS && bp_state.slots[id].enabled)
        bp_state.slots[id].next = MDT_BP_ENABLE;
}

uint8_t mdt_breakpoint_dispatch(uint8_t cmd_id, uint32_t id)
{
    if (id >= MDT_MAX_BREAKPOINTS)
        return 0;

    switch (cmd_id)
    {
        case MDT_BP_DISABLE:
            mdt_breakpoint_disable(id);
            return 1;
        case MDT_BP_ENABLE:
            mdt_breakpoint_enable(id);
            return 1;
        case MDT_BP_RESET:
            mdt_breakpoint_reset(id);
            return 1;
        case MDT_BP_NEXT:
            mdt_breakpoint_next(id);
            return 1;
        default:
            return 0;
    }
}