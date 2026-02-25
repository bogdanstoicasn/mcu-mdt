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

    // Cooperative loop: MCU can still service PC commands
    while (breakpoints[id].enabled)
    {
        mcu_mdt_poll();
    }
}

// Optional: expose enable/disable functions internally
void mdt_breakpoint_enable(uint8_t id)
{
    if (id < MDT_MAX_BREAKPOINTS)
        breakpoints[id].enabled = 1;
}

void mdt_breakpoint_disable(uint8_t id)
{
    if (id < MDT_MAX_BREAKPOINTS)
        breakpoints[id].enabled = 0;
}