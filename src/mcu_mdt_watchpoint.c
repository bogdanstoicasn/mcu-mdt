#include "mcu_mdt_watchpoint.h"
#include "mcu_mdt_private.h"

static volatile mdt_watchpoint_state_t watchpoints_descriptor = {0};

void mdt_watchpoint_poll(void)
{
    if (!watchpoints_descriptor.active_mask)
        return;

    uint8_t mask = watchpoints_descriptor.active_mask;
    uint8_t slot = 0;

    while (mask)
    {
        if (mask & 1)
        {
            uint32_t current = *((volatile uint32_t *)(uintptr_t)watchpoints_descriptor.slots[slot].address);
            if (current != watchpoints_descriptor.slots[slot].snapshot)
            {
                watchpoints_descriptor.slots[slot].snapshot = current;
                mdt_event_wrapper(MDT_EVENT_WATCHPOINT_HIT, (uint32_t)slot);
            }
        }

        mask >>= 1;
        slot++;
    }
}

static inline void mdt_watchpoint_enable(uint8_t id, uint32_t address)
{
    watchpoints_descriptor.slots[id].address  = address;
    watchpoints_descriptor.slots[id].snapshot = *((volatile uint32_t *)(uintptr_t)address);
    watchpoints_descriptor.active_mask       |= (uint8_t)(1u << id);
}

static inline void mdt_watchpoint_disable(uint8_t id)
{
    watchpoints_descriptor.active_mask &= (uint8_t)~(1u << id);
}

static inline void mdt_watchpoint_reset(uint8_t id)
{
    watchpoints_descriptor.slots[id].address  = 0;
    watchpoints_descriptor.slots[id].snapshot = 0;
    watchpoints_descriptor.active_mask       &= (uint8_t)~(1u << id);
}

uint8_t mdt_watchpoint_dispatch(uint8_t control, uint8_t id, uint32_t address)
{
    if (id >= MDT_MAX_WATCHPOINTS)
        return 0;

    switch (control)
    {
        case MDT_WP_ENABLE:
            mdt_watchpoint_enable(id, address);
            return 1;

        case MDT_WP_DISABLE:
            mdt_watchpoint_disable(id);
            return 1;

        case MDT_WP_RESET:
            mdt_watchpoint_reset(id);
            return 1;

        default:
            return 0;
    }
}