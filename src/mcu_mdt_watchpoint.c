#include "mcu_mdt_watchpoint.h"

static mdt_watchpoint_state_t watchpoints_descriptor = {0};

/**
 * @brief Safely read a 32-bit value from memory.
 *
 * Uses byte-wise access to avoid unaligned access faults and
 * undefined behaviour on targets that do not support unaligned reads.
 *
 * @param address Memory address to read.
 * @return 32-bit little-endian value.
 */
static inline uint32_t mdt_read_u32(uint32_t address)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)address;
    return (uint32_t)p[0]
         | ((uint32_t)p[1] << 8)
         | ((uint32_t)p[2] << 16)
         | ((uint32_t)p[3] << 24);
}

uint8_t mdt_watchpoint_take_change(uint8_t *slot, uint32_t *old_value, uint32_t *new_value)
{
    for (uint8_t i = 0; i < MDT_MAX_WATCHPOINTS; i++)
    {
        if (!(watchpoints_descriptor.active_mask & (1u << i)))
            continue;

        mdt_watchpoint_t *wp = &watchpoints_descriptor.slots[i];
        uint32_t current = mdt_read_u32(wp->address);

        if ((current & wp->mask) != (wp->snapshot & wp->mask))
        {
            *slot      = i;
            *old_value = wp->snapshot;
            *new_value = current;
            wp->snapshot = current;
            return 1;
        }
    }
    return 0;
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