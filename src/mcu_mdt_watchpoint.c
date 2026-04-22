#include "mcu_mdt_watchpoint.h"
#include "mcu_mdt_event.h"

static mdt_watchpoint_state_t watchpoints_descriptor = {0};

/* Byte-by-byte 32-bit read
 * Safe at any address on all targets.
 * Avoids undefined behaviour from unaligned pointer casts
 * Prevents hardware alignment faults on Cortex-M0 */
static inline uint32_t mdt_read_u32(uint32_t address)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)address;
    return (uint32_t)p[0]
         | ((uint32_t)p[1] << 8)
         | ((uint32_t)p[2] << 16)
         | ((uint32_t)p[3] << 24);
}

void mcu_mdt_watchpoint_check(void)
{
    if (!watchpoints_descriptor.active_mask)
        return;

    uint8_t mask = watchpoints_descriptor.active_mask;
    uint8_t slot = 0;

    while (mask)
    {
        if (mask & 1)
        {
            uint32_t current = mdt_read_u32(watchpoints_descriptor.slots[slot].address);
            if ((current & watchpoints_descriptor.slots[slot].mask) !=
                (watchpoints_descriptor.slots[slot].snapshot & watchpoints_descriptor.slots[slot].mask))
            {
                watchpoints_descriptor.slots[slot].snapshot = current;
                mdt_event_set(
                    (uint8_t)slot,                                  /* seq = watchpoint ID */
                    INTERNAL_MDT_EVENT_WATCHPOINT_HIT,              /* mem_id = event type */
                    watchpoints_descriptor.slots[slot].snapshot,    /* address = old value */
                    4,                                              /* length = uint32 */
                    current                                         /* data = new value */
                );
            }
        }

        mask >>= 1;
        slot++;
    }
}

static inline void mdt_watchpoint_enable(uint8_t id, uint32_t address)
{
    watchpoints_descriptor.slots[id].address  = address;
    watchpoints_descriptor.slots[id].snapshot = mdt_read_u32(address);
    watchpoints_descriptor.slots[id].mask     = INTERNAL_MDT_DEFAULT_WP_MASK;
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
    watchpoints_descriptor.slots[id].mask     = INTERNAL_MDT_DEFAULT_WP_MASK;
    watchpoints_descriptor.active_mask       &= (uint8_t)~(1u << id);
}

static inline void mdt_watchpoint_setmask(uint8_t id, uint32_t mask)
{
    watchpoints_descriptor.slots[id].mask = mask;
}

uint8_t mdt_watchpoint_dispatch(uint8_t control, uint8_t id, uint32_t address)
{
    if (id >= MDT_MAX_WATCHPOINTS)
        return 0;

    switch (control)
    {
        case INTERNAL_MDT_WP_ENABLE:
            mdt_watchpoint_enable(id, address);
            return 1;

        case INTERNAL_MDT_WP_DISABLE:
            mdt_watchpoint_disable(id);
            return 1;

        case INTERNAL_MDT_WP_RESET:
            mdt_watchpoint_reset(id);
            return 1;

        case INTERNAL_MDT_WP_MASK:
            if (!(watchpoints_descriptor.active_mask & (1u << id)))
                return 0; /* watchpoint not active, mask ignored */
            mdt_watchpoint_setmask(id, address);
            return 1;

        default:
            return 0;
    }
}