#include "mcu_mdt_breakpoints.h"
#include "mcu_mdt.h"
#include "mcu_mdt_config.h"

static mdt_breakpoint_t breakpoints[MDT_MAX_BREAKPOINTS] = {0};

void mdt_breakpoint_trigger(uint8_t id)
{
    if (id >= MDT_MAX_BREAKPOINTS)
        return;

    if (!breakpoints[id].enabled)
        return;
    
    breakpoints[id].hit_count++; // Optional: track hits

    // Cooperative loop: MCU can still service PC commands
    while (breakpoints[id].enabled)
    {
        mcu_mdt_poll();
        if (breakpoints[id].next)
        {
            breakpoints[id].next = 0; // Clear "next" flag
            break; // Exit loop to allow next breakpoint or normal execution
        }
        // TODO: Maybe use watchdog reset or timeout to avoid infinite loop if user forgets to disable breakpoint
    }
}

// Internal functions for breakpoint control (enable/disable/reset/next)
static inline void mdt_breakpoint_enable(uint8_t id)
{
    if (id < MDT_MAX_BREAKPOINTS)
        breakpoints[id].enabled = 1;
}

static inline void mdt_breakpoint_disable(uint8_t id)
{
    if (id < MDT_MAX_BREAKPOINTS)
        breakpoints[id].enabled = 0;
}

static inline void mdt_breakpoint_reset(uint8_t id)
{
    if (id < MDT_MAX_BREAKPOINTS)
    {
        breakpoints[id].enabled = 0;
        breakpoints[id].hit_count = 0;
    }
}

static inline void mdt_breakpoint_next(uint8_t id)
{
    if (id < MDT_MAX_BREAKPOINTS && breakpoints[id].enabled)
        breakpoints[id].next = 1;
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

    return 0;
}